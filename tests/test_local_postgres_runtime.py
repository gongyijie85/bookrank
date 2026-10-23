"""Opt-in checks against an explicitly identified, disposable loopback cluster.

Set BOOKRANK_LOCAL_PG_MANIFEST to the incident runner's manifest. The default
suite skips these checks and never opens a PostgreSQL connection.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.models.database import db
from app.models.new_book import BatchImportReceipt, NewBook, Publisher
from app.routes.api import api_bp
from app.routes.health import health_bp
from app.services import batch_import_service, pilot_gate_service, source_health_service
from app.services.health_service import _schema_heads

_MANIFEST_ENV = 'BOOKRANK_LOCAL_PG_MANIFEST'
pytestmark = pytest.mark.skipif(not os.environ.get(_MANIFEST_ENV), reason='explicit local PostgreSQL manifest required')


@pytest.fixture(scope='module')
def local_pg_app():
    manifest_path = Path(os.environ[_MANIFEST_ENV]).resolve()
    incident_root = Path(__file__).resolve().parents[1] / '.scratch' / 'incident-20261021' / 'continuation-pg'
    assert manifest_path.is_relative_to(incident_root.resolve()), 'manifest must belong to the incident directory'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['host'] == '127.0.0.1'
    assert manifest['started'] is True
    assert Path(manifest['data_dir']).resolve().is_relative_to(incident_root.resolve())
    url = URL.create(
        'postgresql+psycopg2',
        username=manifest['username'],
        host='127.0.0.1',
        port=int(manifest['port']),
        database=manifest['database'],
    )
    control = create_engine(url, poolclass=NullPool, connect_args={'connect_timeout': 3})
    schema = f'bookrank_validation_{uuid4().hex}'
    with control.begin() as connection:
        observed = connection.execute(text('SHOW data_directory')).scalar_one()
        assert Path(observed).resolve() == Path(manifest['data_dir']).resolve(), 'wrong local PostgreSQL cluster'
        connection.execute(text(f'CREATE SCHEMA {schema}'))

    application = Flask('bookrank-local-postgres-validation')
    application.config.update(
        TESTING=True,
        APP_ENV='production',
        SECRET_KEY='isolated-pg-test-only',
        BATCH_IMPORT_SECRET='isolated-pg-import-only',
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_ENGINE_OPTIONS={
            'pool_size': 2,
            'max_overflow': 1,
            'pool_timeout': 3,
            'pool_pre_ping': True,
            'connect_args': {'connect_timeout': 3, 'options': f'-c search_path={schema} -c statement_timeout=5000'},
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)
    application.register_blueprint(health_bp)
    application.register_blueprint(api_bp)

    import run as runtime

    application.before_request(runtime._ensure_db_ready)

    @application.route('/local-business-check')
    def business_check():
        return {'success': True}

    @application.teardown_appcontext
    def remove_session(error=None):
        db.session.remove()

    application.extensions['local_pg_control'] = control
    try:
        yield application
    finally:
        with application.app_context():
            db.session.remove()
            db.engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.dispose()


@pytest.fixture
def pg_case(local_pg_app, monkeypatch):
    import run as runtime

    monkeypatch.setattr(runtime, 'app', local_pg_app)
    # Follow-up source monitoring is independent of the atomic import transaction.
    monkeypatch.setattr(source_health_service, 'record_plan_success', lambda *args, **kwargs: None)
    monkeypatch.setattr(pilot_gate_service, 'record_evidence_run', lambda *args, **kwargs: None)
    with local_pg_app.app_context():
        db.create_all()
    yield local_pg_app
    with local_pg_app.app_context():
        db.session.remove()
        db.drop_all()
        db.session.execute(text('DROP TABLE IF EXISTS alembic_version'))
        db.session.commit()


def _set_version(revisions):
    db.session.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)'))
    for revision in revisions:
        db.session.execute(text('INSERT INTO alembic_version VALUES (:revision)'), {'revision': revision})
    db.session.commit()


def _add_publisher():
    publisher = Publisher(
        name='Local PostgreSQL Publisher',
        name_en='HarperCollins',
        crawler_class='HarperCollinsGoogleCrawler',
        site_import_enabled=True,
        site_display_primary=True,
    )
    db.session.add(publisher)
    db.session.commit()


def _payload():
    records = [
        {
            'title': 'PostgreSQL import check',
            'author': 'Local Author',
            'isbn13': '9780063417113',
            'source_url': 'https://www.harpercollins.com/products/local-postgres-check',
            'publication_date': (datetime.now(UTC) - timedelta(days=2)).date().isoformat(),
            'editions': [{'format': 'Hardcover', 'isbn13': '9780063417113', 'is_main': True}],
            'missing_fields': [],
            'field_provenance': [],
        }
    ]
    digest = batch_import_service.compute_content_sha256('harpercollins', 'hc-observer-v1', records)
    return {
        'batch_id': f'harpercollins:pg-local:{digest[:16]}',
        'source_id': 'harpercollins',
        'schema_version': 'hc-observer-v1',
        'content_sha256': digest,
        'produced_at': datetime.now(UTC).isoformat(),
        'producer': 'isolated-local-postgres-test',
        'records': records,
    }


def test_postgres_cron_claim_concurrent_replay_and_dispose(pg_case):
    from app.services.cron_receipt import CronReceipt

    barrier = threading.Barrier(4)

    def claim():
        with pg_case.app_context():
            barrier.wait(timeout=5)
            receipt, replayed = CronReceipt.claim('local-pg-concurrent-cron', 'new-books-sync:max-15:batch-1')
            return receipt.snapshot(), replayed

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: claim(), range(4)))
    assert sum(not replayed for _, replayed in results) == 1
    assert all(snapshot['status'] == 'accepted' for snapshot, _ in results)
    with pg_case.app_context():
        db.session.remove()
        db.engine.dispose()
        receipt, replayed = CronReceipt.claim('local-pg-concurrent-cron', 'new-books-sync:max-15:batch-1')
        assert replayed is True
        assert receipt.snapshot()['status'] == 'accepted'


def test_postgres_cron_response_loss_replays_one_durable_completion(pg_case):
    from app.models.schemas import SystemConfig
    from app.services.cron_receipt import CronReceipt

    with pg_case.app_context():
        receipt, replayed = CronReceipt.claim('local-pg-completed-cron', 'weekly-report:force-regenerate')
        assert replayed is False
        assert receipt.transition('running')
        assert receipt.transition('completed', {'report_id': 42})
        db.session.remove()
        db.engine.dispose()
        repeated, replayed = CronReceipt.claim('local-pg-completed-cron', 'weekly-report:force-regenerate')
        assert replayed is True
        assert repeated.snapshot()['status'] == 'completed'
        assert repeated.snapshot()['result'] == {'report_id': 42}
        assert SystemConfig.query.filter(SystemConfig.key.like('cron_receipt:%')).count() == 1


def _post(application, payload):
    with application.test_client() as client:
        response = client.post(
            '/api/new-books/import-batch',
            data=json.dumps(payload, sort_keys=True).encode(),
            content_type='application/json',
            headers={'Authorization': 'Bearer isolated-pg-import-only'},
        )
        return response.status_code, response.get_json()


def test_postgres_missing_revision_readiness_does_not_write(pg_case):
    statements = []
    with pg_case.app_context():
        before = set(inspect(db.engine).get_table_names())

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = pg_case.test_client().get('/health/ready')
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        assert set(inspect(db.engine).get_table_names()) == before
    assert response.status_code == 503
    assert response.json['error'] == 'schema_not_ready'
    assert statements and all(statement.lstrip().upper().startswith('SELECT') for statement in statements)


def test_postgres_revision_mismatch_does_not_trigger_business_migration(pg_case, monkeypatch):
    import run as runtime

    initialize = Mock(side_effect=AssertionError('production request must not initialize'))
    monkeypatch.setattr(runtime, '_init_database_lazy', initialize)
    with pg_case.app_context():
        _set_version(['obsolete'])
    client = pg_case.test_client()
    assert client.get('/health/ready').status_code == 503
    assert client.get('/local-business-check').status_code == 200
    initialize.assert_not_called()
    with pg_case.app_context():
        assert db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == 'obsolete'


def test_postgres_current_revision_ready_and_connections_returned(pg_case):
    with pg_case.app_context():
        _set_version(_schema_heads())
        engine = db.engine
    for _ in range(20):
        response = pg_case.test_client().get('/health/ready')
        assert response.status_code == 200
        assert engine.pool.checkedout() == 0


def test_postgres_pool_recovers_a_terminated_idle_connection(pg_case):
    with pg_case.app_context():
        _set_version(_schema_heads())
        engine = db.engine
        with engine.connect() as connection:
            stale_pid = connection.execute(text('SELECT pg_backend_pid()')).scalar_one()
    control = pg_case.extensions['local_pg_control']
    with control.begin() as connection:
        assert connection.execute(text('SELECT pg_terminate_backend(:pid)'), {'pid': stale_pid}).scalar_one() is True
    assert pg_case.test_client().get('/health/ready').status_code == 200
    assert engine.pool.checkedout() == 0
    with engine.connect() as connection:
        assert connection.execute(text('SELECT pg_backend_pid()')).scalar_one() != stale_pid


def test_postgres_committed_response_lost_replay_keeps_one_book_and_receipt(pg_case):
    with pg_case.app_context():
        _add_publisher()
    payload = _payload()
    first_status, _discarded_response = _post(pg_case, payload)
    assert first_status == 200
    second_status, repeated = _post(pg_case, payload)
    assert second_status == 200
    assert repeated['data']['status'] == 'duplicate'
    with pg_case.app_context():
        assert NewBook.query.count() == 1
        assert BatchImportReceipt.query.count() == 1


def test_postgres_receipt_failure_rolls_back_book_write(pg_case):
    with pg_case.app_context():
        _add_publisher()
        session = db.session()

        observed = []

        def fail_receipt(session, flush_context):
            connection = session.connection()
            rows = (
                connection.execute(text('SELECT count(*) FROM new_books')).scalar_one(),
                connection.execute(text('SELECT count(*) FROM batch_import_receipts')).scalar_one(),
            )
            observed.append(rows)
            raise RuntimeError('injected receipt transaction failure')

        event.listen(session, 'after_flush_postexec', fail_receipt)
        try:
            with pytest.raises(RuntimeError, match='injected receipt transaction failure'):
                batch_import_service.import_batch(_payload())
        finally:
            event.remove(session, 'after_flush_postexec', fail_receipt)
            db.session.rollback()
        assert observed == [(1, 1)]
        assert NewBook.query.count() == 0
        assert BatchImportReceipt.query.count() == 0


def test_postgres_simultaneous_same_batch_returns_matching_receipts(pg_case, monkeypatch):
    with pg_case.app_context():
        _add_publisher()
    barrier = threading.Barrier(2, timeout=10)
    original_get = db.session.get

    def synchronized_initial_lookup(model, identity, *args, **kwargs):
        result = original_get(model, identity, *args, **kwargs)
        if model is BatchImportReceipt and result is None:
            barrier.wait()
        return result

    monkeypatch.setattr(db.session, 'get', synchronized_initial_lookup)
    payload = _payload()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: _post(pg_case, payload), range(2)))
    with pg_case.app_context():
        assert NewBook.query.count() == 1
        assert BatchImportReceipt.query.count() == 1
    assert [status for status, _body in results] == [200, 200]
    assert {body['data']['status'] for _status, body in results} == {'applied', 'duplicate'}


def test_postgres_conflicting_concurrent_payload_returns_409(pg_case, monkeypatch):
    with pg_case.app_context():
        _add_publisher()
    barrier = threading.Barrier(2, timeout=10)
    original_get = db.session.get

    def synchronized_initial_lookup(model, identity, *args, **kwargs):
        result = original_get(model, identity, *args, **kwargs)
        if model is BatchImportReceipt and result is None:
            barrier.wait()
        return result

    monkeypatch.setattr(db.session, 'get', synchronized_initial_lookup)
    original = _payload()
    conflict = json.loads(json.dumps(original))
    conflict['records'][0]['title'] = 'Different concurrent payload'
    conflict['content_sha256'] = batch_import_service.compute_content_sha256(
        conflict['source_id'], conflict['schema_version'], conflict['records']
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda payload: _post(pg_case, payload), [original, conflict]))
    assert sorted(status for status, _body in results) == [200, 409]
    rejected = next(body for status, body in results if status == 409)
    assert rejected['errors']['code'] == 'DIGEST_MISMATCH'
    with pg_case.app_context():
        assert NewBook.query.count() == 1
        receipt = BatchImportReceipt.query.one()
        book = NewBook.query.one()
        expected_title = (
            original['records'][0]['title']
            if receipt.content_sha256 == original['content_sha256']
            else conflict['records'][0]['title']
        )
        assert book.title == expected_title


def test_postgres_other_unique_constraint_is_not_a_duplicate_receipt(pg_case, monkeypatch, caplog):
    with pg_case.app_context():
        _add_publisher()
    barrier = threading.Barrier(2, timeout=10)
    original_lookup = batch_import_service._BatchLookup.__init__

    def synchronized_book_lookup(self, publisher):
        original_lookup(self, publisher)
        barrier.wait()

    monkeypatch.setattr(batch_import_service._BatchLookup, '__init__', synchronized_book_lookup)
    first = _payload()
    other = {**first, 'batch_id': first['batch_id'] + '-other'}
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda payload: _post(pg_case, payload), [first, other]))
    assert sorted(status for status, _body in results) == [200, 500]
    assert next(body for status, body in results if status == 500)['success'] is False
    with pg_case.app_context():
        assert NewBook.query.count() == 1
        assert BatchImportReceipt.query.count() == 1
    # The existing API exception handler must not receive raw SQL or payloads.
    assert 'INSERT INTO' not in caplog.text
    assert first['records'][0]['source_url'] not in caplog.text
