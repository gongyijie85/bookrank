"""Repeated ranking hydration must reuse application-memory translation data."""

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.models.schemas import BookMetadata, TranslationCache
from app.services.book_language_pack import BookLanguagePack
from app.services.detail_cache import DetailCache
from app.services.translation_cache_service import TranslationCacheService


@contextmanager
def _language_queries(db):
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        normalized = statement.lower()
        if normalized.lstrip().startswith('select') and any(
            f'from {table}' in normalized for table in ('book_metadata', 'translation_cache')
        ):
            statements.append(normalized)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        yield statements
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)


def _book():
    return {
        'isbn13': '9780000000001',
        'title': 'A test title',
        'description': 'A test description',
        'details': 'A test detail',
    }


def _seed(db):
    db.session.add(BookMetadata(isbn='9780000000001', title='A test title', author='Author', title_zh='元数据书名'))
    db.session.add(
        TranslationCache(
            source_hash=TranslationCacheService._compute_source_hash('A test description'),
            source_text='A test description',
            translated_text='缓存简介',
        )
    )
    db.session.commit()


def test_warm_hydration_across_instances_issues_zero_language_queries(db):
    _seed(db)
    cold = _book()
    with _language_queries(db) as cold_queries:
        BookLanguagePack().hydrate_books([cold])
    assert Counter('metadata' if 'from book_metadata' in query else 'text' for query in cold_queries) == {
        'metadata': 1,
        'text': 1,
    }

    warm = _book()
    with _language_queries(db) as warm_queries:
        BookLanguagePack().hydrate_books([warm])

    assert warm_queries == []
    assert warm == cold
    assert warm['title_zh'] == '元数据书名'
    assert warm['description_zh'] == '缓存简介'


def test_empty_language_results_are_cached(db):
    with _language_queries(db) as queries:
        BookLanguagePack().hydrate_books([_book()])
        first_queries = len(queries)
        BookLanguagePack().hydrate_books([_book()])

    assert first_queries == 2
    assert len(queries) == first_queries


def test_fully_translated_books_need_no_database_hydration(db):
    book = _book() | {'title_zh': '已有书名', 'description_zh': '已有简介', 'details_zh': '已有详情'}
    expected = deepcopy(book)

    with _language_queries(db) as queries:
        BookLanguagePack().hydrate_books([book])

    assert queries == []
    assert book == expected


def test_metadata_keys_ignore_duplicate_isbns_and_order_and_return_copies(db):
    _seed(db)
    with _language_queries(db) as queries:
        first = BookLanguagePack().get_book_metadata_translations(['9780000000002', '9780000000001', ''])
        first['9780000000001']['title_zh'] = '调用方改动'
        second = BookLanguagePack().get_book_metadata_translations(['9780000000001', '9780000000001', '9780000000002'])

    assert len(queries) == 1
    assert second['9780000000001']['title_zh'] == '元数据书名'


def test_text_keys_ignore_empty_inputs_and_order_and_return_copies(db):
    _seed(db)
    with _language_queries(db) as queries:
        first = BookLanguagePack()._get_cached_translations({'A test description', 'Other text', '', '   '})
        first['A test description'] = '调用方改动'
        second = BookLanguagePack()._get_cached_translations({'Other text', 'A test description'})

    assert len(queries) == 1
    assert second == {'A test description': '缓存简介'}
    assert 'model_name' not in queries[0]
    assert 'usage_count' not in queries[0]
    assert 'created_at' not in queries[0]


def test_distinct_text_inputs_keep_exact_match_semantics(db):
    _seed(db)
    db.session.add(
        TranslationCache(
            source_hash=TranslationCacheService._compute_source_hash(' A test description '),
            source_text=' A test description ',
            translated_text='带空格简介',
        )
    )
    db.session.commit()
    pack = BookLanguagePack()

    assert pack._get_cached_translations({'A test description'}) == {'A test description': '缓存简介'}
    assert pack._get_cached_translations({' A test description '}) == {' A test description ': '带空格简介'}


def test_hydration_preserves_existing_then_metadata_then_pack_then_text_priority(db, tmp_path):
    _seed(db)
    pack_path = tmp_path / 'language-pack.json'
    pack_path.write_text(
        json.dumps({'books': {'9780000000001': {'title_zh': '静态书名', 'description_zh': '静态简介'}}}),
        encoding='utf-8',
    )
    first = _book() | {'details_zh': '已有详情'}
    second = deepcopy(first)

    BookLanguagePack(pack_path).hydrate_books([first])
    BookLanguagePack(pack_path).hydrate_books([second])

    assert first == second
    assert first['title_zh'] == '元数据书名'
    assert first['description_zh'] == '静态简介'
    assert first['details_zh'] == '已有详情'


def test_old_schema_metadata_remains_supported(db, monkeypatch):
    _seed(db)
    pack = BookLanguagePack()
    monkeypatch.setattr(pack, '_table_columns', lambda name: {'isbn', 'title_zh'})

    assert pack.get_book_metadata_translations(['9780000000001']) == {
        '9780000000001': {'title_zh': '元数据书名', 'description_zh': None, 'details_zh': None}
    }


@pytest.mark.parametrize('kind', ['metadata', 'text'])
def test_database_errors_are_retried_instead_of_caching_empty_results(db, kind):
    _seed(db)
    table = 'book_metadata' if kind == 'metadata' else 'translation_cache'
    lookups = []

    def fail_first_read(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().lstrip().startswith('select') and f'from {table}' in statement.lower():
            lookups.append(statement)
            if len(lookups) == 1:
                raise OperationalError(statement, parameters, Exception('temporary outage'))

    def lookup():
        pack = BookLanguagePack()
        if kind == 'metadata':
            return pack.get_book_metadata_translations(['9780000000001'])
        return pack._get_cached_translations({'A test description'})

    event.listen(db.engine, 'before_cursor_execute', fail_first_read)
    try:
        assert lookup() == {}
        recovered = lookup()
        assert recovered
        assert lookup() == recovered
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_first_read)

    assert len(lookups) == 2


