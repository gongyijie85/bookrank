"""Translate missing book content and persist it into the static zh language pack."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _book_key(book: dict[str, Any]) -> str:
    return str(book.get('isbn13') or book.get('isbn10') or book.get('id') or '').strip()


def _merge_book(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        'id',
        'title',
        'title_zh',
        'author',
        'description',
        'description_zh',
        'details',
        'details_zh',
        'isbn13',
        'isbn10',
    ):
        if not target.get(key) and source.get(key):
            target[key] = source[key]


def _collect_cache_books(cache_dir: Path) -> list[dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for path in cache_dir.glob('*.json'):
        try:
            raw = _load_json(path)
        except Exception:
            continue

        value = raw.get('value') if isinstance(raw, dict) and 'value' in raw else raw
        if not isinstance(value, list):
            continue

        for item in value:
            if not isinstance(item, dict):
                continue
            key = _book_key(item)
            if not key:
                continue
            books.setdefault(key, {})
            _merge_book(books[key], item)
    return list(books.values())


def _collect_static_new_books(static_data_dir: Path) -> list[dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for path in static_data_dir.glob('*_books.json'):
        if path.name == 'all_books.json':
            continue
        try:
            raw = _load_json(path)
        except Exception:
            continue

        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = _book_key(item)
            if not key:
                continue
            books.setdefault(key, {})
            _merge_book(books[key], item)
    return list(books.values())


def _collect_db_new_books() -> list[dict[str, Any]]:
    try:
        from app.models.new_book import NewBook

        return [book.to_dict() for book in NewBook.query.all()]
    except Exception:
        return []


def _missing_field_count(language_pack, books: list[dict[str, Any]]) -> dict[str, int]:
    language_pack.hydrate_books(books)
    counts = {'title_zh': 0, 'description_zh': 0, 'details_zh': 0}
    for book in books:
        if book.get('title') and not language_pack._is_placeholder(str(book.get('title'))) and not book.get('title_zh'):
            counts['title_zh'] += 1
        if (
            book.get('description')
            and not language_pack._is_placeholder(str(book.get('description')))
            and not book.get('description_zh')
        ):
            counts['description_zh'] += 1
        if (
            book.get('details')
            and not language_pack._is_placeholder(str(book.get('details')))
            and not book.get('details_zh')
        ):
            counts['details_zh'] += 1
    return counts


def _database_url_is_sqlite() -> bool:
    db_url = os.environ.get('DATABASE_URL', f'sqlite:///{ROOT / "bestsellers.db"}')
    return db_url.startswith('sqlite')


def main() -> int:
    parser = argparse.ArgumentParser(description='Sync missing Chinese book translations into the language pack.')
    parser.add_argument('--pack', default='static/data/book_language_pack.zh.json', help='Language pack JSON path')
    parser.add_argument('--cache-dir', default='cache', help='Book cache directory')
    parser.add_argument('--static-data-dir', default='static/data', help='Static data directory')
    parser.add_argument(
        '--skip-static-new-books', action='store_true', help='Do not translate static new-book JSON files'
    )
    parser.add_argument('--skip-db-new-books', action='store_true', help='Do not translate new_books rows from the DB')
    parser.add_argument('--limit', type=int, default=0, help='Limit translated books for debugging')
    args = parser.parse_args()

    load_dotenv(ROOT / '.env')
    os.environ.setdefault('DISABLE_BACKGROUND_THREADS', 'true')
    os.environ['SQLALCHEMY_ECHO'] = 'false'
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').disabled = True

    from app import create_app
    from app.config import Config, ProductionConfig
    from app.services.book_language_pack import BookLanguagePack
    from app.services.zhipu_translation_service import get_translation_service

    if _database_url_is_sqlite():
        ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS = Config.SQLALCHEMY_ENGINE_OPTIONS
        ProductionConfig.SECRET_KEY = ProductionConfig.SECRET_KEY or Config.SECRET_KEY

    app = create_app('production')
    app.config['SQLALCHEMY_ECHO'] = False
    pack_path = (ROOT / args.pack).resolve()
    cache_dir = (ROOT / args.cache_dir).resolve()
    static_data_dir = (ROOT / args.static_data_dir).resolve()

    with app.app_context():
        books_by_key: dict[str, dict[str, Any]] = {}
        for book in _collect_cache_books(cache_dir):
            books_by_key.setdefault(_book_key(book), {})
            _merge_book(books_by_key[_book_key(book)], book)

        if not args.skip_static_new_books:
            for book in _collect_static_new_books(static_data_dir):
                books_by_key.setdefault(_book_key(book), {})
                _merge_book(books_by_key[_book_key(book)], book)

        if not args.skip_db_new_books:
            for book in _collect_db_new_books():
                books_by_key.setdefault(_book_key(book), {})
                _merge_book(books_by_key[_book_key(book)], book)

        books = [book for book in books_by_key.values() if _book_key(book)]
        if args.limit > 0:
            books = books[: args.limit]

        language_pack = BookLanguagePack(pack_path)
        before = _missing_field_count(language_pack, books)
        translator = get_translation_service(app=app)
        stats = language_pack.translate_and_store_books(books, translator=translator)
        after = _missing_field_count(language_pack, books)

    print(f'books_seen={stats["books_seen"]}')
    print(f'before_missing={before}')
    print(f'translated_fields={stats["fields_translated"]}')
    print(f'stored_existing_fields={stats["fields_stored"]}')
    print(f'failures={stats["failures"]}')
    print(f'pack_writes={stats["pack_writes"]}')
    print(f'after_missing={after}')
    return 0 if stats['failures'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
