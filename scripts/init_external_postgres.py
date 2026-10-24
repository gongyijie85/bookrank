"""Explicit PostgreSQL administration; default operation is read-only.

Bootstrap supports the reviewed current model/head baseline in an existing,
dedicated empty schema. It never repairs an unversioned or partial old schema.
"""

import argparse
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import DefaultClause, MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_HEAD = 'add_list_snapshots'

# Historical server defaults are absent from the models' Python-side defaults.
SERVER_DEFAULTS = {
    'translation_cache': {
        'source_lang': "'en'",
        'target_lang': "'zh'",
        'model_name': "'glm-4.7-flash'",
        'usage_count': '0',
    },
    'api_cache': {'status_code': '200', 'ttl_seconds': '86400', 'usage_count': '0'},
    'weekly_reports': {'view_count': '0'},
    'publishers': {
        'is_active': 'true',
        'sync_count': '0',
        'site_crawl_enabled': 'false',
        'site_import_enabled': 'false',
        'site_display_primary': 'false',
        'fallback_google_enabled': 'true',
        'source_status': "'healthy'",
        'consecutive_failures': '0',
        'consecutive_successes': '0',
    },
    'new_books': {'is_verified': 'false', 'is_displayable': 'true'},
}
PERFORMANCE_INDEXES = {
    'idx_new_books_display_date': ('new_books', 'is_displayable, publication_date'),
    'idx_new_books_display_created': ('new_books', 'is_displayable, created_at'),
    'idx_new_books_canonical': ('new_books', 'canonical_source_url'),
    'idx_award_books_year': ('award_books', 'year'),
}


def _scripts():
    return ScriptDirectory(str(ROOT / 'migrations'))


def _engine_options(schema):
    return {
        'poolclass': NullPool,
        'echo': False,
        'hide_parameters': True,
        'connect_args': {
            'connect_timeout': 5,
            'options': f'-c search_path={schema} -c statement_timeout=120000 -c lock_timeout=10000',
        },
    }


def _make_engine(url, schema):
    return create_engine(url, **_engine_options(schema))


def _versions(connection, schema):
    if not inspect(connection).has_table('alembic_version', schema=schema):
        return ()
    return MigrationContext.configure(connection, opts={'version_table_schema': schema}).get_current_heads()


def _verify(engine, schema):
    with engine.connect() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text('SET TRANSACTION READ ONLY'))
        connection.execute(text('SELECT 1'))
        current = _versions(connection, schema)
    matches = set(current) == set(_scripts().get_heads())
    print('Database connection verified; migration head ' + ('matches.' if matches else 'is missing or differs.'))
    print('Business data completeness is not verified by this check.')
    return matches


