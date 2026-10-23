"""Real blocked workers must keep their reservation after the caller times out."""

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.schemas import SystemConfig
from app.services.new_book.sync_engine import IngestStats, SyncEngine
from app.services.publisher_crawler.base_crawler import CrawlOutcome


@pytest.fixture(autouse=True)
def isolated_auto_verification_latch(app, monkeypatch):
    monkeypatch.setitem(app.extensions, 'new_book_sync_verification_pending', False)
    monkeypatch.setitem(app.config, 'ADMIN_SECRET', 'test-admin-secret')
    monkeypatch.setitem(app.config, 'CRON_SECRET', 'isolated-cron-secret')


@pytest.fixture
def blocked_sync(app, monkeypatch):
    import app.services.new_book.sync_engine as module

    entered = threading.Event()
    release = threading.Event()
    publisher = SimpleNamespace(
        id=731, name_en='Isolated Publisher', is_active=True, crawler_class='Test', sync_count=0
    )
    manager = MagicMock()
    manager.get_publisher.return_value = publisher
    manager.get_publishers.return_value = [publisher]
    engine = SyncEngine(manager, MagicMock())
    crawler = MagicMock(SUPPORTS_BACKFILL=False)
    calls = []

    def crawl(request):
        calls.append(request)
        entered.set()
        assert release.wait(3), 'test did not release blocked crawler'
        return CrawlOutcome(books=iter(()))

    crawler.get_new_books.side_effect = crawl
    monkeypatch.setattr(engine, 'get_crawler', lambda name: crawler)
    monkeypatch.setattr(engine, '_ingest_book_stream', lambda *args, **kwargs: IngestStats(total=1, added=1))
    monkeypatch.setattr(module, 'db', SimpleNamespace(session=MagicMock()))
    monkeypatch.setattr(module, '_PER_PUBLISHER_TIMEOUT', 0.02)
    yield SimpleNamespace(engine=engine, publisher=publisher, entered=entered, release=release, calls=calls)
    release.set()
    deadline = time.monotonic() + 3
    while hasattr(engine, 'has_in_flight') and engine.has_in_flight() and time.monotonic() < deadline:
        threading.Event().wait(0.005)


def test_timeout_keeps_single_publisher_reserved_across_three_entries(app, blocked_sync):
    engine = blocked_sync.engine
    with app.app_context():
        first = engine._sync_publisher_with_timeout(blocked_sync.publisher, None, 10, False)
        assert blocked_sync.entered.is_set() and not blocked_sync.release.is_set()
        assert first['status'] == 'pending_verification'
        assert first['transport_status'] == 'timeout'
        assert engine.has_in_flight() is True
        direct = engine.sync_publisher_books(blocked_sync.publisher.id, translate=False)
        timed = engine._sync_publisher_with_timeout(blocked_sync.publisher, None, 10, False)
        batch = engine.sync_all_publishers(translate=False)
        assert direct['status'] == timed['status'] == batch[0]['status'] == 'pending_verification'
        assert len(blocked_sync.calls) == 1

        blocked_sync.release.set()
        deadline = time.monotonic() + 2
        while engine.has_in_flight() and time.monotonic() < deadline:
            threading.Event().wait(0.005)
        assert engine.has_in_flight() is False
        assert engine.sync_publisher_books(blocked_sync.publisher.id, translate=False)['success'] is True
        assert len(blocked_sync.calls) == 2


def test_simultaneous_direct_calls_only_crawl_once(app, blocked_sync):
    def run():
        with app.app_context():
            return blocked_sync.engine.sync_publisher_books(blocked_sync.publisher.id, translate=False)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run)
        assert blocked_sync.entered.wait(1)
        second = executor.submit(run)
        try:
            assert second.result(timeout=0.3)['status'] == 'pending_verification'
            assert len(blocked_sync.calls) == 1
        finally:
            blocked_sync.release.set()
        assert first.result(timeout=1)['success'] is True
    assert blocked_sync.engine.has_in_flight() is False


