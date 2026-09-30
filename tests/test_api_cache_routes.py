"""API 缓存路由测试"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app.services.api_cache_service import APICacheService


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


@pytest.mark.parametrize(
    ('path', 'mode'),
    [
        ('/api/cache/recent', 'fail'),
        ('/api/cache/stats', 'fail'),
        ('/api/cache/recent', 'empty'),
        ('/api/cache/stats', 'empty'),
        ('/api/cache/recent', 'unauth'),
        ('/api/cache/stats', 'unauth'),
    ],
)
def test_cache_recent_and_stats_strict(path, mode, db, app, monkeypatch):
    """真实引擎 SELECT 失败为 500；空表成功；未认证严格 403。"""
    monkeypatch.setattr('app.routes.api.cache.get_api_cache_service', lambda: APICacheService())
    engine = db.engine

    def _boom(conn, cursor, statement, parameters, context, executemany):
        if 'api_cache' in statement.lower() and statement.lstrip().lower().startswith('select'):
            raise SQLAlchemyError('select api_cache failed')

    if mode == 'fail':
        event.listen(engine, 'before_cursor_execute', _boom)
    try:
        headers = {} if mode == 'unauth' else {'X-Admin-Secret': 'test-admin-secret'}
        response = app.test_client().get(path, headers=headers)
        body = response.get_json()
        if mode == 'unauth':
            assert response.status_code == 403
        elif mode == 'fail':
            assert response.status_code == 500
            assert body['success'] is False
        else:
            assert response.status_code == 200
            assert body['success'] is True
            data = body['data']
            if path.endswith('recent'):
                assert data == {'records': [], 'count': 0}
            else:
                assert any(type(v) is int for v in data.values())
                assert all(v == 0 for v in data.values() if type(v) is int)
                assert data == APICacheService().get_stats()
    finally:
        if mode == 'fail':
            event.remove(engine, 'before_cursor_execute', _boom)
