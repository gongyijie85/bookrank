"""首页搜索状态条渲染 + 头部收口（audit item05 / item01 的模板侧契约）。

- search_status empty/partial/failed 与 data_load_failed 的状态条在真实模板里渲染
  （empty 回显查询词并提供清除；failed 重试保留查询词；partial 警告且结果仍显示）
- 卡面不再显示可见 ISBN（保留 data-isbn 供 JS 按需翻译 / 收藏使用）
- 头部：h1 主标题即当前语言榜单名；不再渲染重复的顶部快速链接条（.charts-sections）

后端 search_status 契约本身在 test_ux_search.py 已锁，这里只锁模板渲染结果，
避免把实现细节当成契约。
"""

from unittest.mock import patch

from bs4 import BeautifulSoup

from app.routes import main as main_routes
from app.utils import ExternalAPIError


def _make_book(**overrides):
    book = {
        'title': 'Test Book',
        'title_zh': '测试图书',
        'author': 'Test Author',
        'cover': '',
        '_original_cover': '',
        'isbn13': '9780143127550',
        'isbn10': '014312755X',
        'rank': 1,
        'source_index': 0,
        'source_category': 'hardcover-fiction',
        'category_name': '精装小说',
        'list_name': 'Hardcover Fiction',
        'publisher': 'Test Publisher',
        'weeks_on_list': 3,
        'previous_rank': 2,
        'is_new': False,
        'is_returning': False,
        'published_date': '2024-01-14',
        'description': 'A test description',
        'description_zh': '一段测试简介',
    }
    book.update(overrides)
    return book


def _get_index(client, **query):
    """真实渲染首页；search 路径 patch _search_all_categories，data_load 路径 patch 抓取。"""
    return client.get('/?' + '&'.join(f'{k}={v}' for k, v in query.items()) if query else '/')


class TestSearchStateRendering:
    def test_empty_state_echoes_query_and_offers_clear(self, client):
        with patch.object(main_routes, '_search_all_categories', return_value=([], [])):
            resp = _get_index(client, search='不存在关键词')
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        banner = soup.select_one('.search-state.state-empty')
        assert banner is not None, '搜索零结果应渲染 empty 状态条'
        assert '不存在关键词' in banner.get_text(' ', strip=True)
        clear = banner.select_one('.search-state-clear')
        assert clear is not None, 'empty 状态条应提供清除搜索入口'
        # 清除搜索后回到当前分类，不带查询词
        assert 'search' not in clear['href']
        # 空结果时不应再渲染通用 empty-state（避免一处两现）
        assert soup.select_one('.empty-state') is None

    def test_partial_state_warns_but_still_renders_results(self, client):
        books = [_make_book()]
        with patch.object(main_routes, '_search_all_categories', return_value=(books, ['business-books'])):
            resp = _get_index(client, search='测试')
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        banner = soup.select_one('.search-state.state-partial')
        assert banner is not None, '部分分类不可用应渲染 partial 状态条'
        assert '1' in banner.get_text(' ', strip=True)
        # 可用结果仍应渲染
        assert soup.select_one('#books-grid .card') is not None, 'partial 状态下仍应显示可用结果'

    def test_failed_state_offers_retry_preserving_query(self, client, app):
        total = len(app.config['CATEGORIES'])
        with patch.object(
            main_routes, '_search_all_categories', return_value=([], list(app.config['CATEGORIES'].keys()))
        ):
            resp = _get_index(client, search='台北')
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        banner = soup.select_one('.search-state.state-failed')
        assert banner is not None, '全部分类失败应渲染 failed 状态条'
        retry = banner.select_one('.search-state-clear')
        assert retry is not None
        assert 'search=' in retry['href'], '重试链接应保留查询词'
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(retry['href']).query)
        assert qs.get('search') == ['台北'], '重试链接应保留原始查询词'

    def test_data_load_failed_shows_retry(self, client):
        with patch.object(main_routes, '_get_books_for_category', side_effect=ExternalAPIError('boom')):
            resp = _get_index(client)
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        banner = soup.select_one('.search-state.state-failed')
        assert banner is not None, '单分类抓取失败应渲染重试状态条'


class TestListingHierarchy:
    def test_visible_isbn_removed_but_data_isbn_kept(self, client):
        books = [_make_book()]
        with patch.object(main_routes, '_search_all_categories', return_value=(books, [])):
            resp = _get_index(client, search='测试')
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        card = soup.select_one('#books-grid .card')
        assert card is not None
        # data-isbn 保留供 JS 按需翻译 / 收藏
        assert card.get('data-isbn') == '9780143127550'
        # 可见 ISBN 不应再出现
        assert card.select_one('.card-pub-isbn-item.isbn') is None
        assert card.select_one('.card-pub-isbn-item.isbn13') is None


class TestHeaderIdentity:
    def test_no_duplicate_top_quicklink_strip(self, client):
        with patch.object(main_routes, '_search_all_categories', return_value=([_make_book()], [])):
            resp = _get_index(client, search='测试')
        html = resp.get_data(as_text=True)
        # 首页不再渲染重复的顶部快速链接条
        assert 'class="charts-sections"' not in html

    def test_h1_is_chart_title_in_zh(self, client):
        with patch.object(main_routes, '_search_all_categories', return_value=([_make_book()], [])):
            resp = _get_index(client, search='测试', lang='zh')
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        h1 = soup.select_one('.page-title')
        assert h1 is not None
        text = h1.get_text(strip=True)
        assert '纽约时报畅销书排行榜' in text, f'中文 locale 下主标题应是中文榜单名，实际: {text}'
        assert 'BookRank' not in text, '主标题不应再是品牌大标题'


class TestMobileSearchStateParity:
    """独立 true-mobile 模板的搜索状态条与桌面端同构（data_load/partial/failed 走同一 context）。"""

    MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'

    def test_mobile_empty_state_echoes_query_and_offers_clear(self, client):
        with patch.object(main_routes, '_search_all_categories', return_value=([], [])):
            resp = client.get('/?search=不存在关键词', headers={'User-Agent': self.MOBILE_UA})
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        banner = soup.select_one('.m-search-state')
        assert banner is not None, '移动端搜索零结果应渲染状态条'
        assert '不存在关键词' in banner.get_text(' ', strip=True)
        clear = banner.select_one('.m-search-state-clear')
        assert clear is not None and 'search' not in clear['href'], '移动端 empty 状态条应提供清除入口'

    def test_mobile_failed_state_offers_retry_preserving_query(self, client, app):
        with patch.object(
            main_routes,
            '_search_all_categories',
            return_value=([], list(app.config['CATEGORIES'].keys())),
        ):
            resp = client.get('/?search=台北', headers={'User-Agent': self.MOBILE_UA})
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.get_data(as_text=True), 'html.parser')
        banner = soup.select_one('.m-search-state')
        assert banner is not None, '移动端全部分类失败应渲染状态条'
        retry = banner.select_one('.m-search-state-clear')
        assert retry is not None
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(retry['href']).query)
        assert qs.get('search') == ['台北'], '移动端重试链接应保留查询词'
