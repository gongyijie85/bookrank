"""Persistent cron receipts prevent response-loss replays from executing twice."""

import json
import threading
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.schemas import SystemConfig


@pytest.mark.parametrize('failed,expected', [(0, 'skipped'), (1, 'failed')])
def test_skipped_sync_receipt_does_not_claim_data_was_refreshed(app, db, failed, expected):
    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        receipt, replayed = CronReceipt.claim('skipped-sync', 'new-books-sync')
        assert replayed is False
        receipt.finish_sync({'status': 'skipped', 'reason': 'all_sources_skipped', 'failed': failed})
        replay, duplicate = CronReceipt.claim('skipped-sync', 'new-books-sync')
        assert duplicate is True
        assert replay.snapshot()['status'] == expected
        assert replay.snapshot()['finished_at']


@pytest.fixture
def headers(app, monkeypatch):
    import app.setup as setup

    monkeypatch.setitem(app.config, 'CRON_SECRET', 'isolated-cron-receipt')
    monkeypatch.setattr(setup, '_auto_sync_lock', threading.Lock())
    monkeypatch.setitem(app.extensions, 'new_book_sync_verification_pending', False)
    return {'Authorization': 'Bearer isolated-cron-receipt', 'X-Idempotency-Key': 'isolated-workflow-run'}


def test_weekly_response_loss_replay_returns_durable_result_once(client, app, db, headers, monkeypatch):
    report = SimpleNamespace(
        id=42,
        report_date=date(2026, 10, 21),
        week_start=date(2026, 10, 19),
        week_end=date(2026, 10, 25),
        title='Isolated report',
    )
    generate = Mock(return_value=report)
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', generate)
    assert client.get('/api/cron/trigger-weekly-report', headers=headers).get_json()['data']['status'] == 'completed'
    # A new request has no process-local receipt object, as after response loss/restart.
    replay = client.get('/api/cron/trigger-weekly-report', headers=headers).get_json()['data']
    assert replay['status'] == 'completed'
    assert replay['replayed'] is True
    assert replay['result']['report_id'] == 42
    generate.assert_called_once()


def test_same_key_cannot_replay_another_operation(client, db, headers, monkeypatch):
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', Mock(return_value=None))
    client.get('/api/cron/trigger-weekly-report', headers=headers)
    trigger = Mock()
    monkeypatch.setattr('app.setup.trigger_auto_sync_background', trigger)
    assert client.get('/api/cron/trigger-new-books-sync', headers=headers).status_code == 409
    trigger.assert_not_called()


def test_weekly_missing_completion_never_becomes_completed(client, db, headers, monkeypatch):
    generate = Mock(return_value=None)
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', generate)
    for _ in range(2):
        result = client.get('/api/cron/trigger-weekly-report', headers=headers).get_json()['data']
        assert result['status'] == 'pending_verification'
    generate.assert_called_once()


def test_accepted_new_books_replay_does_not_submit_twice(client, app, db, headers, monkeypatch):
    import app.setup as setup

    thread = Mock()
    monkeypatch.setattr(setup.threading, 'Thread', Mock(return_value=thread))
    first = client.get('/api/cron/trigger-new-books-sync', headers=headers).get_json()['data']
    second = client.get('/api/cron/trigger-new-books-sync', headers=headers).get_json()['data']
    assert first['status'] == second['status'] == 'accepted'
    assert second['replayed'] is True
    thread.start.assert_called_once()
    # This test deliberately never executes its mocked worker.
    setup._auto_sync_lock.release()


def test_failed_weekly_attempt_is_durable_and_not_retried(client, db, headers, monkeypatch):
    generate = Mock(side_effect=RuntimeError('isolated failure'))
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', generate)
    client.get('/api/cron/trigger-weekly-report', headers=headers)
    result = client.get('/api/cron/trigger-weekly-report', headers=headers).get_json()['data']
    assert result['status'] == 'failed'
    generate.assert_called_once()


