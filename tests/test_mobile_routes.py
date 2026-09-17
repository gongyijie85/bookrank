"""移动端路由渲染测试

验证 4 个 MVP 页面在移动端 UA 下渲染移动版模板，
在桌面 UA 下回退桌面版模板。
"""

import json
from pathlib import Path
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


def _related_recommendations() -> dict:
    """推荐位固定载荷：中英书名不同，才能验出 locale 有没有生效。"""
    return {
        'recommendations': [
            {
                'id': 999,
                'title': 'Related Book',
                'title_zh': '相关图书',
                'author': 'Related Author',
                'year': 2022,
                'category': 'Fiction',
                'cover_url': None,
                'isbn13': '9780000000999',
            }
        ],
        'reason': '',
    }


DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'
ZH_MOBILE_HEADERS = {'User-Agent': MOBILE_UA, 'Accept-Language': 'zh'}
EN_MOBILE_HEADERS = {'User-Agent': MOBILE_UA, 'Accept-Language': 'en'}


class TestMobileIndexRoute:
    """首页移动端渲染"""

    @patch('app.routes.main.get_service')
    def test_mobile_ua_renders_mobile_template(self, mock_get_svc, client) -> None:
        """移动端 UA 访问首页应渲染移动版模板（含 m-tabbar）"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data  # 移动端底部 Tab 栏

    @patch('app.routes.main.get_service')
    def test_desktop_ua_renders_desktop_template(self, mock_get_svc, client) -> None:
        """桌面端 UA 访问首页应渲染桌面版模板（不含 m-tabbar）"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' not in resp.data

    @patch('app.routes.main.get_service')
    def test_mobile_monthly_category_shows_hint(self, mock_get_svc, client) -> None:
        """移动端月榜分类显示月榜提示"""
        mock_get_svc.return_value = _mock_book_service(
            [
                _make_book(
                    category_id='paperback-nonfiction-monthly',
                    category_name='平装非虚构',
                    list_name='Paperback Nonfiction',
                    published_date='2026-06-01',
                )
            ]
        )
        resp = client.get('/?category=paperback-nonfiction-monthly&lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert '月榜 · 每月更新 · 榜单日期 2026-06-01'.encode() in resp.data

    @patch('app.routes.main.get_service')
    def test_mobile_weekly_category_hides_monthly_hint(self, mock_get_svc, client) -> None:
        """移动端周榜分类不显示月榜提示"""
        mock_get_svc.return_value = _mock_book_service([_make_book(published_date='2026-07-05')])
        resp = client.get('/?category=hardcover-fiction&lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert '月榜 · 每月更新'.encode() not in resp.data


class TestMobileBookDetailRoute:
    """书籍详情页移动端渲染"""

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_mobile_ua_renders_mobile_book_detail(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """移动端 UA 访问书籍详情应渲染移动版模板"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert b'm-tab-panel' in resp.data  # v0.9.78：详情用 Tab 面板
        assert b'ISBN' in resp.data  # ISBN 信息保留


class TestMobileProfileRoute:
    """个人中心移动端渲染"""

    def test_mobile_ua_renders_profile(self, client, db) -> None:
        """移动端 UA 访问 /profile 应渲染移动版个人中心"""
        resp = client.get('/profile?lang=zh', headers=ZH_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '我的'.encode() in resp.data

    def test_profile_shows_empty_state_without_data(self, client, db) -> None:
        """无数据时个人中心显示空状态"""
        resp = client.get('/profile?lang=zh', headers=ZH_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert '暂无收藏'.encode() in resp.data

    def test_profile_mobile_en_renders_english_labels(self, client, db) -> None:
        """英文移动端个人中心不应残留核心中文标签"""
        # `?lang=en` is pinned: `_get_locale` prefers the `lang` cookie over Accept-Language,
        # and the session-scoped test client inherits that cookie from tests that hit
        # /set-language. Relying on the header alone makes this depend on test order.
        resp = client.get('/profile?lang=en', headers=EN_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert b'<span>My</span>' in resp.data
        assert b'My Favorites' in resp.data


class TestDesktopProfileRoute:
    """个人中心桌面端渲染"""

    def test_desktop_ua_renders_profile(self, client, db) -> None:
        """桌面端 UA 访问 /profile 应渲染桌面版个人中心，而非 500"""
        resp = client.get('/profile?lang=zh', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' not in resp.data  # 确认走的是桌面模板，不是移动模板
        assert '我的收藏'.encode() in resp.data

    def test_desktop_ua_en_renders_english_labels(self, client, db) -> None:
        """英文桌面端个人中心不应残留核心中文标签"""
        resp = client.get('/profile', headers={'User-Agent': DESKTOP_UA, 'Accept-Language': 'en'})
        assert resp.status_code == 200
        assert b'Profile' in resp.data
        assert b'No favorites yet' in resp.data
        assert b'Tap the favorite button while browsing books to add them here' in resp.data
        assert '个人中心'.encode() not in resp.data


class TestMobileAwardsRoute:
    """奖项榜单移动端渲染"""

    def test_mobile_ua_renders_awards(self, client, db) -> None:
        """移动端 UA 访问 /awards 应渲染移动版奖项页"""
        resp = client.get('/awards', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data

    @patch('app.services.award_book_service.AwardBookService')
    def test_mobile_awards_filter_links_preserve_other_dimensions(self, MockAwardService, client) -> None:
        """移动端奖项页,清除某一维度筛选的链接应完整保留其余两个维度"""
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.book_count = 0
        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = [mock_award]
        mock_svc.get_distinct_years.return_value = [2024]
        mock_svc.get_distinct_categories.return_value = ['Fiction']
        mock_svc.get_award_by_name.return_value = mock_award
        mock_svc.get_award_books.return_value = ([], 0)
        mock_svc.get_book_counts_by_award.return_value = {1: 0}
        MockAwardService.return_value = mock_svc

        resp = client.get('/awards?award=TestAward&year=2024&category=Fiction', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # "全部"（清除奖项）应保留 year 与 category
        assert 'href="/awards?year=2024&amp;category=Fiction"' in html
        # "全部类别"（清除类别）应保留 award 与 year
        assert 'href="/awards?award=TestAward&amp;year=2024"' in html


class TestMobileSearchRoute:
    """搜索页移动端渲染"""

    def test_mobile_ua_renders_search(self, client) -> None:
        """移动端 UA 访问 /search 应渲染移动版搜索页"""
        resp = client.get('/search?lang=zh', headers=ZH_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '搜索书籍'.encode() in resp.data


class TestMobileWeeklyRoute:
    """周报列表移动端渲染"""

    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_mobile_ua_renders_weekly(self, mock_get_svc, mock_report_svc, client) -> None:
        """移动端 UA 访问 /reports/weekly 应渲染移动版周报列表"""
        mock_get_svc.return_value = _mock_book_service([])

        report_mock = MagicMock()
        report_mock.get_or_trigger_current_week_report.return_value = (None, False)
        report_mock.get_reports.return_value = []
        mock_report_svc.return_value = report_mock

        resp = client.get('/reports/weekly?lang=zh', headers=ZH_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '周报'.encode() in resp.data


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

    @patch('app.routes.main.get_service')
    def test_error_page_mobile_renders_mobile_template(self, mock_get_svc, client) -> None:
        """移动端 UA 访问不存在的书籍应渲染移动版错误页"""
        mock_get_svc.return_value = _mock_book_service([])  # 空书籍列表
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert b'm-error-page' in resp.data


class TestMobileWeeklyReportDetailEnhanced:
    """周报详情内容测试"""

    @patch('app.routes.main.parse_report_content')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_weekly_report_detail_renders_hero_stats(self, mock_get_svc, mock_report_svc, mock_parse, client) -> None:
        """周报详情应渲染 Hero 区数字卡片"""
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])

        report_mock = MagicMock()
        report_mock.id = 1
        report_mock.week_end = date(2024, 1, 14)
        report_mock.week_start = date(2024, 1, 8)
        report_mock.created_at = datetime(2024, 1, 14, 10, 0)
        report_mock.title = '测试周报'
        report_mock.summary = '测试摘要'

        svc_mock = MagicMock()
        svc_mock.get_report_by_week_end.return_value = report_mock
        svc_mock.record_report_view.return_value = None
        mock_report_svc.return_value = svc_mock

        mock_parse.return_value = {
            'total_books': 10,
            'total_new': 3,
            'total_rising': 4,
            'total_falling': 2,
            'top_changes': [{'title': '测试图书', 'rank_change': 5}],
        }

        resp = client.get('/reports/weekly/2024-01-14?lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-report-hero' in resp.data
        # `?lang=zh` is pinned deliberately: `_get_locale` defaults to 'en', so without it the
        # page renders English and these Chinese assertions only held while the English
        # catalogue had no entry for 上榜记录 / Top 5 排名变化 (the missing translation leaked
        # Chinese through). Asserting a language the request never asked for is a bug in the test.
        assert '上榜记录'.encode() in resp.data
        assert 'Top 5 排名变化'.encode() in resp.data

    @patch('app.routes.main.parse_report_content')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_weekly_report_detail_marks_unknown_metric_with_pending_class(
        self, mock_get_svc, mock_report_svc, mock_parse, client
    ) -> None:
        """未知总量须带 pending 类，已知数值不得带（移动端 390px 断词缺陷回归）

        `Data pending` 在 20px / 71px 单元格里会被 overflow-wrap:anywhere 拆成
        `Data / pendi / ng`；模板据 `total_*_known` 加 `.pending`（14px，
        line-height 1.3）让它整词折行。未知态永远不得显示 0。
        """
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])

        report_mock = MagicMock()
        report_mock.id = 1
        report_mock.week_end = date(2024, 1, 14)
        report_mock.week_start = date(2024, 1, 8)
        report_mock.created_at = datetime(2024, 1, 14, 10, 0)
        report_mock.title = '测试周报'
        report_mock.summary = '测试摘要'

        svc_mock = MagicMock()
        svc_mock.get_report_by_week_end.return_value = report_mock
        svc_mock.record_report_view.return_value = None
        mock_report_svc.return_value = svc_mock

        # total_books 缺失 → unknown；其余三项为已确认的真实计数（含一个已知 0）。
        mock_parse.return_value = {
            'total_new': 3,
            'total_rising': 4,
            'total_falling': 0,
        }

        resp = client.get('/reports/weekly/2024-01-14?lang=en', headers=EN_MOBILE_HEADERS)
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')

        # 恰好第一格（上榜记录）未知 → 只有它带 pending
        assert 'm-report-hero-stat-value pending' in body
        assert body.count('m-report-hero-stat-value pending') == 1
        # 未知格显示占位文案，绝不显示 0
        assert 'Data pending' in body
        # 已知的 0 仍按 0 渲染（已知零 ≠ 未知），且不带 pending
        assert 'm-report-hero-stat-value">0<' in body


class TestMobileIndexSimplified:
    """v0.9.76：移动端首页精简验证"""

    @patch('app.routes.main.get_service')
    def test_mobile_index_no_filter_panel(self, mock_get_svc, client) -> None:
        """移动端首页不应渲染筛选/排序面板"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-filter-panel' not in resp.data
        assert b'm-filter-toggle' not in resp.data

    @patch('app.routes.main.get_service')
    def test_mobile_index_shows_rank_insights(self, mock_get_svc, client) -> None:
        """移动端首页卡片应显示本周排名和历史上榜周数"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/?lang=zh', headers=ZH_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert b'm-book-insights' in resp.data
        assert '本周排名'.encode() in resp.data
        assert '历史上榜'.encode() in resp.data
        assert b'#1' in resp.data
        assert '3周'.encode() in resp.data

    @patch('app.routes.main.get_service')
    def test_mobile_index_has_top_nav(self, mock_get_svc, client) -> None:
        """移动端首页应渲染顶部导航栏"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-top-nav' in resp.data

    @patch('app.routes.main.get_service')
    def test_mobile_index_has_compact_hero_header(self, mock_get_svc, client) -> None:
        """移动端首页头部应为本地化 NYT 榜单主标题 + 小型品牌 kicker（紧凑 hero）"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-top-nav-copy' in resp.data
        assert b'm-top-nav-subtitle' in resp.data
        # 品牌 kicker 收小，h1 让位给本地化榜单任务标题
        assert b'THE BOOKRANK EDIT' in resp.data
        assert b'<h1 class="m-top-nav-title"' in resp.data
        assert b'data-i18n="page_title_bestsellers"' in resp.data
        # 不再保留旧的大号英文品牌 "BookRank Charts"
        assert b'<span>Charts</span>' not in resp.data


class TestMobileBookDetailV2:
    """v0.9.77：书籍详情页 v2 视觉验证（v0.9.78 删除了底部"返回榜单"按钮）"""

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_book_detail_has_meta_list(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """移动端书籍详情应使用单列元信息列表"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-meta-list' in resp.data

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_book_detail_no_back_button(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """v0.9.78：移动端书籍详情页应不显示底部"返回榜单"按钮"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-detail-actions' not in resp.data

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_book_detail_shows_facts_and_detail_text(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """移动端书籍详情应直接展示关键元数据和 details 正文"""
        mock_get_svc.return_value = _mock_book_service([_make_book(details='Full mobile detail text')])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-detail-facts' in resp.data
        assert b'Full mobile detail text' in resp.data


class TestMobileAwardBookDetailFullDescription:
    """v0.9.76：获奖图书详情完整描述"""

    def test_award_book_detail_shows_full_description(self, client, db, sample_award_book) -> None:
        """获奖图书详情应显示完整描述（不截断）"""
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        book.description = 'A' * 250
        db.session.commit()

        resp = client.get(f'/award-book/{sample_award_book}', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'A' * 250 in resp.data

    def test_award_book_detail_no_back_button(self, client, db, sample_award_book) -> None:
        """v0.9.78：获奖图书详情页应不显示底部"返回榜单"按钮"""
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        db.session.commit()

        resp = client.get(f'/award-book/{sample_award_book}', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-detail-actions' not in resp.data


class TestMobileWeeklyReportListV2:
    """v0.9.77：周报列表 v2 视觉验证"""

    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_weekly_list_shows_week_indicator(self, mock_get_svc, mock_report_svc, client) -> None:
        """移动端周报列表应显示周数指示器"""
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])

        report_mock = MagicMock()
        report_mock.id = 1
        report_mock.week_end = date(2024, 1, 14)
        report_mock.week_start = date(2024, 1, 8)
        report_mock.created_at = datetime(2024, 1, 14, 10, 0)
        report_mock.title = '测试周报'
        report_mock.summary = '测试摘要'
        report_mock.content_data = {'total_books': 10}

        svc_mock = MagicMock()
        svc_mock.get_or_trigger_current_week_report.return_value = (report_mock, False)
        svc_mock.get_reports.return_value = [report_mock]
        mock_report_svc.return_value = svc_mock

        resp = client.get('/reports/weekly', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-report-week' in resp.data
        assert b'W02' in resp.data


class TestMobileV978:
    """v0.9.78：详情页 Tab 化 + 删除放大镜 + Tab 改名 + 语言切换器"""

    # ----- base.html 通用：语言切换器 -----

    @patch('app.routes.main.get_service')
    def test_base_has_lang_switcher_button(self, mock_get_svc, client) -> None:
        """移动端 base.html 应包含语言切换按钮"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-lang-globe-btn' in resp.data
        assert b'id="m-lang-globe"' in resp.data

    @patch('app.routes.main.get_service')
    def test_base_has_lang_dropdown_options(self, mock_get_svc, client) -> None:
        """语言下拉应包含"简体中文"和"English"两个选项"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-lang-dropdown' in resp.data
        assert '简体中文'.encode() in resp.data
        assert b'data-lang="en"' in resp.data
        assert b'data-lang="zh"' in resp.data

    @patch('app.routes.main.get_service')
    def test_base_html_lang_follows_current_locale(self, mock_get_svc, client) -> None:
        """移动端 html lang 应跟随当前 locale，供 JS 与辅助技术读取"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA, 'Accept-Language': 'en'})
        assert resp.status_code == 200
        assert b'<html lang="en" data-lang="en">' in resp.data

    def test_mobile_language_switch_uses_server_locale_endpoint(self) -> None:
        """移动端切换语言应写服务端 lang cookie，而不是只改 localStorage"""
        js = Path('static/mobile/js/mobile.js').read_text(encoding='utf-8')
        assert '/set-language?lang=' in js
        assert 'encodeURIComponent(next)' in js
        assert 'localStorage.setItem(APP_LANG_STORAGE_KEY, lang)' in js
        assert "classList.toggle('active', isActive)" in js

    @patch('app.routes.main.get_service')
    def test_base_includes_book_i18n_script(self, mock_get_svc, client) -> None:
        """base.html 应引入 book-i18n.js"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'book-i18n' in resp.data

    # ----- 底部 Tab Bar 文字/链接 -----

    @patch('app.routes.main.get_service')
    def test_tabbar_no_search_label(self, mock_get_svc, client) -> None:
        """底部 Tab Bar 不应再含"搜索"Tab（data-tab 标识）"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        # 旧版"搜索"Tab 用 data-tab="search" 标识，应不再存在
        assert b'data-tab="search"' not in resp.data

    @patch('app.routes.main.get_service')
    def test_tabbar_has_awards_and_publisher(self, mock_get_svc, client) -> None:
        """底部 Tab Bar 应含"获奖书单"和"出版社"两个 Tab（data-tab 标识）"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        # 两个 Tab 用 data-tab 标识，locale 无关
        assert b'data-tab="awards"' in resp.data
        assert b'data-tab="publisher"' in resp.data

    @patch('app.routes.main.get_service')
    def test_tabbar_publisher_links_to_publishers(self, mock_get_svc, client) -> None:
        """底部出版社 Tab 应进入出版社导航页，而不是奖项页"""
        mock_get_svc.return_value = _mock_book_service([])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        publisher_tab = resp.data.split(b'data-tab="publisher"')[0].rsplit(b'<a ', 1)[-1]
        assert b'href="/publishers"' in publisher_tab
        assert b'href="/awards"' not in publisher_tab

    def test_publishers_mobile_renders_mobile_tab(self, client) -> None:
        """移动端访问 /publishers 应渲染移动版并高亮出版社 Tab"""
        resp = client.get('/publishers', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert b'data-tab="publisher"' in resp.data
        assert b'class="m-tab active" data-tab="publisher"' in resp.data

    def test_publishers_mobile_has_category_anchors(self, client) -> None:
        """出版社移动页应提供横向分类锚点导航"""
        resp = client.get('/publishers', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-publisher-anchors' in resp.data
        assert b'href="#publisher-cat-1"' in resp.data
        assert b'id="publisher-cat-1"' in resp.data

    @patch('app.routes.main.get_new_book_modules')
    def test_publishers_mobile_links_matched_entry_to_new_books(self, mock_get_modules, client) -> None:
        """移动端出版社页,数据库里有对应记录的条目应出现「查看新书」跳转链接"""
        mock_pub = MagicMock()
        mock_pub.id = 42
        mock_pub.name_en = 'Penguin Random House'
        mock_modules = MagicMock()
        mock_modules.publisher_manager.get_publishers.return_value = [mock_pub]
        mock_get_modules.return_value = mock_modules

        resp = client.get('/publishers', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert f'/new-books?publisher={mock_pub.id}'.encode() in resp.data

    # ----- 详情页 Tab 化 -----

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_book_detail_has_tabs(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """书籍详情页应包含"图书简介 / 详细信息"两个 Tab"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-detail-tabs' in resp.data
        assert b'm-tab-btn' in resp.data
        assert b'data-tab="description"' in resp.data
        assert b'data-tab="details"' in resp.data
        assert b'data-panel="description"' in resp.data
        assert b'data-panel="details"' in resp.data

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_book_detail_has_data_isbn_attr(self, mock_get_svc, mock_fetch, mock_merge, client) -> None:
        """书籍详情页 Tab 容器应带 data-isbn 属性供 JS 懒加载"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/book/0', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'data-isbn="9780143127550"' in resp.data
        assert b'data-book-index="0"' in resp.data

    def test_award_book_detail_has_tabs(self, client, db, sample_award_book) -> None:
        """获奖图书详情页应包含"图书简介"Tab；"详细信息"仅在确有实质 details 时出现。

        改版前无条件渲染第二个标签，于是只有元信息（出版社/奖项/年份）而没有 details 正文的
        书也挂着一个点了没内容的「详细信息」标签。现在标签按钮与面板同条件渲染。
        """
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        book.details = 'A substantial detail paragraph.'
        db.session.commit()

        resp = client.get(f'/award-book/{sample_award_book}', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-detail-tabs' in resp.data
        assert b'm-tab-btn' in resp.data
        assert b'data-tab="description"' in resp.data
        assert b'data-tab="details"' in resp.data
        assert b'data-panel="details"' in resp.data

    def test_award_book_detail_hides_details_tab_without_details(self, client, db, sample_award_book) -> None:
        """反向断言：没有实质 details 时不该出现「详细信息」标签或面板。"""
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        book.details = None
        db.session.commit()

        resp = client.get(f'/award-book/{sample_award_book}', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'data-tab="description"' in resp.data
        assert b'data-tab="details"' not in resp.data
        assert b'data-panel="details"' not in resp.data

    @patch('app.routes.main.get_or_create_recommendation_service')
    def test_award_book_detail_mobile_shows_related_books(
        self, mock_get_rec_svc, client, db, sample_award_book
    ) -> None:
        """移动端获奖图书详情页,存在相关图书时应展示相关图书区块"""
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        db.session.commit()

        mock_rec_svc = MagicMock()
        mock_rec_svc.get_similarity_recommendations.return_value = _related_recommendations()
        mock_get_rec_svc.return_value = mock_rec_svc

        resp = client.get(f'/award-book/{sample_award_book}', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-related-books' in resp.data
        # 无 ?lang= 时默认英文：推荐位出原文书名。旧断言要求这里显示「相关图书」，
        # 那正是 #227 要消除的英文页中文泄漏，不是该保住的约定。
        assert b'Related Book' in resp.data
        assert '相关图书'.encode() not in resp.data

    @patch('app.routes.main.get_or_create_recommendation_service')
    def test_award_book_detail_related_books_follow_zh(self, mock_get_rec_svc, client, db, sample_award_book) -> None:
        """?lang=zh 时推荐位仍出中文书名（与英文页成对，防只修一半）。"""
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, sample_award_book)
        book.is_displayable = True
        db.session.commit()

        mock_rec_svc = MagicMock()
        mock_rec_svc.get_similarity_recommendations.return_value = _related_recommendations()
        mock_get_rec_svc.return_value = mock_rec_svc

        resp = client.get(f'/award-book/{sample_award_book}?lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-related-books' in resp.data
        assert '相关图书'.encode() in resp.data

    # ----- 首页搜索入口（#66 有意加回，替代历史无图标约定）-----

    @patch('app.routes.main.get_service')
    def test_index_has_search_icon_intentional(self, mock_get_svc, client) -> None:
        """#66 产品决策：移动端首页顶部 nav 恢复搜索图标（同页展开）。
        此断言证明是故意加回而非误操作。"""
        mock_get_svc.return_value = _mock_book_service([_make_book()])
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        top_nav_start = resp.data.find(b'm-top-nav')
        top_nav_end = resp.data.find(b'</nav>', top_nav_start)
        top_nav_block = resp.data[top_nav_start:top_nav_end]
        assert b'm-search-toggle' in top_nav_block


class TestMobileRankingsRoute:
    """更多榜单页（派生榜单）移动端渲染"""

    @staticmethod
    def _mocks(mock_get_svc, mock_award_svc):
        mock_get_svc.return_value = _mock_book_service([_make_book(title='My Friends', author='Fredrik Backman')])
        mock_award_svc.return_value.get_award_books.return_value = ([], 0)

    @patch('app.routes.main.get_service')
    @patch('app.services.award_book_service.AwardBookService')
    def test_mobile_ua_renders_mobile_template(self, mock_award_svc, mock_get_svc, client) -> None:
        self._mocks(mock_get_svc, mock_award_svc)
        resp = client.get('/rankings?lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' in resp.data
        assert '跨榜现象级'.encode() in resp.data
        assert b'My Friends' in resp.data

    @patch('app.routes.main.get_service')
    @patch('app.services.award_book_service.AwardBookService')
    def test_desktop_ua_renders_desktop_template(self, mock_award_svc, mock_get_svc, client) -> None:
        self._mocks(mock_get_svc, mock_award_svc)
        resp = client.get('/rankings?lang=zh', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' not in resp.data
        assert '跨榜现象级'.encode() in resp.data
        assert b'class="cross-list"' in resp.data


class TestMobileWeeklyParityAndCsp:
    """移动端周报：与桌面版信息对等 + CSP 下的脚本/兜底可用性"""

    @staticmethod
    def _report(week_end, top_changes=(), new_books=(), featured=(), total_books=12):
        from datetime import datetime, timedelta

        r = MagicMock()
        r.id = 1
        r.week_end = week_end
        r.week_start = week_end - timedelta(days=6)
        r.report_date = week_end
        r.created_at = datetime(2024, 1, 14, 10, 0)
        r.title = '测试周报'
        r.summary = '测试摘要'
        # audit04：路由会用 prepare_report_presentation 从 content 解析权威总量，
        # 因此 mock 必须提供可解析的 content JSON，而非手工塞 content_data。
        r.content = json.dumps(
            {
                'total_books': total_books,
                'total_new': 3,
                'total_rising': 1,
                'total_falling': 1,
                'top_changes': list(top_changes),
                'new_books': list(new_books),
                'featured_books': list(featured),
                'top_risers': [],
                'longest_running': [],
                'category_stats': {},
            },
            ensure_ascii=False,
        )
        return r

    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_list_groups_by_month_and_shows_stats(self, mock_get_svc, mock_report_svc, client) -> None:
        """列表页应按月份分组并给出三项统计（与桌面版对齐）"""
        from datetime import date

        mock_get_svc.return_value = _mock_book_service([])
        reports = [
            self._report(
                date(2024, 1, 14),
                top_changes=[{'title': 'A', 'rank': 3, 'rank_change': 5}],
                new_books=[{'title': 'B'}],
                featured=[{'title': 'C'}],
            ),
            self._report(date(2023, 12, 31)),
        ]
        svc = MagicMock()
        svc.get_or_trigger_current_week_report.return_value = (reports[0], False)
        svc.get_reports.return_value = reports
        mock_report_svc.return_value = svc

        resp = client.get('/reports/weekly?lang=zh', headers=ZH_MOBILE_HEADERS)
        assert resp.status_code == 200
        assert b'm-report-group' in resp.data
        assert b'm-report-chips' in resp.data
        # audit04：chips 展示权威总量（新上榜/上升/下降），不再用 Top-N 数组长度。
        assert '上升'.encode() in resp.data
        assert '新上榜'.encode() in resp.data
        assert b'W02' in resp.data

    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_generating_banner_declares_poll_marker(self, mock_get_svc, mock_report_svc, client) -> None:
        """生成中横幅须带 data-report-poll，且不得再出现裸内联 <script>

        CSP 为 script-src 'self' 'nonce-…'，无 unsafe-inline，内联脚本会被静默拦截。
        """
        from datetime import date

        mock_get_svc.return_value = _mock_book_service([])
        report = self._report(date(2024, 1, 14))
        svc = MagicMock()
        svc.get_or_trigger_current_week_report.return_value = (report, True)
        svc.get_reports.return_value = [report]
        mock_report_svc.return_value = svc

        resp = client.get('/reports/weekly?lang=zh', headers=ZH_MOBILE_HEADERS)
        body = resp.data.decode('utf-8')
        assert 'data-report-poll' in body
        assert 'startPolling' not in body

    @patch('app.routes.main.parse_report_content')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    @patch('app.routes.main.get_service')
    def test_detail_prefers_translated_title_and_shares(
        self, mock_get_svc, mock_report_svc, mock_parse, client
    ) -> None:
        """详情页书名走 title_zh，并提供分享入口"""
        from datetime import date, datetime

        mock_get_svc.return_value = _mock_book_service([])
        report = MagicMock()
        report.id = 1
        report.week_end = date(2024, 1, 14)
        report.week_start = date(2024, 1, 8)
        report.created_at = datetime(2024, 1, 14, 10, 0)
        report.title = '测试周报'
        report.summary = '测试摘要'
        svc = MagicMock()
        svc.get_report_by_week_end.return_value = report
        svc.record_report_view.return_value = None
        mock_report_svc.return_value = svc
        mock_parse.return_value = {
            'total_books': 10,
            'top_changes': [{'title': 'The Book', 'title_zh': '中文书名', 'rank': 3, 'rank_change': 5}],
            'new_books': [
                {'title': 'New One', 'title_zh': '新书', 'category': '小说', 'cover': '/cache/images/new-one.jpg'},
            ],
            'featured_books': [
                {
                    'title': 'Fav',
                    'title_zh': '荐书',
                    'author': 'A',
                    'reason': '值得一读',
                    'cover': '/cache/images/fav.jpg',
                },
            ],
        }

        body = client.get('/reports/weekly/2024-01-14?lang=zh', headers=ZH_MOBILE_HEADERS).data.decode('utf-8')
        assert '《中文书名》' in body
        assert 'data-share-url' in body
        assert 'm-report-hero' in body
        # 英雄区首格是权威「上榜记录」（原「总书数」措辞与 API 语义不符，已改名）。
        assert '上榜记录' in body
        # 兜底目标取自 mobile.js 常量，模板只负责开关标记；两张封面图都应带上
        assert body.count('data-cover-fallback') == 2

    def test_weekly_templates_have_no_csp_blocked_onerror(self) -> None:
        """移动端周报模板不得再使用内联 onerror（CSP 下永不执行）"""
        root = Path(__file__).resolve().parents[1] / 'templates' / 'mobile'
        for name in ('weekly_reports.html', 'weekly_report_detail.html'):
            src = (root / name).read_text(encoding='utf-8')
            assert 'onerror=' not in src, f'{name} 仍含被 CSP 屏蔽的内联 onerror'
            assert '<script>' not in src, f'{name} 仍含被 CSP 屏蔽的裸内联脚本'

    def test_mobile_js_wires_fallback_and_polling(self) -> None:
        """处理器必须在 DOM ready 队列里被真正调用（只定义不接线是本次要修的故障）"""
        root = Path(__file__).resolve().parents[1] / 'static' / 'mobile' / 'js' / 'mobile.js'
        src = root.read_text(encoding='utf-8')
        ready_block = src[src.index('ready(function () {') :]
        for fn in ('initImageFallback()', 'initReportPolling()', 'initShareButtons()'):
            assert fn in ready_block, f'{fn} 未接入 DOM ready 初始化'
        assert "'error'," in src and 'true' in src, '图片兜底须用捕获阶段监听（error 不冒泡）'


class TestMobileNewBooksCategoryChips:
    """移动端新书页的分类 chip。

    `query_service.get_categories()` 返回的是 `{'name','count'}` 字典列表，桌面版取
    `cat.name`；移动版曾直接输出 `{{ cat }}`，于是 chip 文案变成 Python repr、href 变成
    `?category={'name': ...}`（点不动，也永远匹配不上 selected_category）。
    """

    CATEGORIES = [
        {'name': '儿童读物', 'count': 419},
        {'name': '小说', 'count': 402},
    ]

    @staticmethod
    def _mock_modules():
        modules = MagicMock()
        modules.publisher_manager.get_publishers.return_value = []
        modules.publisher_manager.get_publisher_book_counts.return_value = {}
        modules.query_service.get_categories.return_value = TestMobileNewBooksCategoryChips.CATEGORIES
        modules.query_service.get_new_books.return_value = ([], 0)
        modules.query_service.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        return modules

    @patch('app.routes.main.get_new_book_modules')
    def test_chips_render_names_not_dict_repr(self, mock_get_modules, client) -> None:
        mock_get_modules.return_value = self._mock_modules()
        resp = client.get('/new-books?lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '&#39;name&#39;' not in html, 'chip 仍在输出 Python 字典 repr'
        assert '儿童读物' in html and '小说' in html
        # 中文分类名必须被编码进 query，否则链接点不开
        assert 'category=%E5%B0%8F%E8%AF%B4' in html

    @staticmethod
    def _fake_books():
        book = MagicMock()
        book.id = 7
        book.title = 'The Machine'
        book.title_zh = '机器'
        book.author = 'Ann Writer'
        book.category = '小说'
        book.description = 'An English blurb.'
        book.description_zh = '中文简介。'
        book.cover_url = ''
        book.publication_date = '2026-09-01'
        book.publisher = None
        return [book]

    @patch('app.routes.main.get_new_book_modules')
    def test_english_page_uses_english_titles_and_categories(self, mock_get_modules, client) -> None:
        modules = self._mock_modules()
        modules.query_service.get_new_books.return_value = (self._fake_books(), 1)
        mock_get_modules.return_value = modules

        html = client.get('/new-books?lang=en', headers={'User-Agent': MOBILE_UA}).get_data(as_text=True)
        assert 'm-book-title' in html
        assert 'The Machine' in html, '英文页书名仍是中文'
        assert '机器' not in html
        assert '中文简介。' not in html, '英文页简介取了译文'
        assert '>Fiction<' in html, '分类 chip 未英文化'
        assert 'category=%E5%B0%8F%E8%AF%B4' in html, 'chip 链接仍需保留中文筛选键'

    @patch('app.routes.main.get_new_book_modules')
    def test_chinese_page_keeps_translated_title(self, mock_get_modules, client) -> None:
        modules = self._mock_modules()
        modules.query_service.get_new_books.return_value = (self._fake_books(), 1)
        mock_get_modules.return_value = modules

        html = client.get('/new-books?lang=zh', headers={'User-Agent': MOBILE_UA}).get_data(as_text=True)
        assert '机器' in html, '中文页丢了中文书名'
        assert '中文简介。' in html
        assert '小说' in html

    @patch('app.routes.main.get_new_book_modules')
    def test_selected_category_marks_chip_active(self, mock_get_modules, client) -> None:
        mock_get_modules.return_value = self._mock_modules()
        resp = client.get('/new-books?category=小说&lang=zh', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        anchors = [a for a in html.split('<a ') if 'category=%E5%B0%8F%E8%AF%B4' in a]
        assert anchors, '未渲染小说分类 chip 链接'
        assert any('active' in a for a in anchors), '选中的分类 chip 未标记 active'
        assert '小说</a>' in html
