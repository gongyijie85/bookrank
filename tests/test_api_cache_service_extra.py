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