def test_receipt_old_owner_cannot_overwrite_new_state(app, db):
    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        receipt, replayed = CronReceipt.claim('isolated-fencing', 'weekly-report')
        assert replayed is False
        stale, replayed = CronReceipt.claim('isolated-fencing', 'weekly-report')
        assert replayed is True
        assert receipt.transition('running')
        assert stale.transition('completed', {'report_id': 999}) is False
        assert receipt.transition('completed', {'report_id': 42})
        assert receipt.snapshot()['result']['report_id'] == 42


def test_receipt_claim_commit_failure_never_executes_business(client, app, db, headers, monkeypatch):
    generate = Mock()
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', generate)
    monkeypatch.setattr(db.session, 'commit', Mock(side_effect=RuntimeError('unconfirmed commit')))
    response = client.get('/api/cron/trigger-weekly-report', headers=headers)
    assert response.status_code == 503
    generate.assert_not_called()


def test_cover_replay_stays_accepted_until_actual_worker_completes(client, app, db, headers, monkeypatch):
    captured = []
    monkeypatch.setattr('app.utils.service_helpers.submit_background_task', lambda callback: captured.append(callback))
    service = Mock()
    service.sync_missing_covers.return_value = {'status': 'success', 'updated': 3, 'failed': 0}
    monkeypatch.setattr('app.services.award_cover_sync_service.AwardCoverSyncService', Mock(return_value=service))
    monkeypatch.setattr('app.utils.service_helpers.get_or_create_google_books_client', Mock())
    for _ in range(2):
        assert client.get('/api/cron/sync-award-covers', headers=headers).get_json()['data']['status'] == 'accepted'
    assert len(captured) == 1
    captured[0]()
    result = client.get('/api/cron/sync-award-covers', headers=headers).get_json()['data']
    assert result['status'] == 'completed'
    assert result['result']['updated'] == 3
    service.sync_missing_covers.assert_called_once()


@pytest.mark.parametrize('bad_key', ['', 'x' * 201])
def test_invalid_idempotency_key_rejected_before_submission(client, db, headers, monkeypatch, bad_key):
    headers['X-Idempotency-Key'] = bad_key
    generate = Mock()
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', generate)
    assert client.get('/api/cron/trigger-weekly-report', headers=headers).status_code == 400
    generate.assert_not_called()


def test_auto_summary_commit_failure_does_not_report_synced(app, db, monkeypatch):
    import app.setup as setup

    modules = Mock()
    modules.sync_engine.has_in_flight.return_value = False
    modules.sync_engine.sync_all_publishers.return_value = [{'success': True, 'status': 'success'}]
    monkeypatch.setattr(setup, 'require_service', lambda name: modules)
    monkeypatch.setitem(app.extensions, 'new_book_sync_verification_pending', False)
    with app.app_context():
        with monkeypatch.context() as failing:
            failing.setattr(db.session, 'commit', Mock(side_effect=RuntimeError('isolated commit failure')))
            assert setup.run_auto_sync()['status'] == 'pending_verification'
        assert SystemConfig.get_value('last_auto_sync_time') is None
        assert setup.run_auto_sync()['status'] == 'pending_verification'
    assert modules.sync_engine.sync_all_publishers.call_count == 1


@pytest.mark.parametrize(
    ('outcome', 'expected'),
    [('synced', 'completed'), ('partial', 'failed'), ('pending_verification', 'pending_verification')],
)
def test_keyed_new_books_receipt_tracks_actual_worker_result(client, app, db, headers, monkeypatch, outcome, expected):
    import app.setup as setup

    result = {'status': outcome, 'added': 1, 'updated': 0, 'failed_publishers': 0, 'total_publishers': 1}
    run = Mock(return_value=result)
    monkeypatch.setattr(setup, 'run_auto_sync', run)
    monkeypatch.setattr(setup.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=kwargs['target']))
    for _ in range(2):
        data = client.get('/api/cron/trigger-new-books-sync', headers=headers).get_json()['data']
        assert data['status'] == expected
        assert data['result']['status'] == outcome
    run.assert_called_once()
    assert not setup._auto_sync_lock.locked()


