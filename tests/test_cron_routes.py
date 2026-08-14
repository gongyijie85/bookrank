"""外部 cron 触发端点测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import SystemConfig
from app.utils.rate_limiter import get_rate_limiter


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
        mock_generate.assert_called_once_with(force_regenerate=True)

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


class TestTriggerNewBooksSync:
    """测试 /api/cron/trigger-new-books-sync 端点（issue #81）"""

    def test_missing_cron_secret_returns_401(self, client):
        response = client.get(
            '/api/cron/trigger-new-books-sync',
            headers={'Authorization': 'Bearer any-token'},
        )
        assert response.status_code == 401
        assert response.get_json()['success'] is False

    def test_missing_authorization_returns_401(self, client, cron_secret):
        response = client.get('/api/cron/trigger-new-books-sync')
        assert response.status_code == 401
        assert response.get_json()['success'] is False

    def test_valid_token_starts_background_sync(self, client, cron_secret):
        with patch('app.setup.trigger_auto_sync_background') as mock_trigger:
            mock_trigger.return_value = {'status': 'started'}
            response = client.get(
                '/api/cron/trigger-new-books-sync',
                headers={'Authorization': f'Bearer {cron_secret}'},
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'started'
        mock_trigger.assert_called_once()

    def test_valid_token_reports_already_running(self, client, cron_secret):
        with patch('app.setup.trigger_auto_sync_background') as mock_trigger:
            mock_trigger.return_value = {'status': 'already_running'}
            response = client.get(
                '/api/cron/trigger-new-books-sync',
                headers={'Authorization': f'Bearer {cron_secret}'},
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert '跳过' in data['message']


class TestRunAutoSyncPersistence:
    """run_auto_sync 必须 commit SystemConfig，否则 last-sync 读不到摘要。"""

    def test_persists_last_auto_sync_result_after_commit(self, app, db):
        from app.setup import run_auto_sync

        mock_modules = MagicMock()
        mock_modules.publisher_manager.init_publishers.return_value = None
        mock_modules.sync_engine.sync_all_publishers.return_value = [
            {
                'publisher': 'Simon & Schuster',
                'status': 'success',
                'success': True,
                'elapsed_seconds': 1.2,
                'added': 1,
                'updated': 0,
                'error': None,
                'traversed_total': 10,
                'rejected_no_date': 2,
                'rejected_unparseable': 0,
                'rejected_out_of_window': 3,
                'rejected_future_placeholder': 0,
                'accepted_year_only': 1,
            }
        ]

        with (
            app.app_context(),
            patch('app.setup.require_service', return_value=mock_modules),
        ):
            result = run_auto_sync()

        assert result['status'] == 'synced'
        raw = SystemConfig.get_value('last_auto_sync_result')
        assert raw is not None
        summary = json.loads(raw)
        assert summary['publishers'][0]['date_filter']['traversed_total'] == 10
        assert summary['publishers'][0]['date_filter']['rejected_no_date'] == 2
        assert SystemConfig.get_value('last_auto_sync_time') is not None


class TestCronRateLimit:
    """cron 端点限流测试（此前 /api/cron/ 完全豁免限流，属安全缺口）"""

    def test_exceeding_cron_rate_limit_returns_429(self, client, app, cron_secret) -> None:
        """连续请求超过 CRON_RATE_LIMIT 后应返回 429，而非无限放行"""
        app.config['TESTING'] = False
        limit = app.config.get('CRON_RATE_LIMIT', 20)
        window = app.config.get('CRON_RATE_LIMIT_WINDOW', 60)
        # 复用与 app/__init__.py 相同的缓存 key 拿到同一限流器实例并清空历史，
        # 避免同一 pytest 会话内其它用例的残留调用计数影响本测试判断。
        get_rate_limiter(max_requests=limit, window_seconds=window).reset()

        headers = {'Authorization': f'Bearer {cron_secret}'}
        with patch('app.tasks.weekly_report_task.generate_weekly_report') as mock_generate:
            mock_generate.return_value = None
            for _ in range(limit):
                resp = client.get('/api/cron/trigger-weekly-report', headers=headers)
                assert resp.status_code == 200

            resp = client.get('/api/cron/trigger-weekly-report', headers=headers)
        assert resp.status_code == 429
