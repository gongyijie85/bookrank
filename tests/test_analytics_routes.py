"""Analytics 路由测试"""

import json


class TestAnalyticsRoutes:
    """测试 /api/analytics/* 端点"""

    def test_get_report_views(self, client):
        response = client.get('/api/analytics/report-views')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_get_report_views_with_days(self, client):
        response = client.get('/api/analytics/report-views?days=7')
        assert response.status_code == 200

    def test_get_report_views_days_clamped(self, client):
        response = client.get('/api/analytics/report-views?days=999')
        assert response.status_code == 200

    def test_get_user_behavior(self, client):
        response = client.get('/api/analytics/user-behavior')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_get_user_behavior_with_days(self, client):
        response = client.get('/api/analytics/user-behavior?days=60')
        assert response.status_code == 200

    def test_get_daily_stats(self, client):
        response = client.get('/api/analytics/daily-stats')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_get_top_reports(self, client):
        response = client.get('/api/analytics/top-reports')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_get_top_reports_with_limit(self, client):
        response = client.get('/api/analytics/top-reports?limit=5')
        assert response.status_code == 200

    def test_get_top_reports_limit_clamped(self, client):
        response = client.get('/api/analytics/top-reports?limit=100')
        assert response.status_code == 200

    def test_get_session_stats(self, client):
        response = client.get('/api/analytics/session-stats')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_get_session_stats_with_days(self, client):
        response = client.get('/api/analytics/session-stats?days=14')
        assert response.status_code == 200