def test_keyed_new_books_start_failure_is_durable_and_releases_lock(client, db, headers, monkeypatch):
    import app.setup as setup

    thread = Mock(start=Mock(side_effect=RuntimeError('isolated startup failure')))
    monkeypatch.setattr(setup.threading, 'Thread', Mock(return_value=thread))
    assert client.get('/api/cron/trigger-new-books-sync', headers=headers).status_code == 500
    result = client.get('/api/cron/trigger-new-books-sync', headers=headers).get_json()['data']
    assert result['status'] == 'failed'
    assert result['replayed'] is True
    assert not setup._auto_sync_lock.locked()
    thread.start.assert_called_once()


def test_all_disabled_sources_cannot_advance_success_freshness(app, db, monkeypatch):
    import app.setup as setup

    modules = Mock()
    modules.sync_engine.has_in_flight.return_value = False
    modules.sync_engine.sync_all_publishers.return_value = [{'success': True, 'status': 'skipped'}]
    monkeypatch.setattr(setup, 'require_service', lambda name: modules)
    monkeypatch.setitem(app.extensions, 'new_book_sync_verification_pending', False)
    with app.app_context():
        assert setup.run_auto_sync()['status'] == 'skipped'
        assert SystemConfig.get_value('last_auto_sync_time') is None


@pytest.mark.parametrize('status', ['accepted', 'running', 'completed', 'failed', 'pending_verification', 'skipped'])
def test_receipt_query_reads_all_states_without_writes_or_tasks(client, app, db, headers, monkeypatch, status):
    from sqlalchemy import event

    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        receipt, _ = CronReceipt.claim(headers['X-Idempotency-Key'], 'weekly-report:force-regenerate')
        if status != 'accepted':
            receipt.transition(status, {'report_id': 42})
        before = [(row.key, row.value) for row in SystemConfig.query.all()]
        statements = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        claim = Mock(side_effect=AssertionError('read endpoint must never claim'))
        transition = Mock(side_effect=AssertionError('read endpoint must never transition'))
        commit = Mock(side_effect=AssertionError('read endpoint must never commit'))
        monkeypatch.setattr(CronReceipt, 'claim', claim)
        monkeypatch.setattr(CronReceipt, 'transition', transition)
        monkeypatch.setattr(db.session, 'commit', commit)
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = client.get('/api/cron/receipt', headers=headers)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        assert response.status_code == 200
        assert response.get_json()['data']['status'] == status
        assert response.get_json()['data']['operation'] == 'weekly-report:force-regenerate'
        assert 'token' not in response.get_json()['data']
        assert response.headers['Cache-Control'] == 'no-store'
        assert [(row.key, row.value) for row in SystemConfig.query.all()] == before
        assert statements and all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
        claim.assert_not_called()
        transition.assert_not_called()
        commit.assert_not_called()


def test_receipt_query_unknown_key_never_creates_receipt(client, app, db, headers, monkeypatch):
    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        before = SystemConfig.query.count()
        claim = Mock(side_effect=AssertionError('unknown key must not start a task'))
        monkeypatch.setattr(CronReceipt, 'claim', claim)
        response = client.get('/api/cron/receipt', headers=headers)
        assert response.status_code == 404
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.get_json()['message'] == 'receipt_not_found'
        assert SystemConfig.query.count() == before
        claim.assert_not_called()


@pytest.mark.parametrize('authorization', [None, 'Bearer incorrect-secret'])
def test_receipt_query_requires_auth_before_database(client, app, db, headers, authorization):
    from sqlalchemy import event

    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    headers.pop('Authorization')
    if authorization:
        headers['Authorization'] = authorization
    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = client.get('/api/cron/receipt', headers=headers)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
    assert response.status_code == 401
    assert response.headers['Cache-Control'] == 'no-store'
    assert statements == []


@pytest.mark.parametrize('bad_key', [None, '', 'x' * 201, 'contains space', '\u4e2d\u6587'])
def test_receipt_query_rejects_missing_or_invalid_key_without_database(client, app, db, headers, bad_key):
    from sqlalchemy import event

    if bad_key is None:
        headers.pop('X-Idempotency-Key')
    else:
        headers['X-Idempotency-Key'] = bad_key
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = client.get('/api/cron/receipt', headers=headers)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
    assert response.status_code == 400
    assert response.headers['Cache-Control'] == 'no-store'
    assert statements == []