def test_reservation_released_on_exception(app, blocked_sync, monkeypatch):
    engine = blocked_sync.engine
    monkeypatch.setattr(engine._publisher_manager, 'get_publisher', MagicMock(side_effect=RuntimeError('injected')))
    with app.app_context(), pytest.raises(RuntimeError, match='injected'):
        engine.sync_publisher_books(blocked_sync.publisher.id)
    assert engine.has_in_flight() is False


def test_queued_worker_is_reserved_before_execution(app, blocked_sync, monkeypatch):
    import app.services.new_book.sync_engine as module

    queued = Future()
    callbacks = []

    class DelayedExecutor:
        def __init__(self, **kwargs):
            pass

        def submit(self, callback):
            callbacks.append(callback)
            return queued

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(module, 'ThreadPoolExecutor', DelayedExecutor)
    engine = blocked_sync.engine
    with app.app_context():
        result = engine._sync_publisher_with_timeout(blocked_sync.publisher, None, 10, False)
        assert result['status'] == 'pending_verification'
        assert not blocked_sync.entered.is_set()
        assert engine.sync_publisher_books(blocked_sync.publisher.id)['status'] == 'pending_verification'
        assert blocked_sync.calls == []
        blocked_sync.release.set()
        assert queued.set_running_or_notify_cancel()
        queued.set_result(callbacks[0]())
        assert engine.has_in_flight() is False
        assert queued.result()['success'] is True


def test_old_callback_cannot_release_a_new_publisher_reservation(blocked_sync):
    engine = blocked_sync.engine
    publisher_id = blocked_sync.publisher.id
    old = engine._reserve_publisher(publisher_id)
    engine._release_publisher(publisher_id, old)
    new = engine._reserve_publisher(publisher_id)
    assert new is not old
    engine._release_publisher(publisher_id, old)
    assert engine.has_in_flight() is True
    assert engine._reserve_publisher(publisher_id) is None
    engine._release_publisher(publisher_id, new)
    assert engine.has_in_flight() is False


def test_batch_reservation_blocks_second_batch_and_releases_on_error(app, blocked_sync, monkeypatch):
    engine = blocked_sync.engine
    entered = threading.Event()
    release = threading.Event()

    def fail_batch(*args):
        entered.set()
        assert release.wait(2)
        raise RuntimeError('injected batch failure')

    monkeypatch.setattr(engine, '_sync_all_publishers', fail_batch)

    def run():
        with app.app_context():
            return engine.sync_all_publishers()

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(run)
        assert entered.wait(1)
        try:
            assert engine.has_in_flight() is True
            assert run()[0]['status'] == 'pending_verification'
            with app.app_context():
                assert engine.sync_publisher_books(blocked_sync.publisher.id)['status'] == 'pending_verification'
            assert blocked_sync.calls == []
        finally:
            release.set()
        with pytest.raises(RuntimeError, match='injected batch failure'):
            first.result(timeout=1)
    assert engine.has_in_flight() is False


def test_auto_summary_does_not_mark_unknown_outcome_finished(app, db, monkeypatch):
    import app.setup as setup

    modules = MagicMock()
    modules.sync_engine.has_in_flight.return_value = False
    modules.sync_engine.sync_all_publishers.return_value = [
        {'success': False, 'status': 'pending_verification', 'publisher': 'Blocked', 'added': 0, 'updated': 0},
    ]
    monkeypatch.setattr(setup, 'require_service', lambda name: modules)
    with app.app_context():
        result = setup.run_auto_sync()
        summary = json.loads(SystemConfig.get_value('last_auto_sync_result'))
        assert result['status'] == summary['status'] == 'pending_verification'
        assert result['pending_publishers'] == 1
        assert 'finished_at' not in summary
        assert 'observed_at' in summary
        assert SystemConfig.get_value('last_auto_sync_time') is None


def test_auto_refuses_whole_batch_while_backend_still_writing(app, db, monkeypatch):
    import app.setup as setup

    modules = MagicMock()
    modules.sync_engine.has_in_flight.return_value = True
    monkeypatch.setattr(setup, 'require_service', lambda name: modules)
    with app.app_context():
        assert setup.run_auto_sync()['status'] == 'pending_verification'
    modules.sync_engine.sync_all_publishers.assert_not_called()
    modules.publisher_manager.init_publishers.assert_not_called()


