"""weekly_report_task 模块测试

覆盖范围：
- _get_smtp_config
- _render_weekly_report_html
- send_weekly_report_email
- generate_weekly_report（冷却、锁竞争、无 book_service、成功生成、已有报告跳过）
- _fetch_image_as_base64
- _embed_covers_in_html
- schedule_weekly_report
"""

import base64
import json
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


def _sample_content() -> str:
    """返回一份完整的周报 JSON 内容"""
    return json.dumps(
        {
            'top_changes': [
                {
                    'title': '排名大变动',
                    'author': '作者A',
                    'category': '小说',
                    'rank': 1,
                    'rank_change': 5,
                    'weeks_on_list': 10,
                    'cover': 'https://example.com/cover1.jpg',
                    'original_cover': '',
                }
            ],
            'featured_books': [
                {
                    'title': '推荐书',
                    'author': '作者B',
                    'category': '非虚构',
                    'rank': 3,
                    'rank_change': 2,
                    'weeks_on_list': 8,
                    'cover': 'https://example.com/cover2.jpg',
                    'original_cover': '',
                }
            ],
            'new_books': [],
            'top_risers': [],
            'longest_running': [],
        },
        ensure_ascii=False,
    )


class TestGetSmtpConfig:
    """测试 _get_smtp_config 函数"""

    def test_returns_correct_keys(self, app):
        """验证返回字典包含所有必要字段"""
        with app.app_context():
            from app.tasks.weekly_report_task import _get_smtp_config

            cfg = _get_smtp_config()
            expected_keys = {'server', 'port', 'use_tls', 'username', 'password', 'sender', 'recipients'}
            assert set(cfg.keys()) == expected_keys

    def test_default_values(self, app):
        """验证未配置时使用默认值"""
        with app.app_context():
            from app.tasks.weekly_report_task import _get_smtp_config

            cfg = _get_smtp_config()
            assert cfg['server'] == 'smtp.gmail.com'
            assert cfg['port'] == 587
            assert cfg['use_tls'] is True
            assert cfg['sender'] == 'bookrank@example.com'

    def test_custom_config(self, app):
        """验证自定义配置被正确读取"""
        with app.app_context():
            app.config['MAIL_SERVER'] = 'smtp.qq.com'
            app.config['MAIL_PORT'] = 465
            app.config['MAIL_USE_TLS'] = False
            app.config['MAIL_USERNAME'] = 'user@qq.com'
            app.config['MAIL_PASSWORD'] = 'secret'
            app.config['MAIL_DEFAULT_SENDER'] = 'sender@qq.com'
            app.config['MAIL_RECIPIENTS'] = 'a@x.com,b@x.com'

            from app.tasks.weekly_report_task import _get_smtp_config

            cfg = _get_smtp_config()
            assert cfg['server'] == 'smtp.qq.com'
            assert cfg['port'] == 465
            assert cfg['use_tls'] is False
            assert cfg['username'] == 'user@qq.com'
            assert cfg['password'] == 'secret'
            assert cfg['sender'] == 'sender@qq.com'
            assert cfg['recipients'] == ['a@x.com', 'b@x.com']

    def test_empty_recipients(self, app):
        """验证空收件人字符串返回空列表"""
        with app.app_context():
            app.config['MAIL_RECIPIENTS'] = ''
            from app.tasks.weekly_report_task import _get_smtp_config

            cfg = _get_smtp_config()
            assert cfg['recipients'] == []

    def test_recipients_with_spaces(self, app):
        """验证收件人逗号分隔后自动去除空格"""
        with app.app_context():
            app.config['MAIL_RECIPIENTS'] = ' a@x.com , b@x.com ,  '
            from app.tasks.weekly_report_task import _get_smtp_config

            cfg = _get_smtp_config()
            assert cfg['recipients'] == ['a@x.com', 'b@x.com']

    def test_missing_optional_config(self, app):
        """验证缺少可选配置时返回 None"""
        with app.app_context():
            app.config.pop('MAIL_USERNAME', None)
            app.config.pop('MAIL_PASSWORD', None)
            from app.tasks.weekly_report_task import _get_smtp_config

            cfg = _get_smtp_config()
            assert cfg['username'] is None
            assert cfg['password'] is None


