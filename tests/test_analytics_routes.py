"""Analytics 路由测试"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError


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

    @pytest.mark.parametrize(
        'path',
        [
            '/api/analytics/report-views',
            '/api/analytics/user-behavior',
            '/api/analytics/daily-stats',
            '/api/analytics/top-reports',
            '/api/analytics/session-stats',
        ],
    )
    def test_db_failure_is_500(self, client, db, path):
        def fail(conn, cursor, statement, parameters, context, executemany):
            sql = str(statement).lower()
            if 'select' in sql and ('user_behavior' in sql or 'weekly_report' in sql):
                raise SQLAlchemyError('boom')

        event.listen(db.engine, 'before_cursor_execute', fail)
        try:
            response = client.get(path)
            body = json.loads(response.data)
            assert response.status_code == 500
            assert body['success'] is False
        finally:
            event.remove(db.engine, 'before_cursor_execute', fail)
            db.session.rollback()
            db.session.expire_all()

    @pytest.mark.parametrize(
        ('path', 'expect'),
        [
            ('/api/analytics/report-views', {'total_views': 0, 'average_views': 0, 'view_stats': []}),
            ('/api/analytics/user-behavior', {'total_behaviors': 0, 'behavior_stats': []}),
            ('/api/analytics/session-stats', {'session_count': 0, 'average_behaviors_per_session': 0}),
            ('/api/analytics/top-reports', []),
            ('/api/analytics/daily-stats', 'axis'),
        ],
    )
    def test_empty_success_shapes(self, client, db, path, expect):
        response = client.get(path)
        body = json.loads(response.data)
        assert response.status_code == 200
        assert body['success'] is True
        data = body['data']
        if expect == 'axis':
            today = datetime.now(UTC).date()
            axis = [{'date': (today - timedelta(days=i)).isoformat(), 'count': 0} for i in range(29, -1, -1)]
            assert data['daily_stats'] == axis
            assert 'error' not in data
        elif expect == []:
            assert data == []
        else:
            for key, value in expect.items():
                assert data[key] == value
            assert 'error' not in data
        db.session.rollback()
