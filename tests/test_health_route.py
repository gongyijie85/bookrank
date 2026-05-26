"""健康检查路由测试"""

import json
from unittest.mock import MagicMock, patch


class TestHealthCheck:
    """测试 /health 端点"""

    def test_health_check_returns_200(self, client):
        response = client.get('/health')
        assert response.status_code == 200

    def test_health_check_returns_json(self, client):
        response = client.get('/health')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['status'] == 'healthy'
        assert data['service'] == 'book-rank-api'

    def test_health_check_no_cache_headers(self, client):
        response = client.get('/health')
        assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'
        assert response.headers.get('Pragma') == 'no-cache'
        assert response.headers.get('Expires') == '0'

    def test_health_check_content_type(self, client):
        response = client.get('/health')
        assert 'application/json' in response.headers.get('Content-Type', '')


class TestDetailedHealthCheck:
    """测试 /health/detailed 端点"""

    def test_detailed_returns_200(self, client):
        response = client.get('/health/detailed')
        assert response.status_code == 200

    def test_detailed_returns_json(self, client):
        response = client.get('/health/detailed')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['status'] == 'healthy'
        assert 'checks' in data
        assert data['checks']['app_running'] is True

    def test_detailed_no_cache_headers(self, client):
        response = client.get('/health/detailed')
        assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'


class TestReadinessCheck:
    """测试 /health/ready 端点"""

    def test_ready_returns_200(self, app, db, client):
        with app.app_context():
            response = client.get('/health/ready')
            assert response.status_code == 200

    def test_ready_returns_json(self, app, db, client):
        with app.app_context():
            response = client.get('/health/ready')
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['status'] == 'ready'

    def test_ready_db_operational_error(self, app, client):
        from sqlalchemy.exc import OperationalError

        mock_db = MagicMock()
        mock_db.session.execute.side_effect = OperationalError('stmt', 'params', 'orig')
        mock_db.text = MagicMock()

        with app.app_context(), patch('app.models.database.db', mock_db):
            response = client.get('/health/ready')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'warning' in data

    def test_ready_generic_exception(self, app, client):
        mock_db = MagicMock()
        mock_db.session.execute.side_effect = RuntimeError('unexpected')
        mock_db.text = MagicMock()

        with app.app_context(), patch('app.models.database.db', mock_db):
            response = client.get('/health/ready')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'warning' in data
