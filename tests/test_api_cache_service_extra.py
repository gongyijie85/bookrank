"""API缓存服务补充测试"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.schemas import APICache
from app.services.api_cache_service import APICacheService, get_api_cache_service


@pytest.fixture
def cache_service():
    return APICacheService()


class TestComputeHash:
    """测试 _compute_hash"""

    def test_deterministic(self):
        h1 = APICacheService._compute_hash('nyt', 'fiction')
        h2 = APICacheService._compute_hash('nyt', 'fiction')
        assert h1 == h2

    def test_different_inputs(self):
        h1 = APICacheService._compute_hash('nyt', 'fiction')
        h2 = APICacheService._compute_hash('google_books', 'fiction')
        assert h1 != h2

    def test_hash_length(self):
        h = APICacheService._compute_hash('nyt', 'test')
        assert len(h) == 64


class TestCacheGet:
    """测试 get 方法"""

    def test_cache_hit(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'fiction', {'data': 'test'}, ttl_seconds=3600)
            result = cache_service.get('nyt', 'fiction')
            assert result is not None
            assert result['data'] == 'test'

    def test_cache_miss(self, app, db, cache_service):
        with app.app_context():
            result = cache_service.get('nyt', 'nonexistent')
            assert result is None

    def test_cache_expired(self, app, db, cache_service):
        with app.app_context():
            cache = APICache(
                api_source='nyt',
                request_key='old',
                request_hash=APICacheService._compute_hash('nyt', 'old'),
                response_data='{"data":"old"}',
                status_code=200,
                ttl_seconds=1,
                expires_at=datetime.now(UTC) - timedelta(seconds=10),
                usage_count=1,
                last_used_at=datetime.now(UTC),
            )
            db.session.add(cache)
            db.session.commit()

            result = cache_service.get('nyt', 'old')
            assert result is None

    def test_cache_error_status_ignored(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'error_key', {'error': 'fail'}, is_error=True)
            result = cache_service.get('nyt', 'error_key')
            assert result is None

    def test_cache_invalid_json(self, app, db, cache_service):
        with app.app_context():
            cache = APICache(
                api_source='nyt',
                request_key='badjson',
                request_hash=APICacheService._compute_hash('nyt', 'badjson'),
                response_data='not valid json{',
                status_code=200,
                ttl_seconds=3600,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                usage_count=1,
                last_used_at=datetime.now(UTC),
            )
            db.session.add(cache)
            db.session.commit()

            result = cache_service.get('nyt', 'badjson')
            assert result is not None
            assert 'error' in result


class TestCacheSet:
    """测试 set 方法"""

    def test_set_new_cache(self, app, db, cache_service):
        with app.app_context():
            cache = cache_service.set('google_books', 'isbn123', {'title': 'Test Book'})
            assert cache is not None
            assert cache.api_source == 'google_books'
            assert cache.status_code == 200

    def test_set_error_cache(self, app, db, cache_service):
        with app.app_context():
            cache = cache_service.set('nyt', 'error', 'error msg', is_error=True, error_message='rate limited')
            assert cache.status_code == 500
            assert cache.error_message == 'rate limited'

    def test_set_updates_existing(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'dup', {'v': 1})
            cache_service.set('nyt', 'dup', {'v': 2})

            result = cache_service.get('nyt', 'dup')
            assert result['v'] == 2

    def test_set_string_data(self, app, db, cache_service):
        with app.app_context():
            cache = cache_service.set('open_library', 'key1', 'plain string data')
            assert cache is not None

    def test_set_default_ttl(self, app, db, cache_service):
        with app.app_context():
            cache = cache_service.set('nyt', 'ttl_test', {'d': 1})
            assert cache.ttl_seconds == APICacheService.DEFAULT_TTL['nyt']

    def test_set_custom_ttl(self, app, db, cache_service):
        with app.app_context():
            cache = cache_service.set('nyt', 'custom_ttl', {'d': 1}, ttl_seconds=600)
            assert cache.ttl_seconds == 600

    def test_set_unknown_source_default_ttl(self, app, db, cache_service):
        with app.app_context():
            cache = cache_service.set('unknown_api', 'key', {'d': 1})
            assert cache.ttl_seconds == 86400


class TestCacheDelete:
    """测试 delete 方法"""

    def test_delete_by_source(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'del1', {'d': 1})
            cache_service.set('google_books', 'keep1', {'d': 2})

            deleted = cache_service.delete(api_source='nyt')
            assert deleted >= 1

    def test_delete_by_age(self, app, db, cache_service):
        with app.app_context():
            old_cache = APICache(
                api_source='nyt',
                request_key='old',
                request_hash=APICacheService._compute_hash('nyt', 'old'),
                response_data='{}',
                status_code=200,
                ttl_seconds=3600,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                usage_count=1,
                last_used_at=datetime.now(UTC),
                created_at=datetime.now(UTC) - timedelta(days=30),
            )
            db.session.add(old_cache)
            db.session.commit()

            deleted = cache_service.delete(older_than_days=7)
            assert deleted >= 1

    def test_delete_all(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'a', {'d': 1})
            cache_service.set('nyt', 'b', {'d': 2})

            deleted = cache_service.delete()
            assert deleted >= 2


class TestClearExpired:
    """测试 clear_expired"""

    def test_clear_expired(self, app, db, cache_service):
        with app.app_context():
            expired = APICache(
                api_source='nyt',
                request_key='expired',
                request_hash=APICacheService._compute_hash('nyt', 'expired'),
                response_data='{}',
                status_code=200,
                ttl_seconds=1,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
                usage_count=1,
                last_used_at=datetime.now(UTC),
            )
            db.session.add(expired)
            db.session.commit()

            deleted = cache_service.clear_expired()
            assert deleted >= 1


class TestGetStats:
    """测试 get_stats"""

    def test_stats_with_data(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'stat1', {'d': 1})
            cache_service.set('google_books', 'stat2', {'d': 2})

            stats = cache_service.get_stats()
            assert stats['total_count'] >= 2
            assert 'nyt_count' in stats
            assert 'google_books_count' in stats

    def test_stats_by_source(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'stat3', {'d': 3})

            stats = cache_service.get_stats(api_source='nyt')
            assert stats['total_count'] >= 1

    def test_stats_empty(self, app, db, cache_service):
        with app.app_context():
            cache_service.delete()
            stats = cache_service.get_stats()
            assert stats['total_count'] == 0


class TestGetRecentRecords:
    """测试 get_recent_records"""

    def test_get_recent(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'recent1', {'d': 1})
            cache_service.set('nyt', 'recent2', {'d': 2})

            records = cache_service.get_recent_records(limit=5)
            assert len(records) >= 2

    def test_get_recent_by_source(self, app, db, cache_service):
        with app.app_context():
            cache_service.set('nyt', 'src1', {'d': 1})
            cache_service.set('google_books', 'src2', {'d': 2})

            records = cache_service.get_recent_records(limit=5, api_source='nyt')
            assert all(r.api_source == 'nyt' for r in records)

    def test_get_recent_error(self, app, db, cache_service):
        with app.app_context(), patch.object(APICache.query, 'order_by', side_effect=Exception('DB error')):
            records = cache_service.get_recent_records()
            assert records == []


class TestGetApiCacheService:
    """测试单例获取"""

    def test_singleton(self):
        import app.services.api_cache_service as mod

        mod._api_cache_service = None
        s1 = get_api_cache_service()
        s2 = get_api_cache_service()
        assert s1 is s2
        mod._api_cache_service = None


class TestMemoryLRUCache:
    """测试内存 LRU 缓存层（_mem_get / _mem_set / 淘汰策略）"""

    def test_mem_set_and_get(self, cache_service):
        cache_service._mem_set('key1', {'data': 'a'}, ttl_seconds=60)
        assert cache_service._mem_get('key1') == {'data': 'a'}

    def test_mem_get_missing_returns_none(self, cache_service):
        assert cache_service._mem_get('nonexistent') is None

    def test_mem_get_expired_returns_none(self, cache_service):
        # 写入立即过期的条目
        cache_service._mem_set('expired', {'data': 'x'}, ttl_seconds=-1)
        assert cache_service._mem_get('expired') is None
        # 应该被自动从缓存中移除
        assert 'expired' not in cache_service._mem_cache

    def test_mem_set_moves_to_end_on_update(self, cache_service):
        cache_service._mem_set('a', {'v': 1}, ttl_seconds=60)
        cache_service._mem_set('b', {'v': 2}, ttl_seconds=60)
        cache_service._mem_set('c', {'v': 3}, ttl_seconds=60)
        # 重新写 'a'，应当被移到末尾
        cache_service._mem_set('a', {'v': 1}, ttl_seconds=60)
        keys = list(cache_service._mem_cache.keys())
        assert keys[-1] == 'a'

    def test_mem_lru_eviction_when_over_limit(self, cache_service):
        """超出 _MEMORY_CACHE_MAX 时淘汰最旧条目"""
        import app.services.api_cache_service as mod

        # 临时调低上限以便测试
        original_max = mod._MEMORY_CACHE_MAX
        mod._MEMORY_CACHE_MAX = 3
        try:
            cache_service._mem_set('k1', 'v1', ttl_seconds=60)
            cache_service._mem_set('k2', 'v2', ttl_seconds=60)
            cache_service._mem_set('k3', 'v3', ttl_seconds=60)
            cache_service._mem_set('k4', 'v4', ttl_seconds=60)

            assert len(cache_service._mem_cache) == 3
            # k1 是最旧的，应该被淘汰
            assert 'k1' not in cache_service._mem_cache
            assert 'k4' in cache_service._mem_cache
        finally:
            mod._MEMORY_CACHE_MAX = original_max

    def test_mem_get_promotes_to_end(self, cache_service):
        """LRU: 命中应将条目移到末尾"""
        cache_service._mem_set('a', 1, ttl_seconds=60)
        cache_service._mem_set('b', 2, ttl_seconds=60)
        cache_service._mem_set('c', 3, ttl_seconds=60)
        # 访问 'a'，使其变为最近使用
        cache_service._mem_get('a')
        keys = list(cache_service._mem_cache.keys())
        assert keys[-1] == 'a'

    def test_set_writes_to_memory_cache(self, app, db, cache_service):
        """set() 应同时写通到内存缓存"""
        with app.app_context():
            cache_service.set('nyt', 'memwrite', {'foo': 'bar'})
            # 直接命中内存缓存（无需查库）
            request_hash = APICacheService._compute_hash('nyt', 'memwrite')
            cache_key = f'nyt:{request_hash}'
            assert cache_service._mem_get(cache_key) == {'foo': 'bar'}

    def test_get_uses_memory_cache_fast_path(self, app, db, cache_service):
        """命中内存 LRU 时不应触发数据库查询"""
        with app.app_context():
            cache_service.set('nyt', 'fast', {'cached': True})

            with patch.object(APICache, 'query') as mock_query:
                result = cache_service.get('nyt', 'fast')
                assert result == {'cached': True}
                # 因为命中了内存缓存，不应触发 .filter_by
                mock_query.filter_by.assert_not_called()

    def test_delete_by_source_clears_memory(self, app, db, cache_service):
        """delete(api_source=...) 应同步清理内存中该 source 的条目"""
        with app.app_context():
            cache_service.set('nyt', 'd1', {'a': 1})
            cache_service.set('google_books', 'd2', {'b': 2})

            cache_service.delete(api_source='nyt')

            # nyt 条目应被清理
            nyt_keys = [k for k in cache_service._mem_cache if k.startswith('nyt:')]
            assert nyt_keys == []
            # google_books 条目保留
            gb_keys = [k for k in cache_service._mem_cache if k.startswith('google_books:')]
            assert len(gb_keys) >= 1

    def test_delete_all_clears_memory(self, app, db, cache_service):
        """delete() 无参数应清空整个内存缓存"""
        with app.app_context():
            cache_service.set('nyt', 'all1', {'a': 1})
            cache_service.set('google_books', 'all2', {'b': 2})

            cache_service.delete()

            assert len(cache_service._mem_cache) == 0
