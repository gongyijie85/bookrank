"""Explicit database administration must never hide startup writes or credentials."""

import ast
import importlib.util
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'init_external_postgres.py'


@pytest.fixture
def initializer():
    loggers = [logging.getLogger()] + [
        logger for logger in logging.Logger.manager.loggerDict.values() if isinstance(logger, logging.Logger)
    ]
    logging_state = {
        logger: (logger.disabled, logger.level, logger.handlers[:], logger.filters[:], logger.propagate)
        for logger in loggers
    }
    spec = importlib.util.spec_from_file_location('external_postgres_init', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        # Real migration env.py configures CLI logging; restore pytest/app loggers.
        for logger, (disabled, level, handlers, filters, propagate) in logging_state.items():
            logger.disabled = disabled
            logger.setLevel(level)
            logger.handlers[:] = handlers
            logger.filters[:] = filters
            logger.propagate = propagate


def test_import_does_not_load_runtime_or_mutate_environment():
    tree = ast.parse(SCRIPT.read_text(encoding='utf-8'))
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    assert all(node.module != 'run' and not (node.module or '').startswith('app') for node in imports)
    assert not any(isinstance(node, ast.Expr) and 'os.environ' in ast.unparse(node) for node in tree.body)


def test_procfile_starts_existing_server_without_build_or_dependency_install():
    command = next(
        line for line in (ROOT / 'Procfile').read_text(encoding='utf-8').splitlines() if line.startswith('web:')
    )
    assert command == 'web: gunicorn -c gunicorn.conf.py run:application'


def test_help_in_fresh_process_loads_no_runtime_or_dotenv():
    code = """
import builtins, runpy, sys
original_import = builtins.__import__
def restricted_import(name, *args, **kwargs):
    if name in ('app', 'run', 'dotenv') or name.startswith('app.'):
        raise AssertionError('runtime import before operator selected mode')
    return original_import(name, *args, **kwargs)
builtins.__import__ = restricted_import
sys.argv = [sys.argv[1], '--help']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
    result = subprocess.run([sys.executable, '-I', '-c', code, str(SCRIPT)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--bootstrap-empty-schema' in result.stdout


def test_default_only_verifies_without_printing_target(initializer, monkeypatch, capsys):
    from unittest.mock import Mock

    engine = Mock()
    verify = Mock(return_value=True)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://sensitive-user:secret@private-host/test?application_name=hidden')
    monkeypatch.setattr(initializer, '_make_engine', lambda *args: engine)
    monkeypatch.setattr(initializer, '_verify', verify)
    monkeypatch.setattr(initializer, '_upgrade', Mock(side_effect=AssertionError('unexpected upgrade')))
    monkeypatch.setattr(initializer, '_bootstrap', Mock(side_effect=AssertionError('unexpected bootstrap')))
    assert initializer.main([]) == 0
    verify.assert_called_once()
    output = capsys.readouterr().out
    assert all(value not in output for value in ('sensitive-user', 'secret', 'private-host', 'application_name'))
    engine.dispose.assert_called_once()


def test_seed_requires_explicit_write_mode(initializer, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(SystemExit) as exc:
        initializer.main(['--seed-base-data'])
    assert exc.value.code == 2


@pytest.mark.parametrize('schema', ['public', 'pg_catalog', 'information_schema', 'pg_unsafe', 'unsafe;DROP'])
def test_bootstrap_requires_dedicated_safe_schema(initializer, schema):
    with pytest.raises(SystemExit) as exc:
        initializer.main(['--bootstrap-empty-schema', '--schema', schema])
    assert exc.value.code == 2


def test_bootstrap_rejects_missing_schema_argument(initializer):
    with pytest.raises(SystemExit) as exc:
        initializer.main(['--bootstrap-empty-schema'])
    assert exc.value.code == 2


def test_error_output_never_contains_database_exception_details(initializer, monkeypatch, capsys):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:password@private-host/database')
    monkeypatch.setattr(initializer, '_make_engine', lambda *args: (_ for _ in ()).throw(RuntimeError('secret DSN')))
    assert initializer.main([]) == 1
    output = capsys.readouterr().out
    assert 'RuntimeError' in output
    assert 'secret DSN' not in output and 'private-host' not in output


def test_verify_is_read_only_even_for_missing_version(initializer):
    engine = create_engine('sqlite:///:memory:')
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda c, cur, sql, params, ctx, many: statements.append(sql))
    assert initializer._verify(engine, 'main') is False
    assert inspect(engine).get_table_names() == []
    assert all(
        not sql.lstrip().upper().startswith(('CREATE', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER'))
        for sql in statements
    )


@pytest.mark.parametrize('version', [None, 'unknown-version'])
def test_upgrade_rejects_unversioned_or_unknown_schema_without_writes(initializer, version):
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE retained (id INTEGER PRIMARY KEY)'))
        if version:
            connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)'))
            connection.execute(text('INSERT INTO alembic_version VALUES (:version)'), {'version': version})
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda c, cur, sql, params, ctx, many: statements.append(sql))
    with pytest.raises(ValueError):
        initializer._upgrade(engine, 'main')
    assert 'retained' in inspect(engine).get_table_names()
    assert all(not sql.lstrip().upper().startswith(('INSERT', 'DELETE', 'DROP', 'ALTER')) for sql in statements)
    if version:
        with engine.connect() as connection:
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == version


@pytest.fixture
def isolated_postgres(initializer):
    manifest_value = os.environ.get('BOOKRANK_BOOTSTRAP_PG_MANIFEST')
    if not manifest_value:
        pytest.skip('explicit disposable loopback PostgreSQL manifest required')
    manifest_path = Path(manifest_value).resolve()
    allowed = (ROOT / '.scratch' / 'incident-20261021' / 'continuation-pg').resolve()
    assert manifest_path.is_relative_to(allowed)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['host'] == '127.0.0.1' and manifest['started'] is True
    assert Path(manifest['data_dir']).resolve().is_relative_to(allowed)
    url = URL.create(
        'postgresql+psycopg2',
        username=manifest['username'],
        host='127.0.0.1',
        port=int(manifest['port']),
        database=manifest['database'],
    )
    control = create_engine(url, poolclass=NullPool, connect_args={'connect_timeout': 3})
    schema = f'bootstrap_audit_{uuid4().hex}'
    with control.begin() as connection:
        observed = connection.execute(text('SHOW data_directory')).scalar_one()
        assert Path(observed).resolve() == Path(manifest['data_dir']).resolve()
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine = initializer._make_engine(url, schema)
    try:
        yield engine, schema
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.dispose()


def test_pg_bootstrap_has_head_defaults_and_indexes(initializer, isolated_postgres):
    engine, schema = isolated_postgres
    initializer._bootstrap(engine, schema)
    assert initializer._verify(engine, schema)
    with engine.connect() as connection:
        assert initializer._versions(connection, schema) == (initializer.BOOTSTRAP_HEAD,)
        columns = {column['name']: column for column in inspect(connection).get_columns('publishers', schema=schema)}
        assert columns['site_crawl_enabled']['default'] == 'false'
        indexes = (
            connection.execute(text('SELECT indexname FROM pg_indexes WHERE schemaname=:schema'), {'schema': schema})
            .scalars()
            .all()
        )
        assert set(initializer.PERFORMANCE_INDEXES).issubset(indexes)
        assert {'idx_new_books_trgm_search', 'idx_award_books_trgm_search'}.issubset(indexes)
        assert connection.execute(text('SELECT COUNT(*) FROM publishers')).scalar_one() == 0
    with pytest.raises(ValueError, match='completely empty'):
        initializer._bootstrap(engine, schema)
    assert initializer._verify(engine, schema)


@pytest.mark.parametrize(
    'existing_object',
    [
        'CREATE TABLE unrelated (id INTEGER)',
        'CREATE TABLE alembic_version (version_num VARCHAR(64))',
        'CREATE SEQUENCE unrelated_sequence',
        "CREATE TYPE unrelated_type AS ENUM ('safe')",
        'CREATE VIEW unrelated_view AS SELECT 1 AS id',
        "CREATE COLLATION unrelated_collation (provider = libc, locale = 'C')",
        'CREATE OPERATOR === (LEFTARG=integer, RIGHTARG=integer, FUNCTION=pg_catalog.int4eq)',
    ],
)
def test_pg_bootstrap_rejects_any_existing_object(initializer, isolated_postgres, existing_object):
    engine, schema = isolated_postgres
    with engine.begin() as connection:
        connection.execute(text(existing_object))
    with pytest.raises(ValueError, match='completely empty'):
        initializer._bootstrap(engine, schema)
    assert 'publishers' not in inspect(engine).get_table_names(schema=schema)


@pytest.mark.parametrize('failure_point', ['extras', 'stamp'])
def test_pg_bootstrap_failure_rolls_back_schema_and_stamp(initializer, isolated_postgres, monkeypatch, failure_point):
    engine, schema = isolated_postgres

    def fail(*args, **kwargs):
        raise RuntimeError('injected write failure')

    if failure_point == 'extras':
        monkeypatch.setattr(initializer, '_bootstrap_extras', fail)
    else:
        monkeypatch.setattr(initializer.MigrationContext, 'stamp', fail)
    with pytest.raises(RuntimeError, match='injected write failure'):
        initializer._bootstrap(engine, schema)
    with engine.connect() as connection:
        initializer._require_empty_schema(connection, schema)
    assert inspect(engine).get_table_names(schema=schema) == []


def test_pg_upgrade_failure_keeps_existing_version_and_rows(initializer, isolated_postgres):
    engine, schema = isolated_postgres
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE retained (id INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO retained VALUES (1)'))
        connection.execute(text('CREATE TABLE list_snapshots (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('add_perf_indexes')"))
    with pytest.raises(ProgrammingError):
        initializer._upgrade(engine, schema)
    with engine.connect() as connection:
        assert initializer._versions(connection, schema) == ('add_perf_indexes',)
        assert connection.execute(text('SELECT id FROM retained')).scalar_one() == 1


def test_pg_upgrade_follows_existing_version_chain(initializer, isolated_postgres):
    engine, schema = isolated_postgres
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('add_perf_indexes')"))
    initializer._upgrade(engine, schema)
    assert initializer._verify(engine, schema)
    assert 'list_snapshots' in inspect(engine).get_table_names(schema=schema)


@pytest.mark.parametrize('static_result', [None, {'success': True}, {'success': False, 'errors': 1}])
def test_pg_explicit_seed_checks_business_result(initializer, isolated_postgres, monkeypatch, static_result):
    from unittest.mock import Mock

    import app.services.new_book as new_book_modules

    engine, schema = isolated_postgres
    initializer._bootstrap(engine, schema)
    modules = SimpleNamespace(
        publisher_manager=SimpleNamespace(init_publishers=Mock()),
        sync_engine=SimpleNamespace(ensure_static_data_seeded=Mock(return_value=static_result)),
    )
    monkeypatch.setattr(new_book_modules, 'create_new_book_modules', lambda: modules)
    if static_result is not None and static_result.get('success') is False:
        with pytest.raises(ValueError, match='incomplete'):
            initializer._seed_base_data(engine, schema)
        # Schema remains valid even though separately committed data needs review.
        assert initializer._verify(engine, schema)
    else:
        initializer._seed_base_data(engine, schema)