class TestRenderWeeklyReportHtml:
    """测试 _render_weekly_report_html 函数"""

    def test_basic_rendering(self, app):
        """验证基础渲染输出包含关键元素"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content=_sample_content())
            html = _render_weekly_report_html(report)

            assert '<!DOCTYPE html>' in html
            assert 'BookRank 畅销书周报' in html
            assert '本周畅销书概览' in html.replace('<br>', '\n')

    def test_week_date_range(self, app):
        """验证 HTML 包含周日期范围"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            ws = date(2026, 4, 20)
            we = date(2026, 4, 26)
            report = _MockWeeklyReport(week_start=ws, week_end=we, content=_sample_content())
            html = _render_weekly_report_html(report)

            assert '04月20日' in html
            assert '04月26日' in html

    def test_book_data_in_html(self, app):
        """验证书籍数据被正确渲染到 HTML"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content=_sample_content())
            html = _render_weekly_report_html(report)

            assert '排名大变动' in html
            assert '作者A' in html
            assert '推荐书' in html
            assert '作者B' in html

    def test_rank_change_positive(self, app):
        """验证排名上升的显示样式"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content=_sample_content())
            html = _render_weekly_report_html(report)

            assert '#38a169' in html  # 绿色（上升）
            assert '↑ 5 位' in html

    def test_rank_change_negative(self, app):
        """验证排名下降的显示样式"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            content = json.dumps(
                {
                    'top_changes': [
                        {
                            'title': '下滑书',
                            'author': '作者C',
                            'category': '小说',
                            'rank': 10,
                            'rank_change': -3,
                            'weeks_on_list': 2,
                            'cover': '',
                            'original_cover': '',
                        }
                    ],
                    'featured_books': [],
                    'new_books': [],
                    'top_risers': [],
                    'longest_running': [],
                },
                ensure_ascii=False,
            )
            report = _MockWeeklyReport(content=content)
            html = _render_weekly_report_html(report)

            assert '#e53e3e' in html  # 红色（下降）
            assert '↓ 3 位' in html

    def test_no_cover_shows_placeholder(self, app):
        """验证无封面时显示占位符"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            content = json.dumps(
                {
                    'top_changes': [
                        {
                            'title': '无封面书',
                            'author': '作者D',
                            'category': '小说',
                            'rank': 1,
                            'rank_change': 0,
                            'weeks_on_list': 1,
                            'cover': '',
                            'original_cover': '',
                        }
                    ],
                    'featured_books': [],
                    'new_books': [],
                    'top_risers': [],
                    'longest_running': [],
                },
                ensure_ascii=False,
            )
            report = _MockWeeklyReport(content=content)
            html = _render_weekly_report_html(report)

            assert '📖' in html

    def test_cover_image_rendered(self, app):
        """验证有封面时渲染 img 标签"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content=_sample_content())
            html = _render_weekly_report_html(report)

            assert 'https://example.com/cover1.jpg' in html
            assert '<img src=' in html

    def test_empty_content(self, app):
        """验证空 content 不导致崩溃"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content=None)
            html = _render_weekly_report_html(report)
            assert '<!DOCTYPE html>' in html

    def test_invalid_json_content(self, app):
        """验证非法 JSON content 不导致崩溃"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content='not a json')
            html = _render_weekly_report_html(report)
            assert '<!DOCTYPE html>' in html

    def test_summary_markdown_stripped(self, app):
        """验证摘要中的 Markdown # 符号被去除"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(
                summary='# 标题\n## 二级标题\n### 三级标题\n正文内容',
                content=_sample_content(),
            )
            html = _render_weekly_report_html(report)

            assert '# 标题' not in html
            assert '标题' in html

    def test_empty_sections_omitted(self, app):
        """验证空区块不渲染"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            content = json.dumps(
                {
                    'top_changes': [],
                    'featured_books': [],
                    'new_books': [],
                    'top_risers': [],
                    'longest_running': [],
                },
                ensure_ascii=False,
            )
            report = _MockWeeklyReport(content=content)
            html = _render_weekly_report_html(report)

            assert '重要变化' not in html
            assert '推荐书籍' not in html

    def test_max_five_books_per_section(self, app):
        """验证每个区块最多显示 5 本书"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            books = [
                {
                    'title': f'书{i}',
                    'author': f'作者{i}',
                    'category': '小说',
                    'rank': i,
                    'rank_change': 0,
                    'weeks_on_list': 1,
                    'cover': '',
                    'original_cover': '',
                }
                for i in range(8)
            ]
            content = json.dumps(
                {
                    'top_changes': books,
                    'featured_books': [],
                    'new_books': [],
                    'top_risers': [],
                    'longest_running': [],
                },
                ensure_ascii=False,
            )
            report = _MockWeeklyReport(content=content)
            html = _render_weekly_report_html(report)

            assert html.count('重要变化') == 1
            for i in range(5):
                assert f'书{i}' in html
            assert '书5' not in html

    def test_report_date_fallback(self, app):
        """验证 report_date 为 None 时不崩溃"""
        with app.app_context():
            from app.tasks.weekly_report_task import _render_weekly_report_html

            report = _MockWeeklyReport(content=_sample_content())
            report.report_date = None
            html = _render_weekly_report_html(report)
            assert '发布日期' in html