def test_auto_pending_summary_blocks_resubmit_after_worker_has_exited(app, db, monkeypatch):
    import app.setup as setup

    modules = MagicMock()
    modules.sync_engine.has_in_flight.return_value = False
    previous = json.dumps({'status': 'pending_verification', 'observed_at': 'isolated observation'})
    with app.app_context():
        SystemConfig.set_value('last_auto_sync_result', previous)
        db.session.commit()
        monkeypatch.setattr(setup, 'require_service', lambda name: modules)
        monkeypatch.setitem(app.extensions, 'new_book_modules', modules)
        assert setup.run_auto_sync()['status'] == 'pending_verification'
        assert setup.trigger_auto_sync_background(app)['status'] == 'pending_verification'
        assert SystemConfig.get_value('last_auto_sync_result') == previous
    modules.sync_engine.sync_all_publishers.assert_not_called()
    modules.publisher_manager.init_publishers.assert_not_called()


@pytest.mark.parametrize('failure_point', ['summary', 'commit'])
def test_auto_unknown_outcome_stays_blocked_when_summary_write_fails(app, db, monkeypatch, failure_point):
    import app.setup as setup

    modules = MagicMock()
    modules.sync_engine.has_in_flight.return_value = False
    modules.sync_engine.sync_all_publishers.return_value = [
        {'success': False, 'status': 'pending_verification', 'publisher': 'Blocked'},
    ]
    monkeypatch.setattr(setup, 'require_service', lambda name: modules)
    with app.app_context():
        with monkeypatch.context() as failing:
            if failure_point == 'summary':
                failing.setattr(
                    SystemConfig, 'set_value', MagicMock(side_effect=RuntimeError('injected write failure'))
                )
            else:
                failing.setattr(db.session, 'commit', MagicMock(side_effect=RuntimeError('injected commit failure')))
            assert setup.run_auto_sync()['status'] == 'pending_verification'
        assert setup.run_auto_sync()['status'] == 'pending_verification'
        assert SystemConfig.get_value('last_auto_sync_result') is None
    assert modules.sync_engine.sync_all_publishers.call_count == 1


def test_cron_http_reports_pending_without_claiming_new_task(client, app, monkeypatch):
    import app.setup as setup

    app.config['CRON_SECRET'] = 'isolated-cron-secret'
    monkeypatch.setattr(setup, 'trigger_auto_sync_background', lambda app: {'status': 'pending_verification'})
    response = client.get('/api/cron/trigger-new-books-sync', headers={'Authorization': 'Bearer isolated-cron-secret'})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['status'] == 'pending_verification'
    assert '未启动新任务' in payload['message']


@pytest.fixture
def route_modules(app, monkeypatch):
    import app.routes.new_books as routes

    modules = MagicMock()
    modules.sync_engine.has_in_flight.return_value = False
    monkeypatch.setattr(routes, 'get_new_book_modules', lambda: modules)
    monkeypatch.setattr(routes, 'submit_background_task', lambda callback: callback())
    with app.app_context():
        routes.get_sync_request_gate().reset()
    with routes._sync_task_lock:
        routes._sync_task.clear()
        routes._sync_task['status'] = 'idle'
    yield modules
    with routes._sync_task_lock:
        routes._sync_task.clear()
        routes._sync_task['status'] = 'idle'


def test_manual_all_keeps_unknown_pending_after_worker_exit(client, app, admin_headers, route_modules):
    import app.routes.new_books as routes

    route_modules.sync_engine.sync_all_publishers.return_value = [
        {'success': False, 'status': 'pending_verification', 'publisher': 'Blocked'},
    ]
    assert client.post('/api/new-books/sync', headers=admin_headers).status_code == 202
    snapshot = client.get('/api/new-books/sync/status', headers=admin_headers).get_json()['data']
    assert snapshot['status'] == 'pending_verification'
    assert 'finished_at' not in snapshot
    assert snapshot['backend_in_flight'] is False
    with app.app_context():
        routes.get_sync_request_gate().reset()
    assert client.post('/api/new-books/sync', headers=admin_headers).status_code == 409
    assert route_modules.sync_engine.sync_all_publishers.call_count == 1


