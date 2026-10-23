"""Ranking cache misses share one origin load, including failure outcomes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from app.models.book import Book
from app.models.schemas import BookMetadata
from app.services.book_service import BookService
from app.services.cache_service import CacheService, FileCache, MemoryCache
from app.utils.exceptions import APIException


@pytest.mark.parametrize('failed', [False, True])
def test_concurrent_category_misses_share_origin(tmp_path, monkeypatch, failed):
    cache = CacheService(MemoryCache(), FileCache(tmp_path))
    nyt = Mock()
    service = BookService(nyt, Mock(), cache, Mock())
    entered = Event()
    release = Event()
    ready = Barrier(5)
    calls = []
    waiters_ready = Event()
    waiting = []
    original_wait = Event.wait

    def wait(event, timeout=None):
        flights = getattr(service, '_category_loads', None)
        if flights is not None and any(event is flight.done for flight in list(flights._flights.values())):
            waiting.append(True)
            if len(waiting) == 3:
                waiters_ready.set()
        return original_wait(event, timeout)

    monkeypatch.setattr(Event, 'wait', wait)

    def fetch(*args, **kwargs):
        calls.append(args)
        if len(calls) == 4:
            waiters_ready.set()
        entered.set()
        assert release.wait(5)
        if failed:
            raise APIException('origin timeout')
        return {'results': {}}

    nyt.fetch_books.side_effect = fetch
    book = Book.from_api_response({'title': 'Book', 'author': 'Author'}, 'fiction', 'Fiction', 'List', '2026-10-21', {})
    monkeypatch.setattr(service, '_process_api_response', lambda *args: [book])

    def load():
        ready.wait(5)
        return service.get_books_by_category('fiction', auto_translate=False, notify_refresh=False)

    # The caller barrier plus blocking origin gives all workers a shared cold window.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(load) for _ in range(4)]
        ready.wait(5)
        try:
            assert entered.wait(5)
            assert waiters_ready.wait(5)
        finally:
            release.set()
        results = [future.result(timeout=5) for future in futures]

    assert len(calls) == 1
    assert all(result == results[0] for result in results)
    if failed:
        assert results == [[], [], [], []]
        assert cache.get('books_fiction') is None
        service.get_books_by_category('fiction', auto_translate=False, notify_refresh=False)
        assert len(calls) == 2
    else:
        results[0][0].title = 'Caller mutation'
        assert results[1][0].title == 'Book'


def test_warm_ranking_snapshot_issues_no_translation_queries(app, db, tmp_path):
    book = Book.from_api_response(
        {'title': 'Ranking title', 'author': 'Author', 'primary_isbn13': '9780143127550'},
        'fiction',
        'Fiction',
        'List',
        '2026-10-21',
        {},
    )
    db.session.add(BookMetadata(isbn=book.isbn13, title=book.title, author=book.author, title_zh='缓存译文'))
    db.session.commit()
    cache = CacheService(MemoryCache(), FileCache(tmp_path))
    cache.set('books_fiction', [book.to_dict()])
    nyt = Mock()
    service = BookService(nyt, Mock(), cache, Mock(), app=app)
    queries = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        normalized = statement.lower()
        if normalized.lstrip().startswith('select') and any(
            f'from {table}' in normalized for table in ('book_metadata', 'translation_cache')
        ):
            queries.append(normalized)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        first = service.get_books_by_category('fiction')
        cold_count = len(queries)
        second = service.get_books_by_category('fiction')
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)
    assert cold_count > 0
    assert len(queries) == cold_count
    assert first[0].title_zh == second[0].title_zh == '缓存译文'
    nyt.fetch_books.assert_not_called()


def test_uncommitted_translation_is_not_published_in_ranking_cache(app, db, tmp_path, monkeypatch):
    book = Book.from_api_response(
        {'title': 'Book', 'author': 'Author', 'primary_isbn13': '9780143127550'},
        'fiction',
        'Fiction',
        'List',
        '2026-10-21',
        {},
    )
    book.title_zh = '未提交的译文'
    db.session.add(BookMetadata(isbn=book.isbn13, title=book.title, author=book.author, title_zh=book.title_zh))
    cache = CacheService(MemoryCache(), FileCache(tmp_path))
    service = BookService(Mock(), Mock(), cache, Mock(), app=app)
    monkeypatch.setattr(service, '_process_api_response', lambda *args: [book])
    result = service.get_books_by_category('fiction', auto_translate=False, notify_refresh=False)
    assert result[0].title_zh == '未提交的译文'
    assert cache.get('books_fiction') is None
    db.session.rollback()