@pytest.mark.parametrize('kind', ['metadata', 'text'])
def test_committed_translation_changes_refresh_memory_cache(db, kind):
    _seed(db)
    pack = BookLanguagePack()
    if kind == 'metadata':
        first = pack.get_book_metadata_translations(['9780000000001'])
        record = db.session.get(BookMetadata, '9780000000001')
        record.title_zh = '更新书名'
    else:
        first = pack._get_cached_translations({'A test description'})
        record = TranslationCache.query.filter_by(source_text='A test description').one()
        record.translated_text = '更新简介'
    db.session.commit()

    if kind == 'metadata':
        refreshed = pack.get_book_metadata_translations(['9780000000001'])
        assert refreshed['9780000000001']['title_zh'] == '更新书名'
    else:
        refreshed = pack._get_cached_translations({'A test description'})
        assert refreshed == {'A test description': '更新简介'}
    assert refreshed != first


def test_cached_language_data_is_isolated_between_flask_apps(app, db):
    _seed(db)
    pack = BookLanguagePack()
    assert pack.get_book_metadata_translations(['9780000000001'])['9780000000001']['title_zh'] == '元数据书名'

    other_app = Flask(__name__)
    other_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    other_app.extensions['book_detail_cache'] = DetailCache()
    db.init_app(other_app)
    with other_app.app_context():
        db.create_all()
        try:
            db.session.add(
                BookMetadata(isbn='9780000000001', title='Other title', author='Author', title_zh='另一应用书名')
            )
            db.session.commit()
            assert pack.get_book_metadata_translations(['9780000000001'])['9780000000001']['title_zh'] == '另一应用书名'
        finally:
            db.session.remove()
            db.drop_all()

    assert pack.get_book_metadata_translations(['9780000000001'])['9780000000001']['title_zh'] == '元数据书名'


def test_missing_cache_extension_keeps_original_database_path(app, db, monkeypatch):
    _seed(db)
    monkeypatch.delitem(app.extensions, 'book_detail_cache')

    with _language_queries(db) as queries:
        first = _book()
        BookLanguagePack().hydrate_books([first])
        second = _book()
        BookLanguagePack().hydrate_books([second])

    assert first == second
    assert first['title_zh'] == '元数据书名'
    assert first['description_zh'] == '缓存简介'
    assert len(queries) == 4


def test_no_app_context_keeps_standalone_database_lookup_available(monkeypatch):
    session = Mock()
    session.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(_mapping={'isbn': '9780000000001', 'title_zh': '独立查询书名'})
    ]
    monkeypatch.setattr('app.services.book_language_pack.db', SimpleNamespace(session=session))
    pack = BookLanguagePack()
    monkeypatch.setattr(pack, '_table_columns', lambda name: {'isbn', 'title_zh'})

    assert pack.get_book_metadata_translations(['9780000000001'])['9780000000001']['title_zh'] == '独立查询书名'

    session.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(
            source_hash=TranslationCacheService._compute_source_hash('Standalone text'),
            source_text='Standalone text',
            translated_text='独立查询译文',
        )
    ]
    assert pack._get_cached_translations({'Standalone text'}) == {'Standalone text': '独立查询译文'}


@pytest.mark.parametrize('kind', ['metadata', 'text'])
def test_concurrent_language_lookups_share_one_database_read(app, db, kind):
    _seed(db)
    table = 'book_metadata' if kind == 'metadata' else 'translation_cache'
    reads = []
    ready = Barrier(4)
    started = Event()
    release = Event()

    def pause_read(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().lstrip().startswith('select') and f'from {table}' in statement.lower():
            reads.append(statement)
            started.set()
            assert release.wait(5)

    def lookup():
        with app.app_context():
            ready.wait(5)
            pack = BookLanguagePack()
            if kind == 'metadata':
                return pack.get_book_metadata_translations(['9780000000001'])
            return pack._get_cached_translations({'A test description'})

    event.listen(db.engine, 'before_cursor_execute', pause_read)
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(lookup) for _ in range(4)]
            try:
                assert started.wait(5)
            finally:
                release.set()
            results = [future.result(timeout=5) for future in futures]
    finally:
        event.remove(db.engine, 'before_cursor_execute', pause_read)

    assert len(reads) == 1
    assert results[0]
    assert all(result == results[0] for result in results)


@pytest.mark.parametrize('kind', ['metadata', 'text'])
@pytest.mark.parametrize('flushed', [False, True])
@pytest.mark.parametrize('warm', [False, True])
def test_uncommitted_translations_are_visible_only_in_their_transaction(db, kind, flushed, warm):
    _seed(db)
    pack = BookLanguagePack()
    if kind == 'metadata':
        # SQLite StaticPool 的 schema inspection 共用连接；在事务前探测表结构。
        pack._table_columns('book_metadata')

    def lookup():
        if kind == 'metadata':
            return pack.get_book_metadata_translations(['9780000000001'])['9780000000001']['title_zh']
        return pack._get_cached_translations({'A test description'})['A test description']

    committed = '元数据书名' if kind == 'metadata' else '缓存简介'
    if warm:
        assert lookup() == committed
    if kind == 'metadata':
        record = db.session.get(BookMetadata, '9780000000001')
        record.title_zh = '未提交译文'
    else:
        record = TranslationCache.query.filter_by(source_text='A test description').one()
        record.translated_text = '未提交译文'
    if flushed:
        db.session.flush()

    assert lookup() == '未提交译文'
    db.session.rollback()

    assert lookup() == committed
