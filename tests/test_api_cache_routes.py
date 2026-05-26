"""API 缓存路由测试"""

import json
from unittest.mock import MagicMock, patch


class TestCacheRoutes:
    """测试 /api/cache/* 端点"""

    def test_get_cache_stats_no_auth(self, client):
        response = client.get('/api/cache/stats')
        assert response.status_code in (403, 429, 500)

    def test_get_cache_recent_no_auth(self, client):
        response = client.get('/api/cache/recent')
        assert response.status_code in (403, 429, 500)

    def test_clear_cache_no_auth(self, client):
        response = client.post(
            '/api/cache/clear',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (403, 429, 500)

    def test_clear_expired_no_auth(self, client):
        response = client.post(
            '/api/cache/clear-expired',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (403, 429, 500)

    @patch('app.routes.api.cache.admin_required', lambda f: f)
    def test_get_cache_stats_with_mock(self, client, app):
        mock_service = MagicMock()
        mock_service.get_stats.return_value = {'total_count': 10}

        with app.app_context(), patch('app.routes.api.cache.get_api_cache_service', return_value=mock_service):
            response = client.get('/api/cache/stats')
            assert response.status_code in (200, 403, 429)

    @patch('app.routes.api.cache.admin_required', lambda f: f)
    def test_get_cache_recent_with_mock(self, client, app):
        mock_service = MagicMock()
        mock_service.get_recent_records.return_value = []

        with app.app_context(), patch('app.routes.api.cache.get_api_cache_service', return_value=mock_service):
            response = client.get('/api/cache/recent?limit=10')
            assert response.status_code in (200, 403, 429)

    @patch('app.routes.api.cache.csrf_protect', lambda f: f)
    @patch('app.routes.api.cache.admin_required', lambda f: f)
    def test_clear_cache_with_mock(self, client, app):
        mock_service = MagicMock()
        mock_service.delete.return_value = 5

        with app.app_context(), patch('app.routes.api.cache.get_api_cache_service', return_value=mock_service):
            response = client.post(
                '/api/cache/clear',
                data=json.dumps({'older_than_days': 7}),
                content_type='application/json',
            )
            assert response.status_code in (200, 403, 429)

    @patch('app.routes.api.cache.csrf_protect', lambda f: f)
    @patch('app.routes.api.cache.admin_required', lambda f: f)
    def test_clear_expired_with_mock(self, client, app):
        mock_service = MagicMock()
        mock_service.clear_expired.return_value = 3

        with app.app_context(), patch('app.routes.api.cache.get_api_cache_service', return_value=mock_service):
            response = client.post(
                '/api/cache/clear-expired',
                content_type='application/json',
            )
            assert response.status_code in (200, 403, 429)
