"""请求路径不得运行生产迁移，失败不得破坏迁移历史。"""

from unittest.mock import Mock

import pytest

import run as runtime


def test_production_business_request_never_initializes_database(monkeypatch):
    monkeypatch.setitem(runtime.app.config, 'APP_ENV', 'production')
    initialize = Mock()
    monkeypatch.setattr(runtime, '_init_database_lazy', initialize)
    with runtime.app.test_request_context('/rankings'):
        runtime._ensure_db_ready()
    initialize.assert_not_called()


def test_failed_upgrade_preserves_version_history(monkeypatch):
    monkeypatch.delenv('SPACE_ID', raising=False)
    database = Mock()
    database.session.execute.return_value.fetchone.return_value = ('known_revision',)
    monkeypatch.setattr(runtime, 'db', database)
    upgrade = Mock(side_effect=RuntimeError('migration failed'))
    monkeypatch.setattr('flask_migrate.upgrade', upgrade)
    stamp = Mock()
    monkeypatch.setattr('flask_migrate.stamp', stamp)
    assert runtime._run_migrations() is False
    database.session.commit.assert_not_called()
    database.create_all.assert_not_called()
    stamp.assert_not_called()
    assert not any('DELETE' in str(call) for call in database.session.execute.call_args_list)


def test_failed_lazy_init_is_not_marked_success(monkeypatch):
    monkeypatch.setattr(runtime, '_db_initialized', False)
    database = Mock()
    database.session.query.side_effect = RuntimeError('seed unavailable')
    monkeypatch.setattr(runtime, 'db', database)
    assert runtime._init_database_lazy() is False
    assert runtime._db_initialized is False
    runtime.db.create_all.assert_not_called()


def test_local_first_business_request_uses_existing_model_schema(monkeypatch):
    from app import create_app
    from app.models.new_book import Publisher
    from app.models.schemas import Award

    local = create_app('testing')
    monkeypatch.setattr(runtime, 'app', local)
    monkeypatch.setattr(runtime, '_db_initialized', False)
    migrate = Mock(side_effect=AssertionError('request must not migrate'))
    monkeypatch.setattr(runtime, '_run_migrations', migrate)
    with local.test_request_context('/about'):
        assert runtime._ensure_db_ready() is None
        assert runtime._db_initialized is True
        assert Award.query.count() > 0
        assert Publisher.query.count() > 0
    migrate.assert_not_called()


@pytest.mark.parametrize('path', ['/health', '/health/ready', '/static/missing.css'])
def test_health_and_static_do_not_initialize_database(monkeypatch, path):
    initialize = Mock()
    monkeypatch.setattr(runtime, '_init_database_lazy', initialize)
    with runtime.app.test_request_context(path):
        runtime._ensure_db_ready()
    initialize.assert_not_called()


def test_production_readiness_missing_schema_is_read_only(app, db, client, monkeypatch):
    from sqlalchemy import event, inspect

    monkeypatch.setitem(app.config, 'APP_ENV', 'production')
    statements = []
    with app.app_context():
        before = set(inspect(db.engine).get_table_names())

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = client.get('/health/ready')
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        assert set(inspect(db.engine).get_table_names()) == before
    assert response.status_code == 503
    assert response.json['error'] == 'schema_not_ready'
    assert statements and all(sql.lstrip().upper().startswith('SELECT') for sql in statements)


def test_production_readiness_requires_current_revision(app, db, client, monkeypatch):
    from app.services.health_service import _schema_heads

    monkeypatch.setitem(app.config, 'APP_ENV', 'production')
    with app.app_context():
        db.session.execute(db.text('CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)'))
        try:
            db.session.execute(db.text("INSERT INTO alembic_version VALUES ('obsolete')"))
            db.session.commit()
            assert client.get('/health/ready').status_code == 503
            db.session.execute(db.text('DELETE FROM alembic_version'))
            for revision in _schema_heads():
                db.session.execute(db.text('INSERT INTO alembic_version VALUES (:revision)'), {'revision': revision})
            db.session.commit()
            assert client.get('/health/ready').status_code == 200
        finally:
            db.session.execute(db.text('DROP TABLE alembic_version'))
            db.session.commit()


def test_duplicate_cron_reserves_lock_before_thread_start(app, monkeypatch):
    import threading

    import app.setup as setup

    lock = threading.Lock()
    monkeypatch.setattr(setup, '_auto_sync_lock', lock)
    thread = Mock()
    monkeypatch.setattr(setup.threading, 'Thread', Mock(return_value=thread))
    assert setup.trigger_auto_sync_background(app)['status'] == 'started'
    assert setup.trigger_auto_sync_background(app)['status'] == 'already_running'
    thread.start.assert_called_once()


def test_cron_thread_start_failure_releases_lock(app, monkeypatch):
    import threading

    import app.setup as setup

    lock = threading.Lock()
    monkeypatch.setattr(setup, '_auto_sync_lock', lock)
    monkeypatch.setattr(setup.threading, 'Thread', Mock(return_value=Mock(start=Mock(side_effect=RuntimeError))))
    with pytest.raises(RuntimeError):
        setup.trigger_auto_sync_background(app)
    assert not lock.locked()


def test_production_deferred_init_never_cleans_or_seeds(monkeypatch):
    import app.setup as setup

    clean = Mock()
    seed = Mock()
    monkeypatch.setattr(runtime, '_cleanup_dirty_translations', clean)
    monkeypatch.setattr('app.initialization.sample_award_books.init_sample_award_books', seed)
    setup._deferred_init_task(Mock(config={'APP_ENV': 'production'}))
    clean.assert_not_called()
    seed.assert_not_called()
