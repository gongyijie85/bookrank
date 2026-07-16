"""Initialize or verify an external PostgreSQL database.

Use this for a fresh Supabase/Postgres database before pointing production
traffic at it. The app's historical first Alembic migration assumes tables
already exist, so this script reuses the runtime migration guard that can
create the current model schema and stamp Alembic safely.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault('DISABLE_BACKGROUND_THREADS', 'true')
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('SECRET_KEY', 'local-db-init-only-not-for-runtime')

from run import _run_migrations, app, db


def _database_url_is_external_postgres() -> bool:
    db_url = os.environ.get('DATABASE_URL', '').lower()
    return db_url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg2://'))


def _count_rows() -> dict[str, int | str]:
    from app.models.new_book import NewBook, Publisher
    from app.models.schemas import Award, AwardBook, BookMetadata, TranslationCache, WeeklyReport

    models = {
        'awards': Award,
        'award_books': AwardBook,
        'book_metadata': BookMetadata,
        'new_books': NewBook,
        'publishers': Publisher,
        'translation_cache': TranslationCache,
        'weekly_reports': WeeklyReport,
    }

    counts: dict[str, int | str] = {}
    for name, model in models.items():
        try:
            counts[name] = model.query.count()
        except Exception as exc:
            counts[name] = f'error: {exc}'
            db.session.rollback()
    return counts


def _seed_base_data() -> None:
    from app.initialization import init_awards_data, init_sample_books
    from app.services.new_book_service import NewBookService

    init_awards_data(app)
    init_sample_books(app)

    service = NewBookService()
    service.init_publishers()
    service.ensure_static_data_seeded()


def main() -> int:
    parser = argparse.ArgumentParser(description='Initialize or verify an external BookRank PostgreSQL database.')
    parser.add_argument(
        '--seed-base-data',
        action='store_true',
        help='Seed awards, sample ranking data, publishers, and static new-book fallback data.',
    )
    args = parser.parse_args()

    if not _database_url_is_external_postgres():
        print('DATABASE_URL must point to an external PostgreSQL database.')
        print('Refusing to initialize the local SQLite fallback.')
        return 2

    with app.app_context():
        print(f'Target database: {db.engine.url.render_as_string(hide_password=True)}')

        if not _run_migrations():
            print('Database migration/bootstrap failed.')
            return 1

        if args.seed_base_data:
            _seed_base_data()

        print('Database is ready. Row counts:')
        for table, count in _count_rows().items():
            print(f'  {table}: {count}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
