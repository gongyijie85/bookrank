"""weekly_report_task 模块测试

覆盖范围：
- send_weekly_report_email（已禁用，始终返回 False）
- generate_weekly_report（冷却、锁竞争、无 book_service、成功生成、已有报告跳过）
- schedule_weekly_report
- compute_expected_week_range（v0.9.46 新增）
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch


class _MockWeeklyReport:
    """构造 WeeklyReport 模拟对象"""

    def __init__(
        self,
        title: str = '测试周报',
        summary: str = '本周畅销书概览',
        content: str | None = None,
        report_date: date | None = None,
        week_start: date | None = None,
        week_end: date | None = None,
    ) -> None:
        self.title = title
        self.summary = summary
        self.content = content
        self.report_date = report_date or date.today()
        self.week_start = week_start or (date.today() - timedelta(days=7))
        self.week_end = week_end or (date.today() - timedelta(days=1))
        self.view_count = 0


class TestSendWeeklyReportEmail:
    """测试 send_weekly_report_email 函数（已禁用）"""

    def test_always_returns_false(self, app):
        """验证邮件发送始终返回 False（Render 免费版禁用）"""
        with app.app_context():
            from app.tasks.weekly_report_task import send_weekly_report_email

            report = _MockWeeklyReport()
            result = send_weekly_report_email(report)
            assert result is False


class TestGenerateWeeklyReport:
    """测试 generate_weekly_report 函数"""

    def _reset_globals(self):
        """重置模块级全局变量"""
        import app.tasks.weekly_report_task as mod

        mod._last_report_trigger_time = 0

    def test_cooldown_skip(self, app):
        """验证冷却期内跳过生成"""
        self._reset_globals()
        with app.app_context():
            import time

            import app.tasks.weekly_report_task as mod

            mod._last_report_trigger_time = time.time()
            result = mod.generate_weekly_report()
            assert result is None

    def test_cooldown_bypassed_with_force(self, app):
        """验证 force_regenerate 跳过冷却检查"""
        self._reset_globals()
        with app.app_context():
            import time

            import app.tasks.weekly_report_task as mod

            mod._last_report_trigger_time = time.time()
            with patch.object(mod, 'require_book_service', side_effect=RuntimeError('未初始化')):
                result = mod.generate_weekly_report(force_regenerate=True)
                assert result is None  # RuntimeError 被捕获返回 None

    def test_lock_contention(self, app):
        """验证并发锁竞争时跳过"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            lock = mod._weekly_report_lock
            lock.acquire(blocking=False)
            try:
                result = mod.generate_weekly_report()
                assert result is None
            finally:
                lock.release()

    def test_no_book_service(self, app):
        """验证 book_service 未初始化时返回 None"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            with patch.object(mod, 'require_book_service', side_effect=RuntimeError('服务未初始化')):
                result = mod.generate_weekly_report(force_regenerate=True)
                assert result is None

    def test_report_generation_success(self, app, db):
        """验证正常生成周报成功"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            mock_report = _MockWeeklyReport()
            mock_book_service = MagicMock()
            mock_report_service = MagicMock()
            mock_report_service.generate_report.return_value = mock_report

            with (
                patch.object(mod, 'require_book_service', return_value=mock_book_service),
                patch.object(mod, 'WeeklyReportService', return_value=mock_report_service),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = None
                result = mod.generate_weekly_report(force_regenerate=True)

            assert result is mock_report
            mock_report_service.generate_report.assert_called_once()

    def test_existing_report_skip(self, app, db):
        """验证已有报告时直接返回已有报告"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            existing = _MockWeeklyReport(title='已有周报')
            mock_book_service = MagicMock()

            with (
                patch.object(mod, 'require_book_service', return_value=mock_book_service),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = existing
                result = mod.generate_weekly_report()

            assert result is existing

    def test_existing_report_force_regenerate(self, app, db):
        """验证强制重新生成时生成新报告"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            existing = _MockWeeklyReport(title='旧报告')
            new_report = _MockWeeklyReport(title='新报告')
            mock_book_service = MagicMock()
            mock_report_service = MagicMock()
            mock_report_service.generate_report.return_value = new_report

            with (
                patch.object(mod, 'require_book_service', return_value=mock_book_service),
                patch.object(mod, 'WeeklyReportService', return_value=mock_report_service),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = existing
                result = mod.generate_weekly_report(force_regenerate=True)

            assert result is new_report
            mock_report_service.generate_report.assert_called_once()

    def test_generation_failure_returns_none(self, app, db):
        """验证生成失败返回 None"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            mock_book_service = MagicMock()
            mock_report_service = MagicMock()
            mock_report_service.generate_report.return_value = None

            with (
                patch.object(mod, 'require_book_service', return_value=mock_book_service),
                patch.object(mod, 'WeeklyReportService', return_value=mock_report_service),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = None
                result = mod.generate_weekly_report(force_regenerate=True)

            assert result is None

    def test_exception_in_service_returns_none(self, app, db):
        """验证 WeeklyReportService 抛出异常时返回 None"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            mock_book_service = MagicMock()

            with (
                patch.object(mod, 'require_book_service', return_value=mock_book_service),
                patch.object(mod, 'WeeklyReportService', side_effect=Exception('意外错误')),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = None
                result = mod.generate_weekly_report(force_regenerate=True)

            assert result is None

    def test_lock_released_on_exception(self, app, db):
        """验证异常后锁被正确释放"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            with (
                patch.object(mod, 'require_book_service', side_effect=RuntimeError('未初始化')),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = None
                mod.generate_weekly_report(force_regenerate=True)

            assert not mod._weekly_report_lock.locked()

    def test_lock_released_on_success(self, app, db):
        """验证成功后锁被正确释放"""
        self._reset_globals()
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            mock_report = _MockWeeklyReport()
            mock_book_service = MagicMock()
            mock_report_service = MagicMock()
            mock_report_service.generate_report.return_value = mock_report

            with (
                patch.object(mod, 'require_book_service', return_value=mock_book_service),
                patch.object(mod, 'WeeklyReportService', return_value=mock_report_service),
                patch.object(mod, 'WeeklyReport') as MockWR,
            ):
                MockWR.query.filter.return_value.first.return_value = None
                mod.generate_weekly_report(force_regenerate=True)

            assert not mod._weekly_report_lock.locked()


class TestScheduleWeeklyReport:
    """测试 schedule_weekly_report 函数"""

    def test_calls_generate(self, app):
        """验证调度函数调用 generate_weekly_report"""
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            mock_report = _MockWeeklyReport()
            with patch.object(mod, 'generate_weekly_report', return_value=mock_report) as mock_gen:
                result = mod.schedule_weekly_report()

            mock_gen.assert_called_once_with()
            assert result is mock_report

    def test_returns_none_on_failure(self, app):
        """验证生成失败时返回 None"""
        with app.app_context():
            import app.tasks.weekly_report_task as mod

            with patch.object(mod, 'generate_weekly_report', return_value=None):
                result = mod.schedule_weekly_report()

            assert result is None


class TestComputeExpectedWeekRange:
    """v0.9.46: 周报任务辅助函数测试"""

    def test_monday_returns_last_week(self):
        """周一（weekday=0）→ 期望上周的周报"""
        from app.tasks.weekly_report_task_helpers import compute_expected_week_range

        # 2026-06-01 是周一
        week_start, week_end = compute_expected_week_range(date(2026, 6, 1))
        assert week_start == date(2026, 5, 25)
        assert week_end == date(2026, 5, 31)

    def test_tuesday_returns_last_week(self):
        """周二（weekday=1）→ 期望上周的周报"""
        from app.tasks.weekly_report_task_helpers import compute_expected_week_range

        # 2026-06-02 是周二
        week_start, week_end = compute_expected_week_range(date(2026, 6, 2))
        assert week_start == date(2026, 5, 25)
        assert week_end == date(2026, 5, 31)

    def test_wednesday_returns_last_week(self):
        """周三（weekday=2）→ 期望上周的周报"""
        from app.tasks.weekly_report_task_helpers import compute_expected_week_range

        # 2026-06-03 是周三
        week_start, week_end = compute_expected_week_range(date(2026, 6, 3))
        assert week_start == date(2026, 5, 25)
        assert week_end == date(2026, 5, 31)

    def test_thursday_returns_current_week(self):
        """周四（weekday=3）→ 期望本周的周报"""
        from app.tasks.weekly_report_task_helpers import compute_expected_week_range

        # 2026-06-04 是周四
        week_start, week_end = compute_expected_week_range(date(2026, 6, 4))
        assert week_start == date(2026, 6, 1)
        assert week_end == date(2026, 6, 7)

    def test_friday_returns_current_week(self):
        """周五（weekday=4）→ 期望本周的周报"""
        from app.tasks.weekly_report_task_helpers import compute_expected_week_range

        # 2026-06-05 是周五
        week_start, week_end = compute_expected_week_range(date(2026, 6, 5))
        assert week_start == date(2026, 6, 1)
        assert week_end == date(2026, 6, 7)

    def test_sunday_returns_current_week(self):
        """周日（weekday=6）→ 期望本周的周报"""
        from app.tasks.weekly_report_task_helpers import compute_expected_week_range

        # 2026-06-07 是周日
        week_start, week_end = compute_expected_week_range(date(2026, 6, 7))
        assert week_start == date(2026, 6, 1)
        assert week_end == date(2026, 6, 7)


def test_cron_force_regenerates_existing_week(client, app):
    app.config['CRON_SECRET'] = 'test-secret'
    report = _MockWeeklyReport()
    report.id = 1

    with patch('app.tasks.weekly_report_task.generate_weekly_report', return_value=report) as generate:
        response = client.get(
            '/api/cron/trigger-weekly-report',
            headers={'Authorization': 'Bearer test-secret'},
        )

    assert response.status_code == 200
    generate.assert_called_once_with(force_regenerate=True)