@contextmanager
def _safe_model_imports():
    # Importing app.models executes the legacy app factory. Confine that factory
    # to SQLite testing: no dotenv, production API credentials or background jobs.
    overrides = {
        'FLASK_ENV': 'testing',
        'DATABASE_URL': 'sqlite:///:memory:',
        'PYTHON_DOTENV_DISABLED': '1',
        'DISABLE_BACKGROUND_THREADS': 'true',
        'MAIL_ENABLED': 'false',
        'MAIL_SUPPRESS_SEND': 'true',
        'NYT_API_KEY': '',
        'GOOGLE_API_KEY': '',
        'PRH_API_KEY': '',
        'ZHIPU_API_KEY': '',
        'SILICONFLOW_API_KEY': '',
        'RATE_LIMIT_REDIS_URL': '',
        'TRANSLATION_PROVIDER': 'zhipu',
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _metadata():
    with _safe_model_imports():
        from app.models.database import db

    metadata = MetaData()
    for table in db.metadata.sorted_tables:
        table.to_metadata(metadata)
    for table, defaults in SERVER_DEFAULTS.items():
        for column, value in defaults.items():
            metadata.tables[table].c[column].server_default = DefaultClause(text(value))
    return metadata


def _require_empty_schema(connection, schema):
    exists = connection.execute(text('SELECT 1 FROM pg_namespace WHERE nspname = :schema'), {'schema': schema}).scalar()
    if not exists:
        raise ValueError('Create a dedicated empty schema explicitly before bootstrap.')
    occupied = connection.execute(
        text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_depend d JOIN pg_namespace n ON n.oid=d.refobjid
            WHERE d.refclassid='pg_namespace'::regclass AND n.nspname=:schema
        )
    """),
        {'schema': schema},
    ).scalar_one()
    if occupied:
        raise ValueError('Bootstrap requires a completely empty schema, including no version table.')


def _bootstrap_extras(connection):
    for index, (table, columns) in PERFORMANCE_INDEXES.items():
        connection.execute(text(f'CREATE INDEX {index} ON {table} ({columns})'))
    # Extension/permission failure aborts the transaction and never stamps head.
    connection.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))
    extension_schema = connection.execute(
        text("""
        SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pg_trgm'
    """)
    ).scalar_one()
    opclass = connection.dialect.identifier_preparer.quote_schema(extension_schema) + '.gin_trgm_ops'
    for table in ('new_books', 'award_books'):
        expressions = ', '.join(f"lower(coalesce({column},'')) {opclass}" for column in ('title', 'title_zh', 'author'))
        connection.execute(text(f'CREATE INDEX idx_{table}_trgm_search ON {table} USING GIN ({expressions})'))


def _bootstrap(engine, schema):
    scripts = _scripts()
    if scripts.get_heads() != [BOOTSTRAP_HEAD]:
        raise ValueError('Migration head changed; review the bootstrap baseline before writing.')
    metadata = _metadata()
    with engine.begin() as connection:
        if connection.dialect.name != 'postgresql':
            raise ValueError('Bootstrap requires PostgreSQL transactional DDL.')
        locked = connection.execute(
            text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'), {'key': f'bookrank-bootstrap:{schema}'}
        ).scalar_one()
        if not locked:
            raise ValueError('Another bootstrap is running; verify its outcome before retrying.')
        _require_empty_schema(connection, schema)
        metadata.create_all(connection)
        _bootstrap_extras(connection)
        MigrationContext.configure(connection, opts={'version_table_schema': schema}).stamp(scripts, BOOTSTRAP_HEAD)
    print('Explicit empty-schema bootstrap committed; no data was seeded.')


def _upgrade(engine, schema):
    # Never infer/stamp a version for an existing schema.
    scripts = _scripts()
    with engine.connect() as connection:
        versions = _versions(connection, schema)
        if not versions:
            raise ValueError('Upgrade requires an existing, known Alembic version history.')
        for version in versions:
            try:
                revision = scripts.get_revision(version)
            except CommandError as exc:
                raise ValueError('Unknown Alembic version history.') from exc
            if revision is None:
                raise ValueError('Unknown Alembic version history.')
    from alembic import command
    from flask import Flask
    from flask_migrate import Migrate
    from flask_sqlalchemy import SQLAlchemy

    application = Flask('bookrank-explicit-upgrade')
    application.config.update(
        SQLALCHEMY_DATABASE_URI=engine.url,
        SQLALCHEMY_ENGINE_OPTIONS=_engine_options(schema),
    )
    database = SQLAlchemy(application)
    Migrate(application, database, directory=str(ROOT / 'migrations'), version_table_schema=schema)
    try:
        with application.app_context():
            configuration = application.extensions['migrate'].migrate.get_config(str(ROOT / 'migrations'))
            command.upgrade(configuration, 'heads')
    finally:
        with application.app_context():
            database.session.remove()
            database.engine.dispose()
    print('Explicit migration upgrade completed; existing version history was preserved.')


def _seed_base_data(engine, schema):
    with _safe_model_imports():
        from app.initialization import init_awards_data, init_sample_books
        from app.models.database import db
        from app.models.schemas import Award, AwardBook
        from app.services.new_book import create_new_book_modules
    from flask import Flask

    application = Flask('bookrank-explicit-seed', static_folder=str(ROOT / 'static'))
    application.config.update(
        SQLALCHEMY_DATABASE_URI=engine.url,
        SQLALCHEMY_ENGINE_OPTIONS=_engine_options(schema),
        IMAGE_CACHE_DIR=ROOT / 'cache' / 'images',
        GOOGLE_API_KEY='',
        APP_ENV='production',
    )
    db.init_app(application)
    try:
        with application.app_context():
            init_awards_data(application)
            init_sample_books(application)
            modules = create_new_book_modules()
            modules.publisher_manager.init_publishers()
            result = modules.sync_engine.ensure_static_data_seeded()
            if result is not None and result.get('success') is not True:
                raise ValueError('Static base-data seed is incomplete; inspect retained data before retrying.')
            if Award.query.count() == 0 or AwardBook.query.count() == 0:
                raise ValueError('Expected award/sample rows are missing after explicit seed.')
            print(
                'Static new-book seed: ' + ('existing displayable data retained.' if result is None else 'successful.')
            )
    finally:
        with application.app_context():
            db.session.remove()
            db.engine.dispose()
    print('Explicit base-data seed completed separately from the schema transaction.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--upgrade', action='store_true', help='Explicitly upgrade an existing versioned schema.')
    modes.add_argument(
        '--bootstrap-empty-schema', action='store_true', help='Create reviewed baseline in a dedicated empty schema.'
    )
    parser.add_argument('--schema', help='Target schema (default public for verification/upgrade).')
    parser.add_argument(
        '--seed-base-data', action='store_true', help='Explicitly seed base/sample data after a write mode succeeds.'
    )
    args = parser.parse_args(argv)
    if args.seed_base_data and not (args.upgrade or args.bootstrap_empty_schema):
        parser.error('--seed-base-data requires an explicit write mode.')
    schema = args.schema or 'public'
    if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', schema):
        parser.error('--schema must be a simple lowercase PostgreSQL identifier.')
    if args.bootstrap_empty_schema and (
        not args.schema or schema == 'public' or schema.startswith('pg_') or schema == 'information_schema'
    ):
        parser.error(
            'Bootstrap requires --schema naming a dedicated empty schema; system/public schemas are forbidden.'
        )
    engine = None
    try:
        raw_url = os.environ.get('DATABASE_URL', '')
        if raw_url.startswith('postgres://'):
            raw_url = 'postgresql://' + raw_url.removeprefix('postgres://')
        url = make_url(raw_url)
        if url.get_backend_name() != 'postgresql':
            print('DATABASE_URL must explicitly select PostgreSQL; no fallback database is used.')
            return 2
        engine = _make_engine(url, schema)
        if args.bootstrap_empty_schema:
            _bootstrap(engine, schema)
        elif args.upgrade:
            _upgrade(engine, schema)
        verified = _verify(engine, schema)
        if args.seed_base_data and verified:
            _seed_base_data(engine, schema)
        return 0 if verified else 1
    except Exception as exc:
        # Exception messages can contain DSNs, credentials, SQL or driver options.
        print(f'Database operation stopped ({type(exc).__name__}); verify state before another write attempt.')
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
