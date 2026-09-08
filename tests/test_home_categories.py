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
    def test_desktop_category_select_always_chinese(self, mock_get_svc, client):
        """分类下拉恒为中文（即使英文 locale）."""
        mock_get_svc.return_value = _mock_book_service({'hardcover-fiction': [_make_book()]})
        resp = client.get('/?lang=en', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '精装小说' in html
        assert 'Middle Grade Paperback' not in html


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
