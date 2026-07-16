"""外部 cron 触发端点测试"""

from unittest.mock import patch

import pytest


@pytest.fixture
def cron_secret(app):
    """设置测试用的 CRON_SECRET"""
    app.config['CRON_SECRET'] = 'test-cron-secret'
    return 'test-cron-secret'


class TestTriggerWeeklyReport:
    """测试 /api/cron/trigger-weekly-report 端点"""

    def test_missing_cron_secret_returns_401(self, client):
        response = client.get(
            '/api/cron/trigger-weekly-report',
            headers={'Authorization': 'Bearer any-token'},
        )
        assert response.status_code == 401
        assert response.get_json()['success'] is False

    def test_missing_authorization_returns_401(self, client, cron_secret):
        response = client.get('/api/cron/trigger-weekly-report')
        assert response.status_code == 401
        assert response.get_json()['success'] is False

    def test_invalid_token_returns_401(self, client, cron_secret):
        response = client.get(
            '/api/cron/trigger-weekly-report',
            headers={'Authorization': 'Bearer invalid-token'},
        )
        assert response.status_code == 401
        assert response.get_json()['success'] is False

    def test_valid_token_triggers_report(self, client, cron_secret):
        with patch('app.tasks.weekly_report_task.generate_weekly_report') as mock_generate:
            mock_generate.return_value = None
            response = client.get(
                '/api/cron/trigger-weekly-report',
                headers={'Authorization': f'Bearer {cron_secret}'},
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert '跳过' in data['message']
        mock_generate.assert_called_once()

    def test_valid_token_returns_report_data(self, client, cron_secret):
        from datetime import date

        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            id=1,
            report_date=date(2026, 5, 30),
            week_start=date(2026, 5, 25),
            week_end=date(2026, 5, 31),
            title='测试周报',
        )
        with patch('app.tasks.weekly_report_task.generate_weekly_report') as mock_generate:
            mock_generate.return_value = report
            response = client.get(
                '/api/cron/trigger-weekly-report',
                headers={'Authorization': f'Bearer {cron_secret}'},
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['title'] == '测试周报'
        assert data['data']['report_id'] == 1
