"""移动端路由渲染测试

验证 4 个 MVP 页面在移动端 UA 下渲染移动版模板，
在桌面 UA 下回退桌面版模板。
"""

from typing import Any
from unittest.mock import MagicMock, patch

from app.models.book import Book


def _make_book(**overrides: Any) -> Book:
    """构造测试用 Book 对象"""
    defaults: dict[str, Any] = {
        'id': '9780143127550',
        'title': 'Test Book',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'cover': '',
        'list_name': 'Hardcover Fiction',
        'category_id': 'hardcover-fiction',
        'category_name': '精装小说',
        'rank': 1,
        'weeks_on_list': 3,
        'rank_last_week': '2',
        'published_date': '2024-01-14',
        'description': 'A test description',
        'details': 'Test details',
        'publication_dt': '2023-10-01',
        'page_count': '320',
        'language': 'en',
        'buy_links': [],
        'isbn13': '9780143127550',
        'isbn10': '014312755X',
        'price': '28.00',
        'title_zh': None,
        'description_zh': None,
        'details_zh': None,
    }
    defaults.update(overrides)
    return Book(**defaults)


def _mock_book_service(books=None):
    """构造 mock book_service"""
    svc = MagicMock()
    svc.get_books_by_category.return_value = books or []
    svc.get_cache_time.return_value = '2024-01-14'
    svc.get_latest_cache_time.return_value = '2024-01-14'
    svc.search_books.return_value = []
    return svc


MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'
DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'


class TestMobileIndexRoute:
    """首页移动端渲染"""

    @patch('app.routes.main.get_book_service')
    def test_mobile_ua_renders_mobile_template(self, mock_get_svc, client) -> None:
        """移动端 UA 访问首页应渲染移动版模板（含 m-tabbar）"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data  # 移动端底部 Tab 栏

    @patch('app.routes.main.get_book_service')
    def test_desktop_ua_renders_desktop_template(self, mock_get_svc, client) -> None:
        """桌面端 UA 访问首页应渲染桌面版模板（不含 m-tabbar）"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' not in resp.data


