"""API缓存服务测试"""

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
