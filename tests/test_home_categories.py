"""首页 13 分类 + 跨分类搜索（#66）."""

from unittest.mock import MagicMock, patch

from app.config import Config
from app.models.book import Book


def _make_book(**overrides):
    defaults = {
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


def _mock_book_service(by_category):
    """按分类返回不同书单的 mock service."""
    svc = MagicMock()

    def _get_books(category_id, **kwargs):
        return by_category.get(category_id, [])

    svc.get_books_by_category.side_effect = _get_books
    svc.get_cache_time.return_value = '2024-01-14'
    svc.get_latest_cache_time.return_value = '2024-01-14'
    svc.search_books.return_value = []
    return svc


MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'
DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'


def _mobile_tabs(html: str) -> str:
    """只取移动端分类 tabs 那一段，避免整页别处的中英文造成误判。"""
    start = html.find('m-cat-tabs')
    if start < 0:
        return ''
    end = html.find('</section>', start)
    return html[start : end if end > start else None]


class TestCategoryConfig:
    def test_thirteen_categories(self):
        assert len(Config.CATEGORIES) == 13

    def test_groups_cover_all_exactly_once(self):
        grouped = [c for cats in Config.CATEGORY_GROUPS.values() for c in cats]
        assert sorted(grouped) == sorted(Config.CATEGORIES.keys())
        assert len(grouped) == len(set(grouped))

    def test_frequencies_parity(self):
        assert set(Config.NYT_CATEGORY_UPDATE_FREQUENCIES.keys()) == set(Config.CATEGORIES.keys())
        assert set(Config.NYT_CATEGORY_UPDATE_FREQUENCIES.values()) <= {'weekly', 'monthly'}

    def test_new_categories_monthly(self):
        freqs = Config.NYT_CATEGORY_UPDATE_FREQUENCIES
        for key in (
            'picture-books',
            'series-books',
            'business-books',
            'middle-grade-paperback-monthly',
            'young-adult-paperback-monthly',
        ):
            assert freqs[key] == 'monthly'

    def test_english_names_parity(self):
        assert set(Config.CATEGORY_NAMES_EN.keys()) == set(Config.CATEGORIES.keys())

    def test_js_labels_parity_with_config(self):
        """static/js/categories.js 的 LABELS 必须与 CATEGORIES 对齐，
        否则前端语言切换会把缺失项回退显示为 key 原文（#66 跟进教训）."""
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parent.parent / 'static' / 'js' / 'categories.js').read_text(encoding='utf-8')
        labels_block = src.split('var LABELS = {', 1)[1].split('};', 1)[0]
        js_keys = set(re.findall(r"'([a-z0-9-]+)':\s*\{", labels_block))
        assert js_keys == set(Config.CATEGORIES.keys())
        order_block = src.split('var ORDERED_IDS = [', 1)[1].split('];', 1)[0]
        js_order = re.findall(r"'([a-z0-9-]+)'", order_block)
        assert js_order == list(Config.CATEGORIES.keys())

    def test_js_labels_values_parity_with_config(self):
        """JS 的 zh/en 取值必须与 config 逐字一致（不只是 key 集合一致）.

        服务端按 `CATEGORY_NAMES_EN` 渲染首屏 option，客户端 `getCategoryLabel()` 会在语言切换时
        改写同一批 option。两边取值若不一致，用户会看到文本在 JS 跑完后"跳一下"；
        #235 落地 SSR 英文时就发现 `graphic-books-and-manga` 是 'and' vs '&' 不一致。
        """
        import json
        import re
        from pathlib import Path

        def _js_string(literal: str) -> str:
            """JS 字符串字面量 -> 值。双引号形式是合法 JSON，单引号形式不是。"""
            if literal.startswith('"'):
                return json.loads(literal)
            return literal[1:-1].replace("\\'", "'").replace('\\\\', '\\')

        src = (Path(__file__).resolve().parent.parent / 'static' / 'js' / 'categories.js').read_text(encoding='utf-8')
        labels_block = src.split('var LABELS = {', 1)[1].split('};', 1)[0]

        # JS 值有单引号也有双引号（含撇号时用双引号），两种都要能解析
        pairs = re.findall(
            r"'([a-z0-9-]+)':\s*\{\s*zh:\s*(\"[^\"]*\"|'[^']*')\s*,\s*en:\s*(\"[^\"]*\"|'[^']*')\s*\}",
            labels_block,
        )
        js = {k: (_js_string(z), _js_string(e)) for k, z, e in pairs}
        assert set(js) == set(Config.CATEGORIES.keys()), (
            f'JS LABELS not parsed for all categories: {set(Config.CATEGORIES) - set(js)}'
        )

        for key, (zh, en) in js.items():
            assert zh == Config.CATEGORIES[key], f'{key}: JS zh={zh!r} != config {Config.CATEGORIES[key]!r}'
            assert en == Config.CATEGORY_NAMES_EN[key], (
                f'{key}: JS en={en!r} != config {Config.CATEGORY_NAMES_EN[key]!r}'
            )