class TestMobileBookDetailRoute:
    """书籍详情页移动端渲染"""

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.fetch_google_books_details')
    @patch('app.routes.main.get_book_service')
    def test_mobile_ua_renders_mobile_book_detail(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """移动端 UA 访问书籍详情应渲染移动版模板"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert b'm-fav-btn' in resp.data  # 收藏按钮


class TestMobileProfileRoute:
    """个人中心移动端渲染"""

    def test_mobile_ua_renders_profile(self, client, db) -> None:
        """移动端 UA 访问 /profile 应渲染移动版个人中心"""
        resp = client.get('/profile', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '我的'.encode() in resp.data

    def test_profile_shows_empty_state_without_data(self, client, db) -> None:
        """无数据时个人中心显示空状态"""
        resp = client.get('/profile', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert '暂无收藏'.encode() in resp.data


class TestMobileAwardsRoute:
    """奖项榜单移动端渲染"""

    def test_mobile_ua_renders_awards(self, client, db) -> None:
        """移动端 UA 访问 /awards 应渲染移动版奖项页"""
        resp = client.get('/awards', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data


class TestMobileSearchRoute:
    """搜索页移动端渲染"""

    def test_mobile_ua_renders_search(self, client) -> None:
        """移动端 UA 访问 /search 应渲染移动版搜索页"""
        resp = client.get('/search', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '搜索书籍'.encode() in resp.data


class TestMobileWeeklyRoute:
    """周报列表移动端渲染"""

    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_book_service')
    def test_mobile_ua_renders_weekly(self, mock_get_svc, mock_report_svc, client) -> None:
        """移动端 UA 访问 /reports/weekly 应渲染移动版周报列表"""
        mock_get_svc.return_value = _mock_book_service([])

        report_mock = MagicMock()
        report_mock.get_or_trigger_current_week_report.return_value = (None, False)
        report_mock.get_reports.return_value = []
        mock_report_svc.return_value = report_mock

        resp = client.get('/reports/weekly', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '阅读周报'.encode() in resp.data


class TestTemplateFallback:
    """模板回退机制测试"""

    def test_mobile_template_missing_falls_back_to_desktop(self, client, app) -> None:
        """移动模板缺失时自动回退桌面版（不报错）"""
        from jinja2 import TemplateNotFound

        from app.utils.template_resolver import render_adaptive

        # 模拟移动端 + 模板缺失场景
        with app.test_request_context('/', headers={'User-Agent': MOBILE_UA}):
            # render_adaptive 内部会捕获 TemplateNotFound 并回退
            # 这里验证回退逻辑：当 mobile/xxx.html 不存在时，应回退到 xxx.html
            with patch('app.utils.template_resolver.render_template') as mock_render:
                def side_effect(name, **ctx):
                    if name.startswith('mobile/'):
                        raise TemplateNotFound(name)
                    return f'desktop:{name}'
                mock_render.side_effect = side_effect
                result = render_adaptive('nonexistent.html')
                assert result == 'desktop:nonexistent.html'


class TestMobileAwardBookDetailRoute:
    """获奖图书详情页移动端渲染"""

    def test_award_book_detail_mobile_renders_mobile_template(self, client, db, sample_award_book) -> None:
        """移动端 UA 访问 /award-book/<id> 应渲染移动版详情页"""
        from app.models.schemas import AwardBook

        # sample_award_book fixture 默认 is_displayable=False，需改为 True
        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        db.session.commit()

        resp = client.get(f'/award-book/{sample_award_book}', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data


class TestMobileAboutAndErrorRoute:
    """关于页与错误页移动端渲染"""

    def test_about_mobile_renders_mobile_template(self, client) -> None:
        """移动端 UA 访问 /about 应渲染移动版关于页"""
        resp = client.get('/about', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data

    @patch('app.routes.main.get_book_service')
    def test_error_page_mobile_renders_mobile_template(self, mock_get_svc, client) -> None:
        """移动端 UA 访问不存在的书籍应渲染移动版错误页"""
        mock_get_svc.return_value = _mock_book_service([])  # 空书籍列表
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert b'm-error-page' in resp.data


class TestMobileWeeklyReportDetailEnhanced:
    """周报详情增强内容测试"""

    @patch('app.routes.main.parse_report_content')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_book_service')
    def test_weekly_report_detail_has_top_risers(
        self, mock_get_svc, mock_report_svc, mock_parse, client
    ) -> None:
        """周报详情应包含'排名上升最快'区块"""
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])

        # 构造 mock report
        report_mock = MagicMock()
        report_mock.id = 1
        report_mock.week_end = date(2024, 1, 14)
        report_mock.created_at = datetime(2024, 1, 14, 10, 0)

        svc_mock = MagicMock()
        svc_mock.get_report_by_week_end.return_value = report_mock
        svc_mock.record_report_view.return_value = None
        mock_report_svc.return_value = svc_mock

        # mock parse_report_content 返回含 top_risers 和 longest_running
        mock_parse.return_value = {
            'top_risers': [{'title': '上升最快图书', 'rank_change': 5}],
            'longest_running': [{'title': '长青图书', 'weeks_on_list': 10}],
        }

        resp = client.get('/reports/weekly/2024-01-14', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert '排名上升最快'.encode() in resp.data
        assert '上升最快图书'.encode() in resp.data
        assert '持续上榜最久'.encode() in resp.data

    @patch('app.routes.main.parse_report_content')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_book_service')
    def test_weekly_report_detail_has_export_buttons(
        self, mock_get_svc, mock_report_svc, mock_parse, client
    ) -> None:
        """周报详情应包含 PDF/Excel 导出按钮"""
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])

        report_mock = MagicMock()
        report_mock.id = 1
        report_mock.week_end = date(2024, 1, 14)
        report_mock.created_at = datetime(2024, 1, 14, 10, 0)

        svc_mock = MagicMock()
        svc_mock.get_report_by_week_end.return_value = report_mock
        svc_mock.record_report_view.return_value = None
        mock_report_svc.return_value = svc_mock

        mock_parse.return_value = {}

        resp = client.get('/reports/weekly/2024-01-14', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'export?format=pdf' in resp.data
        assert b'export?format=excel' in resp.data


class TestMobileWeeklyReportsSearch:
    """周报列表搜索框测试"""

    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_book_service')
    def test_weekly_reports_has_search_box(self, mock_get_svc, mock_report_svc, client) -> None:
        """周报列表应包含搜索框"""
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])

        # 构造 1 条周报记录，使搜索框（在 {% if reports %} 块内）能渲染
        report_item = MagicMock()
        report_item.title = '测试周报'
        report_item.summary = '测试摘要'
        report_item.week_start = date(2024, 1, 8)
        report_item.week_end = date(2024, 1, 14)
        report_item.created_at = datetime(2024, 1, 14, 10, 0)
        report_item.content_data = None

        report_mock = MagicMock()
        report_mock.get_or_trigger_current_week_report.return_value = (None, False)
        report_mock.get_reports.return_value = [report_item]
        mock_report_svc.return_value = report_mock

        resp = client.get('/reports/weekly', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'type="search"' in resp.data
        assert b'filterBySearch' in resp.data
