"""公开分类和统计应跨请求复用纯数据，不共享 ORM 或未提交事务。"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import event, update
from sqlalchemy.exc import OperationalError

from app.models.new_book import NewBook, Publisher
from app.services.new_book.publisher_manager import PublisherManager
from app.services.new_book.query_service import NewBookQueryService
from app.services.public_metadata_cache import cached_public_metadata


@contextmanager
def _selects(db):
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        yield statements
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)


def _read(kind):
    if kind == 'counts':
        return PublisherManager().get_publisher_book_counts()
    query = NewBookQueryService(Mock())
    return query.get_categories() if kind == 'categories' else query.get_statistics()


def _seed(db):
    publisher = Publisher(name='测试出版社', name_en='Test Publisher', crawler_class='TestCrawler', is_active=True)
    db.session.add(publisher)
    db.session.flush()
    book = NewBook(
        publisher_id=publisher.id,
        title='Test Book',
        author='Author',
        category='Fiction',
        publication_date=datetime.now(UTC).date(),
        is_displayable=True,
    )
    db.session.add(book)
    db.session.flush()
    identifiers = publisher.id, book.id
    db.session.commit()
    db.session.remove()
    return identifiers


@pytest.mark.parametrize(('kind', 'cold_count'), [('categories', 1), ('statistics', 3), ('counts', 1)])
def test_public_metadata_reuses_values_across_service_instances(db, kind, cold_count):
    _seed(db)
    with _selects(db) as cold:
        expected = _read(kind)
    db.session.remove()
    with _selects(db) as warm:
        actual = _read(kind)

    assert len(cold) == cold_count
    assert warm == []
    assert actual == expected


@pytest.mark.parametrize('kind', ['categories', 'statistics', 'counts'])
def test_public_metadata_returns_independent_mutable_values(db, kind):
    _seed(db)
    first = _read(kind)
    expected = _read(kind)
    if kind == 'categories':
        first[0]['count'] = 999
        first.append({'name': 'Injected', 'count': 999})
    elif kind == 'statistics':
        first['top_categories'][0]['count'] = 999
        first['total_books'] = 999
    else:
        first.clear()

    assert _read(kind) == expected


@pytest.mark.parametrize(('kind', 'cold_count'), [('categories', 1), ('statistics', 3), ('counts', 1)])
def test_public_metadata_caches_empty_successes(db, kind, cold_count):
    with _selects(db) as statements:
        empty = _read(kind)
        assert len(statements) == cold_count
        assert _read(kind) == empty
        assert len(statements) == cold_count
    if kind == 'statistics':
        assert empty['total_books'] == 0
    else:
        assert not empty


@pytest.mark.parametrize('kind', ['categories', 'statistics', 'counts'])
def test_public_metadata_retries_database_errors(db, kind):
    _seed(db)

    def fail(connection, cursor, statement, parameters, context, executemany):
        raise OperationalError(statement, parameters, RuntimeError('temporary read failure'))

    event.listen(db.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(OperationalError):
            _read(kind)
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail)

    assert _read(kind)


@pytest.mark.parametrize('kind', ['categories', 'statistics', 'counts'])
@pytest.mark.parametrize('operation', ['unflushed', 'flushed', 'bulk'])
@pytest.mark.parametrize('warm', [False, True])
def test_uncommitted_metadata_reads_see_changes_without_polluting_cache(db, kind, operation, warm):
    _, book_id = _seed(db)
    committed = _read(kind)
    if not warm:
        from flask import current_app

        current_app.extensions['book_detail_cache'].clear()
    if operation == 'bulk':
        db.session.execute(update(NewBook).values(is_displayable=False))
    else:
        book = db.session.get(NewBook, book_id)
        book.is_displayable = False
        if operation == 'flushed':
            db.session.flush()

    assert _read(kind) != committed
    db.session.rollback()
    assert _read(kind) == committed


@pytest.mark.parametrize(('kind', 'cold_count'), [('categories', 1), ('statistics', 3), ('counts', 1)])
@pytest.mark.parametrize('operation', ['orm', 'bulk'])
def test_new_book_commit_expires_public_metadata(db, kind, cold_count, operation):
    _, book_id = _seed(db)
    before = _read(kind)
    if operation == 'bulk':
        db.session.execute(update(NewBook).values(is_displayable=False))
    else:
        db.session.get(NewBook, book_id).is_displayable = False
    db.session.commit()

    with _selects(db) as statements:
        assert _read(kind) != before
    assert len(statements) == cold_count


@pytest.mark.parametrize(('kind', 'cold_count'), [('categories', 1), ('statistics', 3), ('counts', 1)])
@pytest.mark.parametrize('operation', ['orm', 'bulk'])
def test_publisher_commit_expires_public_metadata(db, kind, cold_count, operation):
    publisher_id, _ = _seed(db)
    _read(kind)
    if operation == 'bulk':
        db.session.execute(update(Publisher).values(is_active=False))
    else:
        db.session.get(Publisher, publisher_id).is_active = False
    db.session.commit()

    with _selects(db) as statements:
        _read(kind)
    assert len(statements) == cold_count
    if kind == 'statistics':
        assert _read(kind)['active_publishers'] == 0


@pytest.mark.parametrize('kind', ['categories', 'statistics', 'counts'])
def test_savepoint_rollback_keeps_committed_metadata(db, kind):
    _, book_id = _seed(db)
    committed = _read(kind)
    nested = db.session.begin_nested()
    db.session.get(NewBook, book_id).is_displayable = False
    db.session.flush()
    assert _read(kind) != committed
    nested.rollback()
    db.session.commit()

    with _selects(db) as statements:
        assert _read(kind) == committed
    assert statements == []


@pytest.mark.parametrize('kind', ['categories', 'statistics', 'counts'])
def test_nested_commit_then_outer_rollback_keeps_committed_metadata(db, kind):
    _, book_id = _seed(db)
    committed = _read(kind)
    # SQLite must have a database transaction before SAVEPOINT, rather than
    # treating its release as a top-level commit.
    db.session.connection().exec_driver_sql('BEGIN')
    nested = db.session.begin_nested()
    db.session.get(NewBook, book_id).is_displayable = False
    db.session.flush()
    nested.commit()
    assert _read(kind) != committed
    db.session.rollback()

    with _selects(db) as statements:
        assert _read(kind) == committed
    assert statements == []


@pytest.mark.parametrize(('kind', 'cold_count'), [('categories', 1), ('statistics', 3), ('counts', 1)])
def test_missing_cache_extension_preserves_direct_query_contract(app, db, kind, cold_count):
    _seed(db)
    cache = app.extensions.pop('book_detail_cache')
    try:
        with _selects(db) as statements:
            expected = _read(kind)
            assert _read(kind) == expected
        assert len(statements) == 2 * cold_count
    finally:
        app.extensions['book_detail_cache'] = cache


def test_public_metadata_helper_without_application_context():
    loader = Mock(return_value={'count': 1})
    assert cached_public_metadata(('test', None), loader) == {'count': 1}
    assert loader.call_count == 1


def test_public_metadata_cache_is_app_specific(app, db):
    _seed(db)
    assert _read('counts')
    other = Flask('isolated-public-metadata')
    other.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    from app.services.detail_cache import DetailCache

    db.init_app(other)
    other.extensions['book_detail_cache'] = DetailCache()
    with other.app_context():
        db.create_all()
        assert _read('counts') == {}
    assert _read('counts')


def test_statistics_refreshes_at_utc_day_boundary(db, monkeypatch):
    _, book_id = _seed(db)
    today = datetime.now(UTC)
    db.session.get(NewBook, book_id).publication_date = today.date() - timedelta(days=7)
    db.session.commit()

    class Clock:
        current = today

        @classmethod
        def now(cls, tz):
            assert tz is UTC
            return cls.current

    monkeypatch.setattr('app.services.new_book.query_service.datetime', Clock)
    assert _read('statistics')['recent_books_7d'] == 1
    Clock.current += timedelta(days=1)
    with _selects(db) as statements:
        assert _read('statistics')['recent_books_7d'] == 0
    assert len(statements) == 3