class TestSendWeeklyReportEmail:
    """测试 send_weekly_report_email 函数（已禁用）"""

    def test_always_returns_false(self, app):
        """验证邮件发送始终返回 False（Render 免费版禁用）"""
        with app.app_context():
            from app.tasks.weekly_report_task import send_weekly_report_email

            report = _MockWeeklyReport()
            result = send_weekly_report_email(report)
            assert result is False

    def test_does_not_access_smtp(self, app):
        """验证不会触发任何 SMTP 连接"""
        with app.app_context():
            from app.tasks.weekly_report_task import send_weekly_report_email

            report = _MockWeeklyReport()
            with patch('app.tasks.weekly_report_task._get_smtp_config') as mock_smtp:
                send_weekly_report_email(report)
                mock_smtp.assert_not_called()


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
                patch.object(mod, 'send_weekly_report_email'),
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
                patch.object(mod, 'send_weekly_report_email') as mock_email,
            ):
                MockWR.query.filter.return_value.first.return_value = existing
                result = mod.generate_weekly_report()

            assert result is existing
            mock_email.assert_called_once_with(existing)

    def test_existing_report_force_regenerate(self, app, db):
        """验证强制重新生成时删除已有报告"""
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
                patch.object(mod, 'send_weekly_report_email'),
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
                patch.object(mod, 'send_weekly_report_email'),
            ):
                MockWR.query.filter.return_value.first.return_value = None
                mod.generate_weekly_report(force_regenerate=True)

            assert not mod._weekly_report_lock.locked()


class TestFetchImageAsBase64:
    """测试 _fetch_image_as_base64 函数"""

    def test_invalid_url_returns_none(self, app):
        """验证无效 URL 返回 None"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            assert _fetch_image_as_base64('') is None
            assert _fetch_image_as_base64('not-a-url') is None
            assert _fetch_image_as_base64('ftp://example.com/img.jpg') is None

    def test_none_url_returns_none(self, app):
        """验证 None URL 返回 None"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            assert _fetch_image_as_base64(None) is None

    def test_http_error_returns_none(self, app):
        """验证 HTTP 错误返回 None"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception('404 Not Found')

            with patch('requests.get', return_value=mock_resp):
                result = _fetch_image_as_base64('https://example.com/missing.jpg')
                assert result is None

    def test_non_image_content_type_returns_none(self, app):
        """验证非图片 Content-Type 返回 None"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'text/html'}
            mock_resp.content = b'<html>error</html>'

            with patch('requests.get', return_value=mock_resp):
                result = _fetch_image_as_base64('https://example.com/page.html')
                assert result is None

    def test_successful_fetch(self, app):
        """验证成功下载并转换为 base64"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            image_data = b'\x89PNG\r\n\x1a\n'
            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'image/png'}
            mock_resp.content = image_data
            mock_resp.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_resp):
                result = _fetch_image_as_base64('https://example.com/cover.png')

            assert result is not None
            assert result.startswith('data:image/png;base64,')
            expected_b64 = base64.b64encode(image_data).decode('utf-8')
            assert result.endswith(expected_b64)

    def test_jpeg_content_type(self, app):
        """验证 JPEG Content-Type 正确处理"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            image_data = b'\xff\xd8\xff\xe0'
            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'image/jpeg'}
            mock_resp.content = image_data
            mock_resp.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_resp):
                result = _fetch_image_as_base64('https://example.com/cover.jpg')

            assert result is not None
            assert result.startswith('data:image/jpeg;base64,')

    def test_timeout_passed_to_requests(self, app):
        """验证 timeout 参数被正确传递"""
        with app.app_context():
            from app.tasks.weekly_report_task import _fetch_image_as_base64

            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'image/png'}
            mock_resp.content = b'\x89PNG'
            mock_resp.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_resp) as mock_get:
                _fetch_image_as_base64('https://example.com/cover.png', timeout=30)
                mock_get.assert_called_once()
                call_kwargs = mock_get.call_args
                assert call_kwargs.kwargs.get('timeout') == 30 or call_kwargs[1].get('timeout') == 30