@pytest.mark.parametrize('endpoint', ['/api/new-books/sync', '/api/new-books/sync/731'])
def test_manual_submission_rejected_while_backend_still_writing(client, admin_headers, route_modules, endpoint):
    route_modules.sync_engine.has_in_flight.return_value = True
    assert client.post(endpoint, headers=admin_headers).status_code == 409
    route_modules.sync_engine.sync_all_publishers.assert_not_called()
    route_modules.sync_engine.sync_publisher_books.assert_not_called()


def test_auto_db_pending_also_blocks_manual_submission(client, app, db, admin_headers, route_modules):
    with app.app_context():
        SystemConfig.set_value('last_auto_sync_result', json.dumps({'status': 'pending_verification'}))
        db.session.commit()
    assert client.post('/api/new-books/sync', headers=admin_headers).status_code == 409
    route_modules.sync_engine.sync_all_publishers.assert_not_called()


def test_manual_pending_also_blocks_auto_after_worker_exit(client, app, db, admin_headers, route_modules, monkeypatch):
    import app.setup as setup

    route_modules.sync_engine.sync_all_publishers.return_value = [
        {'success': False, 'status': 'pending_verification'},
    ]
    assert client.post('/api/new-books/sync', headers=admin_headers).status_code == 202
    with app.app_context():
        SystemConfig.set_value('last_auto_sync_result', json.dumps({'status': 'synced'}))
        db.session.commit()
        monkeypatch.setattr(setup, 'require_service', lambda name: route_modules)
        assert setup.run_auto_sync()['status'] == 'pending_verification'
    assert route_modules.sync_engine.sync_all_publishers.call_count == 1


@pytest.fixture
def admin_modules(route_modules, monkeypatch):
    import app.routes.admin as admin

    publisher = SimpleNamespace(id=731, name='Timeout Publisher', crawler_class='Test')
    route_modules.publisher_manager.get_publishers.return_value = [publisher]
    route_modules.publisher_manager.get_publisher_book_counts.return_value = {}
    monkeypatch.setattr(admin, 'get_new_book_modules', lambda: route_modules)
    monkeypatch.setattr(admin, '_crawler_status', {})
    return route_modules


def test_admin_pending_keeps_observation_and_blocks_all_origins(
    client, app, db, admin_headers, admin_modules, monkeypatch
):
    import app.setup as setup

    admin_modules.sync_engine.sync_publisher_books.return_value = {'success': False, 'status': 'pending_verification'}
    response = client.post('/api/admin/crawler/run/Timeout Publisher', headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json()['data']['status'] == 'pending_verification'
    snapshot = client.get('/api/admin/crawler/status', headers=admin_headers).get_json()['data']
    assert snapshot['backend_in_flight'] is False
    status = snapshot['publishers'][0]['last_run']
    assert status['status'] == 'pending_verification'
    assert 'observed_at' in status and 'finished_at' not in status
    assert client.post('/api/admin/crawler/run/Timeout Publisher', headers=admin_headers).status_code == 409
    assert client.post('/api/new-books/sync', headers=admin_headers).status_code == 409
    with app.app_context():
        monkeypatch.setattr(setup, 'require_service', lambda name: admin_modules)
        assert setup.run_auto_sync()['status'] == 'pending_verification'
    assert admin_modules.sync_engine.sync_publisher_books.call_count == 1
    admin_modules.sync_engine.sync_all_publishers.assert_not_called()


@pytest.mark.parametrize('origin', ['in_flight', 'auto_summary'])
def test_admin_submission_respects_shared_unknown_gate(client, app, db, admin_headers, admin_modules, origin):
    if origin == 'in_flight':
        admin_modules.sync_engine.has_in_flight.return_value = True
    else:
        with app.app_context():
            SystemConfig.set_value('last_auto_sync_result', json.dumps({'status': 'pending_verification'}))
            db.session.commit()
    assert client.post('/api/admin/crawler/run/Timeout Publisher', headers=admin_headers).status_code == 409
    admin_modules.sync_engine.sync_publisher_books.assert_not_called()