class TestCrossCategorySearch:
    @patch('app.routes.main.get_service')
    def test_search_queries_all_categories(self, mock_get_svc, client):
        """?search= 应跨全部分类，结果带来源分类，详情链指向来源分类."""
        mock_get_svc.return_value = _mock_book_service(
            {
                'hardcover-fiction': [_make_book(title='Python Programming', rank=1)],
                'business-books': [
                    _make_book(
                        title='Python for Business',
                        rank=2,
                        list_name='Business Books',
                        category_id='business-books',
                        category_name='商业',
                        isbn13='9780000000001',
                        isbn10='0000000001',
                        id='9780000000001',
                    )
                ],
            }
        )
        resp = client.get('/?search=Python', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Python Programming' in html
        assert 'Python for Business' in html
        # 详情链分别指向各自来源分类
        assert '/book/0?category=hardcover-fiction' in html
        assert '/book/1?category=business-books' in html

    @patch('app.routes.main.get_service')
    def test_search_without_query_stays_single_category(self, mock_get_svc, client):
        """无搜索词时保持单分类行为，不触发全量抓取."""
        svc = _mock_book_service({'hardcover-fiction': [_make_book()]})
        mock_get_svc.return_value = svc
        resp = client.get('/?category=hardcover-fiction', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        assert svc.get_books_by_category.call_count == 1

    @patch('app.routes.main.get_service')
    def test_desktop_category_select_grouped(self, mock_get_svc, client):
        """桌面端分类下拉按体裁分组，月榜标注更新频率."""
        mock_get_svc.return_value = _mock_book_service({'hardcover-fiction': [_make_book()]})
        resp = client.get('/?lang=zh', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '<optgroup' in html
        assert '儿童与青少年' in html
        assert '(每月)' in html

    @patch('app.routes.main.get_service')
    def test_desktop_category_select_follows_locale(self, mock_get_svc, client):
        """分类下拉跟随 locale：英文页首屏即英文（#235 反转了旧行为）.

        此前本用例断言「分类下拉恒为中文（即使英文 locale）」，把当时的行为固化了：
        SSR 一律输出中文，只靠 index.js 的 `updateCategorySelectOptions()` 在语言切换时改写
        option 文本。但该函数只在 `setGlobalLanguage` 路径里被调用，**首屏加载不调用**，
        于是 `?lang=en` 首屏始终是中文（浏览器实测可见中文 4 字符），这正是不该有的泄漏。

        现在改为 SSR 按 locale 取值 —— 与站内其它 `_()` 文案一致，且不依赖 JS；
        客户端 `categories.js` 仍会在切换语言时改写，两边取值已由
        `test_js_labels_values_parity_with_config` 保证一致，不会出现切换后闪动。
        """
        mock_get_svc.return_value = _mock_book_service({'hardcover-fiction': [_make_book()]})
        resp = client.get('/?lang=en', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Hardcover Fiction' in html
        assert '精装小说' not in html

    @patch('app.routes.main.get_service')
    def test_desktop_category_select_chinese_locale(self, mock_get_svc, client):
        """中文页仍显示中文分类名."""
        mock_get_svc.return_value = _mock_book_service({'hardcover-fiction': [_make_book()]})
        resp = client.get('/?lang=zh', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '精装小说' in html

    @patch('app.routes.main.get_service')
    def test_mobile_category_tabs_follow_locale(self, mock_get_svc, client):
        """移动端 tabs 与桌面下拉同源：英文页首屏即英文，中文页仍是中文.

        #188 原文明确规定「分类下拉（桌面）与 tabs（移动）恒显示中文」，#235 反转该决定时
        只改了桌面半边 —— 本用例锁住两端一致，避免再次出现「桌面英文、移动中文」的半套状态。
        """
        mock_get_svc.return_value = _mock_book_service({'hardcover-fiction': [_make_book()]})

        en = client.get('/?lang=en', headers={'User-Agent': MOBILE_UA}).data.decode('utf-8')
        tabs_en = _mobile_tabs(en)
        assert tabs_en, '移动端分类 tabs 未渲染'
        assert 'Hardcover Fiction' in tabs_en
        assert '精装小说' not in tabs_en
        assert 'aria-label="Category"' in tabs_en  # 读屏语言也得跟随 locale

        zh = client.get('/?lang=zh', headers={'User-Agent': MOBILE_UA}).data.decode('utf-8')
        tabs_zh = _mobile_tabs(zh)
        assert '精装小说' in tabs_zh
        assert 'Hardcover Fiction' not in tabs_zh
        assert 'aria-label="图书分类"' in tabs_zh


class TestOnDemandTranslationMarker:
    @patch('app.routes.main.get_service')
    def test_untranslated_books_marked(self, mock_get_svc, client):
        """无 title_zh 的书打标 data-needs-translation，有的不打."""
        mock_get_svc.return_value = _mock_book_service(
            {
                'hardcover-fiction': [
                    _make_book(title_zh=None, isbn13='9780000000001', isbn10='0000000001', id='9780000000001'),
                    _make_book(
                        title_zh='中文标题',
                        isbn13='9780000000002',
                        isbn10='0000000002',
                        id='9780000000002',
                    ),
                ]
            }
        )
        resp = client.get('/?lang=zh', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert html.count('data-needs-translation="1"') == 1  # 当前视图下一本未翻译


class TestMobileSearchEntry:
    @patch('app.routes.main.get_service')
    def test_mobile_has_search_toggle(self, mock_get_svc, client):
        """移动端首页有搜索图标入口（同页展开）."""
        mock_get_svc.return_value = _mock_book_service({'hardcover-fiction': [_make_book()]})
        resp = client.get('/', headers={'User-Agent': MOBILE_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'm-search-toggle' in html
        assert 'm-search-input' in html
        assert 'name="search"' in html