@pytest.mark.parametrize(
    'corrupt', [None, '', 'not-json-private-token', '[]', '{"token":"private-token"}', '{"status":"unknown"}']
)
def test_receipt_query_corrupt_record_fails_closed_without_exposing_data(
    client, app, db, headers, monkeypatch, caplog, corrupt
):
    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        receipt, _ = CronReceipt.claim(headers['X-Idempotency-Key'], 'weekly-report:force-regenerate')
        record = db.session.get(SystemConfig, receipt.key)
        record.value = corrupt
        db.session.commit()
        response = client.get('/api/cron/receipt', headers=headers)
        assert response.status_code == 503
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.get_json()['message'] == 'receipt_unavailable'
        assert 'private-token' not in response.get_data(as_text=True)
        assert 'private-token' not in caplog.text
        assert db.session.get(SystemConfig, receipt.key).value == corrupt


@pytest.mark.parametrize(
    'invalid_fields',
    [
        {'status': 'unknown'},
        {'operation': None},
        {'accepted_at': 'invalid-time'},
        {'observed_at': []},
        {'token': None},
        {'result': []},
        {'unexpected_private_field': 'private-token'},
    ],
)
def test_receipt_query_rejects_corrupted_envelope_fields(client, app, db, headers, invalid_fields, caplog):
    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        receipt, _ = CronReceipt.claim(headers['X-Idempotency-Key'], 'weekly-report:force-regenerate')
        record = db.session.get(SystemConfig, receipt.key)
        payload = json.loads(record.value)
        payload.update(invalid_fields)
        record.value = json.dumps(payload)
        db.session.commit()
        response = client.get('/api/cron/receipt', headers=headers)
        assert response.status_code == 503
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.get_json()['message'] == 'receipt_unavailable'
        assert payload['token'] is None or payload['token'] not in response.get_data(as_text=True)
        assert 'private-token' not in response.get_data(as_text=True)
        assert 'private-token' not in caplog.text


def test_receipt_query_does_not_flush_unrelated_pending_changes(client, app, db, headers):
    from sqlalchemy import event

    from app.services.cron_receipt import CronReceipt

    with app.app_context():
        CronReceipt.claim(headers['X-Idempotency-Key'], 'weekly-report:force-regenerate')
        db.session.add(SystemConfig(key='uncommitted-query-side-effect', value='must not flush'))
        statements = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = client.get('/api/cron/receipt', headers=headers)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        assert response.status_code == 200
        assert all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
        db.session.rollback()
        assert db.session.get(SystemConfig, 'uncommitted-query-side-effect') is None


def test_receipt_query_database_error_returns_generic_unavailable(client, app, db, headers, monkeypatch, caplog):
    from app.services.cron_receipt import CronReceipt

    monkeypatch.setattr(CronReceipt, 'read', Mock(side_effect=RuntimeError('private-database-marker')), raising=False)
    response = client.get('/api/cron/receipt', headers=headers)
    assert response.status_code == 503
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'private-database-marker' not in response.get_data(as_text=True)
    assert 'private-database-marker' not in caplog.text


def test_receipt_query_rate_limit_response_is_not_cached(client, app, db, headers, monkeypatch):
    from app.services.cron_receipt import CronReceipt

    monkeypatch.setitem(app.config, 'TESTING', False)
    limiter = Mock()
    limiter.is_allowed.return_value = False
    monkeypatch.setattr('app.utils.api_helpers.get_rate_limiter', Mock(return_value=limiter))
    read = Mock(side_effect=AssertionError('rate-limited request must not query receipts'))
    monkeypatch.setattr(CronReceipt, 'read', read)

    response = client.get('/api/cron/receipt', headers=headers)

    assert response.status_code == 429
    assert response.headers['Cache-Control'] == 'no-store'
    limiter.is_allowed.assert_called_once()
    read.assert_not_called()