class TestEmbedCoversInHtml:
    """测试 _embed_covers_in_html 函数"""

    def test_external_url_replaced(self, app):
        """验证外部 URL 被替换为 base64"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            image_data = b'\x89PNG'
            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'image/png'}
            mock_resp.content = image_data
            mock_resp.raise_for_status = MagicMock()

            html = '<img src="https://example.com/cover.png" alt="test">'
            with patch('requests.get', return_value=mock_resp):
                result = _embed_covers_in_html(html)

            assert 'data:image/png;base64,' in result
            assert 'https://example.com/cover.png' not in result

    def test_already_base64_unchanged(self, app):
        """验证已经是 base64 的 src 不被处理"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            b64_src = 'data:image/png;base64,abc123'
            html = f'<img src="{b64_src}" alt="test">'
            result = _embed_covers_in_html(html)

            assert b64_src in result

    def test_relative_path_no_base_url(self, app):
        """验证无 BASE_URL 时相对路径保持不变"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            app.config.pop('BASE_URL', None)
            html = '<img src="/cache/images/cover.jpg" alt="test">'

            with patch('pathlib.Path') as MockPath:
                mock_instance = MagicMock()
                mock_instance.exists.return_value = False
                MockPath.return_value = mock_instance
                result = _embed_covers_in_html(html)

            assert '/cache/images/cover.jpg' in result

    def test_relative_path_local_file(self, app):
        """验证相对路径从本地文件系统读取成功"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            image_data = b'\x89PNG'
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_bytes.return_value = image_data
            mock_path.suffix = '.png'

            html = '<img src="/cache/images/cover.png" alt="test">'

            with patch('pathlib.Path', return_value=mock_path):
                result = _embed_covers_in_html(html)

            assert 'data:image/png;base64,' in result

    def test_non_http_url_unchanged(self, app):
        """验证非 http/https URL 不被处理"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            html = '<img src="data:image/png;base64,abc" alt="test">'
            result = _embed_covers_in_html(html)
            assert 'data:image/png;base64,abc' in result

    def test_multiple_images(self, app):
        """验证多张图片同时处理"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            image_data = b'\x89PNG'
            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'image/png'}
            mock_resp.content = image_data
            mock_resp.raise_for_status = MagicMock()

            html = '<img src="https://example.com/a.png" alt="a"><img src="https://example.com/b.png" alt="b">'
            with patch('requests.get', return_value=mock_resp):
                result = _embed_covers_in_html(html)

            assert result.count('data:image/png;base64,') == 2

    def test_failed_download_keeps_original(self, app):
        """验证下载失败时保留原始 URL"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception('timeout')

            html = '<img src="https://example.com/fail.png" alt="test">'
            with patch('requests.get', return_value=mock_resp):
                result = _embed_covers_in_html(html)

            assert 'https://example.com/fail.png' in result

    def test_relative_path_with_base_url(self, app):
        """验证相对路径在有 BASE_URL 时拼接完整 URL 后发起请求"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            image_data = b'\x89PNG'
            mock_resp = MagicMock()
            mock_resp.headers = {'Content-Type': 'image/png'}
            mock_resp.content = image_data
            mock_resp.raise_for_status = MagicMock()

            app.config['BASE_URL'] = 'https://bookrank.example.com'

            mock_path = MagicMock()
            mock_path.exists.return_value = False

            html = '<img src="/cache/images/cover.png" alt="test">'

            with (
                patch('pathlib.Path', return_value=mock_path),
                patch('requests.get', return_value=mock_resp) as mock_get,
            ):
                _embed_covers_in_html(html)

            mock_get.assert_called_once()
            call_url = mock_get.call_args[0][0]
            assert call_url == 'https://bookrank.example.com/cache/images/cover.png'

    def test_relative_path_jpg_mime(self, app):
        """验证 .jpg 后缀使用 image/jpeg MIME 类型"""
        with app.app_context():
            from app.tasks.weekly_report_task import _embed_covers_in_html

            image_data = b'\xff\xd8\xff\xe0'
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_bytes.return_value = image_data
            mock_path.suffix = '.jpg'

            html = '<img src="/cache/images/cover.jpg" alt="test">'

            with patch('pathlib.Path', return_value=mock_path):
                result = _embed_covers_in_html(html)

            assert 'data:image/jpeg;base64,' in result


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
