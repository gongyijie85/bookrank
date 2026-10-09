"""API缓存服务测试"""

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError

from app.models.schemas import APICache, Award
from app.services.api_cache_service import APICacheService


def test_api_cache_get_ignores_error_cache(db):
    """测试错误响应缓存不会作为正常API数据返回"""
    cache = APICacheService()
    cache.set(
        'nyt',
        'trade-fiction-paperback',
        {'error': 'rate_limit_exceeded'},
        ttl_seconds=300,
        is_error=True,
        error_message='rate limited',
    )

    assert cache.get('nyt', 'trade-fiction-paperback') is None


def test_get_recent_records_select_error_propagates(db):
    """SELECT api_cache 失败必须抛出 SQLAlchemyError，不能吞成 []。"""
    engine = db.engine

    def _boom(conn, cursor, statement, parameters, context, executemany):
        if 'api_cache' in statement.lower() and statement.lstrip().lower().startswith('select'):
            raise SQLAlchemyError('select api_cache failed')

    event.listen(engine, 'before_cursor_execute', _boom)
    try:
        with pytest.raises(SQLAlchemyError):
            APICacheService().get_recent_records(limit=5)
    finally:
        event.remove(engine, 'before_cursor_execute', _boom)


def test_get_recent_records_empty_returns_empty_list(db):
    """空表上的真实查询仍返回 []。"""
    assert APICacheService().get_recent_records(limit=5) == []


def test_release_session_cache_miss_returns_connection(db):
    cache = APICacheService()
    assert cache.get('google_books', 'synthetic-cold', release_session=True) is None
    assert not db.session().in_transaction()


@pytest.mark.parametrize('memory_hit', [False, True])
def test_release_session_hit_keeps_data_and_releases_connection(db, memory_hit):
    cache = APICacheService()
    payload = {'cover_url': 'https://books.google.com/synthetic-cover'}
    cache.set('google_books', 'synthetic-hit', payload)
    if not memory_hit:
        cache._mem_cache.clear()
    db.session.execute(text('SELECT 1'))
    assert db.session().in_transaction()
    assert cache.get('google_books', 'synthetic-hit', release_session=True) == payload
    assert not db.session().in_transaction()
    assert APICache.query.filter_by(request_key='synthetic-hit').count() == 1


def test_default_cache_read_preserves_callers_transaction(db):
    award = Award(name='Synthetic uncommitted award')
    db.session.add(award)
    db.session.flush()
    award_id = award.id
    award.name = 'Synthetic edited award'
    assert APICacheService().get('google_books', 'synthetic-default-miss') is None
    assert db.session().in_transaction()
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Award, award_id).name == 'Synthetic edited award'


def test_release_session_read_error_still_returns_connection(db):
    engine = db.engine

    def fail(conn, cursor, statement, parameters, context, executemany):
        if 'api_cache' in statement.lower() and statement.lstrip().lower().startswith('select'):
            raise SQLAlchemyError('synthetic cache read failure')

    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(SQLAlchemyError, match='synthetic cache read failure'):
            APICacheService().get('google_books', 'synthetic-failed-miss', release_session=True)
        assert not db.session().in_transaction()
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
