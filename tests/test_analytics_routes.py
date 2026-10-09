"""Analytics 路由测试"""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

analytics_routes = import_module('app.routes.analytics_bp')


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

    @pytest.mark.parametrize(
        ('title', 'english_title'),
        [
            ('纽约时报畅销书周报', 'NYT Weekly Bestseller Report'),
            (
                '2026年09月28日-2026年10月04日 畅销书周报',
                '2026-09-28–2026-10-04 Weekly Bestseller Report',
            ),
        ],
    )
    @pytest.mark.parametrize('locale', ['en', 'zh'])
    def test_top_reports_localizes_standard_display_title(self, client, monkeypatch, title, english_title, locale):
        rows = [{'id': 7, 'date': '2026-10-04', 'title': title, 'view_count': 23}]
        original = deepcopy(rows)
        monkeypatch.setattr(analytics_routes, 'fetch_top_reports', lambda limit: rows)

        response = client.get(f'/api/analytics/top-reports?lang={locale}')

        assert response.status_code == 200
        assert response.get_json() == {
            'success': True,
            'message': 'Success',
            'data': [{**original[0], 'title_display': english_title if locale == 'en' else title}],
        }
        assert rows == original

    @pytest.mark.parametrize('locale', ['en', 'zh'])
    def test_top_reports_preserves_custom_and_html_titles(self, client, monkeypatch, locale):
        titles = [
            '书店专刊：纽约时报畅销书周报访谈',
            'Independent editorial report',
            '<script>alert("title")</script><img src=x onerror="alert(1)">',
        ]
        rows = [{'date': '2026-10-04', 'title': title, 'view_count': 9} for title in titles]
        original = deepcopy(rows)
        monkeypatch.setattr(analytics_routes, 'fetch_top_reports', lambda limit: rows)

        response = client.get(f'/api/analytics/top-reports?lang={locale}')

        assert response.status_code == 200
        body = response.get_json()
        assert body['success'] is True
        assert body['data'] == [{**row, 'title_display': row['title']} for row in original]
        assert rows == original

    def test_top_reports_shared_rows_do_not_leak_display_locale(self, client, monkeypatch):
        rows = [
            {
                'id': 12,
                'date': '2026-10-04',
                'title': '纽约时报畅销书周报',
                'view_count': 5,
                'metadata': {'source': 'unchanged'},
            }
        ]
        original = deepcopy(rows)
        monkeypatch.setattr(analytics_routes, 'fetch_top_reports', lambda limit: rows)

        english = client.get('/api/analytics/top-reports?lang=en').get_json()
        assert english['data'][0]['title_display'] == 'NYT Weekly Bestseller Report'
        assert rows == original
        chinese = client.get('/api/analytics/top-reports?lang=zh').get_json()
        assert chinese['data'][0]['title_display'] == '纽约时报畅销书周报'
        assert rows == original
        assert english['data'][0]['title'] == chinese['data'][0]['title'] == original[0]['title']
        assert {key: value for key, value in english['data'][0].items() if key != 'title_display'} == original[0]

    @pytest.mark.parametrize(
        ('failure', 'status', 'message'),
        [
            (SQLAlchemyError('query unavailable'), 500, '服务器内部错误，请稍后重试'),
            (ValueError('invalid report query'), 400, 'invalid report query'),
        ],
    )
    def test_top_reports_display_keeps_error_response(self, client, monkeypatch, failure, status, message):
        def fail(limit):
            raise failure

        monkeypatch.setattr(analytics_routes, 'fetch_top_reports', fail)

        response = client.get('/api/analytics/top-reports?lang=en')

        assert response.status_code == status
        assert response.get_json() == {'success': False, 'message': message}

    @pytest.mark.parametrize(('requested', 'expected'), [('0', 1), ('100', 50), ('invalid', 10)])
    def test_top_reports_display_preserves_limit_and_empty_shape(self, client, monkeypatch, requested, expected):
        limits = []

        def fetch(limit):
            limits.append(limit)
            return []

        monkeypatch.setattr(analytics_routes, 'fetch_top_reports', fetch)

        response = client.get(f'/api/analytics/top-reports?limit={requested}&lang=en')

        assert limits == [expected]
        assert response.status_code == 200
        assert response.get_json() == {'success': True, 'message': 'Success', 'data': []}

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
