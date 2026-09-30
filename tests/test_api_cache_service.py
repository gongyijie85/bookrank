"""API缓存服务测试"""

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

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
