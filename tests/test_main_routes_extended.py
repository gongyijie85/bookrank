"""main.py 路由扩展测试 — 覆盖现有测试未覆盖的路由和代码路径"""

import json
import re
from datetime import UTC
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import MultiDict

from app.models.book import Book
from app.routes.main import _load_new_books_data, _parse_new_books_params


def _make_book(**overrides):
    defaults = {
        'id': '9780143127550',
        'title': 'Test Book',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'cover': '',
        'list_name': 'Hardcover Fiction',
        'category_id': 'hardcover-fiction',
        'category_name': 'Hardcover Fiction',
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
    svc = MagicMock()
    svc.get_books_by_category.return_value = books or []
    svc.get_cache_time.return_value = '2024-01-14'
    svc.get_latest_cache_time.return_value = '2024-01-14'
    svc.search_books.return_value = []
    return svc


def _parse_cookie_value(response, name):
    """从 Set-Cookie 头中解析指定名称的 cookie 值"""
    for header in response.headers.getlist('Set-Cookie'):
        if header.startswith(f'{name}='):
            return header.split(';')[0].split('=', 1)[1]
    return None


class TestCachedImage:
    def test_valid_filename_format_returns_404_when_file_missing(self, client):
        valid_hash = 'a' * 32 + '.jpg'
        response = client.get(f'/cache/images/{valid_hash}')
        assert response.status_code == 404

    def test_invalid_format_short_hash(self, client):
        response = client.get('/cache/images/abc.jpg')
        assert response.status_code == 404

    def test_invalid_format_no_extension(self, client):
        response = client.get('/cache/images/' + 'a' * 32)
        assert response.status_code == 404

    def test_path_traversal_with_valid_length(self, client):
        filename = '../' * 5 + 'a' * 20 + '.jpg'
        response = client.get(f'/cache/images/{filename}')
        assert response.status_code == 404


class TestAwardBookCover:
    @patch('app.services.award_cover_sync_service.AwardCoverSyncService')
    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_google_books_client')
    def test_cover_resolved_successfully(self, mock_gbc, mock_ics, MockACSS, client, app, db):
        from app.models.schemas import Award, AwardBook

        with app.app_context():
            award = Award(name='TestAward', name_en='Test Award')
            db.session.add(award)
            db.session.flush()
            book = AwardBook(
                award_id=award.id,
                year=2024,
                title='Book',
                author='Author',
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()
            book_id = book.id

        mock_sync = MagicMock()
        mock_sync._resolver.resolve.return_value = 'https://example.com/cover.jpg'
        MockACSS.return_value = mock_sync
        response = client.get(f'/award-book/{book_id}/cover')
        assert response.status_code == 302
        # 解析结果仍是外链时不再 302 到境外图床（国内必然失败），改投同源代理
        assert response.location.startswith('/cover?src=')
        assert 'example.com' in response.location

    @patch('app.services.award_cover_sync_service.AwardCoverSyncService')
    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_google_books_client')
    def test_cover_resolved_to_local_cache_is_served_inline(
        self, mock_gbc, mock_ics, MockACSS, client, app, db, tmp_path
    ):
        """解析结果已落到本地缓存时直接下发字节，省掉一次 302 往返。"""
        from app.models.schemas import Award, AwardBook

        with app.app_context():
            award = Award(name='TestAwardLocal', name_en='Test Award Local')
            db.session.add(award)
            db.session.flush()
            book = AwardBook(award_id=award.id, year=2024, title='BookL', author='AuthorL', is_displayable=True)
            db.session.add(book)
            db.session.commit()
            book_id = book.id

        cache_dir = tmp_path / 'images'
        cache_dir.mkdir(parents=True, exist_ok=True)
        filename = 'd' * 32 + '.jpg'
        (cache_dir / filename).write_bytes(b'\xff\xd8\xff' + b'0' * 4096)

        mock_sync = MagicMock()
        mock_sync._resolver.resolve.return_value = f'/cache/images/{filename}'
        MockACSS.return_value = mock_sync

        original_dir = app.config.get('IMAGE_CACHE_DIR')
        app.config['IMAGE_CACHE_DIR'] = cache_dir
        try:
            response = client.get(f'/award-book/{book_id}/cover')
        finally:
            app.config['IMAGE_CACHE_DIR'] = original_dir

        assert response.status_code == 200
        assert response.mimetype == 'image/jpeg'
        assert response.headers['X-Cover-Source'] == 'cache'

    @patch('app.services.award_cover_sync_service.AwardCoverSyncService')
    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_google_books_client')
    def test_cover_resolve_fails_fallback_to_original(self, mock_gbc, mock_ics, MockACSS, client, app, db):
        from app.models.schemas import Award, AwardBook

        with app.app_context():
            award = Award(name='TestAward2', name_en='Test Award 2')
            db.session.add(award)
            db.session.flush()
            book = AwardBook(
                award_id=award.id,
                year=2024,
                title='Book2',
                author='Author2',
                cover_original_url='https://example.com/original.jpg',
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()
            book_id = book.id

        mock_sync = MagicMock()
        mock_sync._resolver.resolve.side_effect = Exception('API Error')
        MockACSS.return_value = mock_sync
        response = client.get(f'/award-book/{book_id}/cover')
        assert response.status_code == 302
        assert 'original.jpg' in response.location

    @patch('app.services.award_cover_sync_service.AwardCoverSyncService')
    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_google_books_client')
    def test_cover_resolve_fails_no_original_url(self, mock_gbc, mock_ics, MockACSS, client, app, db):
        from app.models.schemas import Award, AwardBook

        with app.app_context():
            award = Award(name='TestAward3', name_en='Test Award 3')
            db.session.add(award)
            db.session.flush()
            book = AwardBook(
                award_id=award.id,
                year=2024,
                title='Book3',
                author='Author3',
                cover_original_url='  ',
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()
            book_id = book.id

        mock_sync = MagicMock()
        mock_sync._resolver.resolve.side_effect = Exception('API Error')
        MockACSS.return_value = mock_sync
        response = client.get(f'/award-book/{book_id}/cover')
        assert response.status_code == 302
        assert 'no-store' in response.headers.get('Cache-Control', '')


class TestAwardsPage:
    def test_awards_default_render(self, client):
        response = client.get('/awards')
        assert response.status_code == 200

    def test_awards_page_declares_utf8_and_preserves_chinese(self, client):
        response = client.get('/awards?lang=zh')
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert response.headers['Content-Type'].startswith('text/html; charset=utf-8')
        assert '<meta charset="UTF-8">' in html
        assert '获奖书单' in html

    def test_awards_with_view_list(self, client):
        response = client.get('/awards?view=list')
        assert response.status_code == 200

    def test_awards_with_invalid_view(self, client):
        response = client.get('/awards?view=invalid')
        assert response.status_code == 200

    def test_awards_with_valid_year(self, client):
        response = client.get('/awards?year=2024')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_year_select_marks_selected_option(self, MockAwardService, client):
        """ADDITIONAL：?year=2026 时 #year-select 应渲染对应 option 为 selected。

        _parse_awards_params 把 year 规范为 int，模板 `selected_year == year`（years 是
        int 列表）才成立；否则会出现 chip 显示 2026 但下拉无选中项，再改别的筛选就
        会静默丢掉年份。
        """
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.book_count = 0
        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = [mock_award]
        mock_svc.get_distinct_years.return_value = [2026]
        mock_svc.get_distinct_categories.return_value = ['小说']
        mock_svc.get_award_by_name.return_value = mock_award
        mock_svc.get_award_books.return_value = ([], 0)
        mock_svc.get_book_counts_by_award.return_value = {}
        MockAwardService.return_value = mock_svc

        response = client.get('/awards?award=布克奖&year=2026&category=小说')
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert '<option value="2026" selected>' in html
        # 年份筛选 chip 仍在（移除 chip 的链接保留 year=2026 与 category=小说）
        assert '2026' in html

    def test_awards_with_year_too_old(self, client):
        response = client.get('/awards?year=1800')
        assert response.status_code == 200

    def test_awards_with_year_too_future(self, client):
        response = client.get('/awards?year=2200')
        assert response.status_code == 200

    def test_awards_with_invalid_year(self, client):
        response = client.get('/awards?year=abc')
        assert response.status_code == 200

    def test_awards_with_search(self, client):
        response = client.get('/awards?search=test')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_awards_list_exception(self, MockAwardService, client):
        mock_svc = MagicMock()
        mock_svc.get_all_awards.side_effect = Exception('DB error')
        mock_svc.get_distinct_years.return_value = []
        mock_svc.get_award_books.return_value = ([], 0)
        mock_svc.get_book_counts_by_award.return_value = {}
        MockAwardService.return_value = mock_svc
        response = client.get('/awards')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_years_list_exception(self, MockAwardService, client):
        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = []
        mock_svc.get_distinct_years.side_effect = Exception('DB error')
        mock_svc.get_award_books.return_value = ([], 0)
        mock_svc.get_book_counts_by_award.return_value = {}
        MockAwardService.return_value = mock_svc
        response = client.get('/awards')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_books_load_exception(self, MockAwardService, client):
        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = []
        mock_svc.get_distinct_years.return_value = []
        mock_svc.get_award_books.side_effect = Exception('DB error')
        MockAwardService.return_value = mock_svc
        mock_render = MagicMock(return_value='ok')
        with patch('app.routes.main.render_adaptive', mock_render):
            response = client.get('/awards')
        assert response.status_code == 200
        _, kwargs = mock_render.call_args
        assert kwargs['data_load_failed'] is True
        assert kwargs['total_books'] is None
        assert kwargs['total_pages'] is None

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_with_award_name_filter(self, MockAwardService, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award.wikidata_id = None
        mock_award.description = 'desc'
        mock_award.book_count = 0

        mock_book = MagicMock()
        mock_book.id = 10
        mock_book.title = 'Test Title'
        mock_book.title_zh = None
        mock_book.display_title = 'Test Title'
        mock_book.author = 'Author'
        mock_book.description = 'desc'
        mock_book.description_zh = None
        mock_book.details = 'details'
        mock_book.cover_local_path = None
        mock_book.cover_original_url = None
        mock_book.isbn13 = '9780000000001'
        mock_book.isbn10 = None
        mock_book.publisher = 'Pub'
        mock_book.publication_year = 2024
        mock_book.year = 2024
        mock_book.category = 'fiction'
        mock_book.award = mock_award
        mock_book.buy_links = []

        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = [mock_award]
        mock_svc.get_distinct_years.return_value = [2024]
        mock_svc.get_award_by_name.return_value = mock_award
        mock_svc.get_award_books.return_value = ([mock_book], 1)
        mock_svc.get_book_counts_by_award.return_value = {1: 1}
        MockAwardService.return_value = mock_svc

        response = client.get('/awards?award=TestAward')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_with_category_filter(self, MockAwardService, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award.wikidata_id = None
        mock_award.book_count = 0

        mock_book = MagicMock()
        mock_book.id = 10
        mock_book.title = 'Test Title'
        mock_book.author = 'Author'
        mock_book.description = 'desc'
        mock_book.description_zh = None
        mock_book.details = 'details'
        mock_book.cover_local_path = None
        mock_book.cover_original_url = None
        mock_book.isbn13 = '9780000000001'
        mock_book.isbn10 = None
        mock_book.publisher = 'Pub'
        mock_book.publication_year = 2024
        mock_book.year = 2024
        mock_book.category = 'Fiction'
        mock_book.title_zh = None
        mock_book.display_title = 'Test Title'
        mock_book.award = mock_award
        mock_book.buy_links = []

        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = [mock_award]
        mock_svc.get_distinct_years.return_value = [2024]
        mock_svc.get_distinct_categories.return_value = ['Fiction', 'Non-fiction']
        mock_svc.get_award_by_name.return_value = mock_award
        mock_svc.get_award_books.return_value = ([mock_book], 1)
        mock_svc.get_book_counts_by_award.return_value = {1: 1}
        MockAwardService.return_value = mock_svc

        response = client.get('/awards?category=Fiction')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'Fiction' in html
        assert 'Test Title' in html

        # category 参数应传给服务层查询方法
        _, kwargs = mock_svc.get_award_books.call_args
        assert kwargs.get('category') == 'Fiction'

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_with_award_and_category_intersection(self, MockAwardService, client):
        """奖项 + 类别同时筛选时,两个条件都应传给服务层（交集，而非互相覆盖）"""
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.book_count = 0

        mock_svc = MagicMock()
        mock_svc.get_all_awards.return_value = [mock_award]
        mock_svc.get_distinct_years.return_value = []
        mock_svc.get_distinct_categories.return_value = ['Fiction']
        mock_svc.get_award_by_name.return_value = mock_award
        mock_svc.get_award_books.return_value = ([], 0)
        mock_svc.get_book_counts_by_award.return_value = {}
        MockAwardService.return_value = mock_svc

        response = client.get('/awards?award=TestAward&category=Fiction')
        assert response.status_code == 200

        _, kwargs = mock_svc.get_award_books.call_args
        assert kwargs.get('award_id') == 1
        assert kwargs.get('category') == 'Fiction'


class TestNewBooksPage:
    def test_new_books_default(self, client):
        response = client.get('/new-books')
        assert response.status_code == 200

    def test_new_books_with_publisher(self, client):
        response = client.get('/new-books?publisher=abc')
        assert response.status_code == 200

    def test_new_books_with_category(self, client):
        response = client.get('/new-books?category=fiction')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_raw_english_category_selects_canonical_option(self, mock_get_modules, client):
        """audit08：?category=Health & Fitness（旧英文 URL）应选中规范选项并显示规范 chip。

        路由把原始英文分类归一为规范显示键（健康养生），否则下拉无选中项、chip 显示英文，
        且已入库的英文记录会从筛选中消失。
        """
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.return_value = None
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.return_value = [
            {'name': '健康养生', 'count': 2},
            {'name': '小说', 'count': 1},
        ]
        mock_modules.query_service.get_statistics.return_value = {
            'total_books': 3,
            'total_publishers': 1,
            'active_publishers': 1,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_modules.query_service.get_new_books.return_value = ([], 0)
        mock_get_modules.return_value = mock_modules

        response = client.get('/new-books?category=Health%20%26%20Fitness')
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        # 规范选项被选中（而非英文原始值）
        assert 'value="健康养生" selected' in html
        # 筛选 chip 显示规范显示名
        assert '健康养生' in html

    def test_new_books_with_days(self, client):
        response = client.get('/new-books?days=7')
        assert response.status_code == 200

    def test_new_books_days_clamp_min(self, client):
        response = client.get('/new-books?days=-5')
        assert response.status_code == 200

    def test_new_books_days_clamp_max(self, client):
        response = client.get('/new-books?days=999')
        assert response.status_code == 200

    def test_new_books_with_search(self, client):
        response = client.get('/new-books?search=python')
        assert response.status_code == 200

    def test_new_books_with_page(self, client):
        response = client.get('/new-books?page=2')
        assert response.status_code == 200

    def test_new_books_page_clamp(self, client):
        response = client.get('/new-books?page=0')
        assert response.status_code == 200

    def test_new_books_view_list(self, client):
        response = client.get('/new-books?view=list')
        assert response.status_code == 200

    def test_new_books_view_invalid(self, client):
        response = client.get('/new-books?view=invalid')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_service_ensure_fails(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.side_effect = Exception('seed error')
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.return_value = []
        mock_modules.query_service.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_modules.query_service.get_new_books.return_value = ([], 0)
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_publishers_exception(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.return_value = None
        mock_modules.publisher_manager.get_publishers.side_effect = Exception('db error')
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.return_value = []
        mock_modules.query_service.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_modules.query_service.get_new_books.return_value = ([], 0)
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_categories_exception(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.return_value = None
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.side_effect = Exception('db error')
        mock_modules.query_service.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_modules.query_service.get_new_books.return_value = ([], 0)
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_statistics_exception(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.return_value = None
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.return_value = []
        mock_modules.query_service.get_statistics.side_effect = Exception('db error')
        mock_modules.query_service.get_new_books.return_value = ([], 0)
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_get_books_exception(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.return_value = None
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.return_value = []
        mock_modules.query_service.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_modules.query_service.get_new_books.side_effect = Exception('db error')
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_new_books_search_path(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.sync_engine.ensure_static_data_seeded.return_value = None
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_modules.publisher_manager.get_publisher_book_counts.return_value = {}
        mock_modules.query_service.get_categories.return_value = []
        mock_modules.query_service.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_modules.query_service.search_books.return_value = ([], 0)
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-books?search=test')
        assert response.status_code == 200
        mock_modules.query_service.search_books.assert_called_once()

    def test_new_books_ssr_card_shows_freshness_badge(self, client, app, db):
        """首屏 SSR 渲染的卡片也应该有"刚上市"徽章，和 AJAX 局部刷新保持一致"""
        from datetime import date

        from app.models.new_book import NewBook, Publisher

        with app.app_context():
            publisher = Publisher(name='测试出版社', name_en='SSR Test Publisher', crawler_class='TestCrawler')
            db.session.add(publisher)
            db.session.commit()

            book = NewBook(
                publisher_id=publisher.id,
                title='Freshly Published Book',
                author='Test Author',
                isbn13='9780000000501',
                category='Fiction',
                publication_date=date.today(),
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()

        response = client.get('/new-books?days=365')
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        # 只检查 #books-container 内服务端渲染出的卡片标记本身；书页内联的
        # <script> 源码也含有同样的 class 名字符串，不能作为渲染证据（会造成假阳性）。
        rendered_markup = html.split('id="books-container"', 1)[1].split('<script', 1)[0]
        assert 'books-grid' in rendered_markup
        assert 'tag-new' in rendered_markup

    def test_new_books_ssr_card_shows_muted_placeholders_for_missing_info(self, client, app, db):
        """分类/出版日期缺失时，首屏卡片应显示占位标签，而不是整段不渲染"""
        from app.models.new_book import NewBook, Publisher

        with app.app_context():
            publisher = Publisher(name='测试出版社', name_en='SSR Test Publisher 2', crawler_class='TestCrawler')
            db.session.add(publisher)
            db.session.commit()

            book = NewBook(
                publisher_id=publisher.id,
                title='No Metadata Book',
                author='Test Author',
                isbn13='9780000000502',
                category=None,
                publication_date=None,
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()

        response = client.get('/new-books?days=365')
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        rendered_markup = html.split('id="books-container"', 1)[1].split('<script', 1)[0]
        assert 'books-grid' in rendered_markup
        assert 'tag-muted' in rendered_markup


class TestNewBookDetail:
    @patch('app.routes.main.get_new_book_modules')
    def test_book_not_found(self, mock_get_modules, client):
        mock_modules = MagicMock()
        mock_modules.query_service.get_book.return_value = None
        mock_get_modules.return_value = mock_modules
        response = client.get('/new-book/999')
        assert response.status_code == 404

    @patch('app.routes.main.submit_background_task')
    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_new_book_modules')
    def test_book_found_needs_translation(self, mock_get_modules, mock_trans, mock_bg, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Title'
        mock_book.title_zh = None
        mock_book.description_zh = None
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.description = 'Test description'
        mock_book.cover_url = 'http://example.com/cover.jpg'
        mock_book.publisher = None
        mock_modules = MagicMock()
        mock_modules.query_service.get_book.return_value = mock_book
        mock_get_modules.return_value = mock_modules
        mock_trans.return_value = MagicMock()

        response = client.get('/new-book/1')
        assert response.status_code == 200
        mock_bg.assert_called_once()

    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_new_book_modules')
    def test_book_found_already_translated(self, mock_get_modules, mock_trans, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Title'
        mock_book.title_zh = '已翻译'
        mock_book.description_zh = '已翻译描述'
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.description = 'Test description'
        mock_book.cover_url = 'http://example.com/cover.jpg'
        mock_book.publisher = None
        mock_modules = MagicMock()
        mock_modules.query_service.get_book.return_value = mock_book
        mock_get_modules.return_value = mock_modules

        response = client.get('/new-book/1')
        assert response.status_code == 200

    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_new_book_modules')
    def test_book_found_no_translation_service(self, mock_get_modules, mock_trans, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Title'
        mock_book.title_zh = None
        mock_book.description_zh = None
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.description = 'Test description'
        mock_book.cover_url = 'http://example.com/cover.jpg'
        mock_book.publisher = None
        mock_modules = MagicMock()
        mock_modules.query_service.get_book.return_value = mock_book
        mock_get_modules.return_value = mock_modules
        mock_trans.return_value = None

        response = client.get('/new-book/1')
        assert response.status_code == 200

    @patch('app.routes.main.get_service')
    @patch('app.routes.main.get_new_book_modules')
    def test_book_found_partial_translation(self, mock_get_modules, mock_trans, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Title'
        mock_book.title_zh = '已翻译'
        mock_book.description_zh = None
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.description = 'Test description'
        mock_book.cover_url = 'http://example.com/cover.jpg'
        mock_book.publisher = None
        mock_modules = MagicMock()
        mock_modules.query_service.get_book.return_value = mock_book
        mock_get_modules.return_value = mock_modules
        mock_trans.return_value = MagicMock()

        response = client.get('/new-book/1')
        assert response.status_code == 200


class TestAwardBookDetail:
    @patch('app.services.award_book_service.AwardBookService')
    def test_award_book_found(self, MockAwardService, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Book Title'
        mock_book.title_zh = '测试书名'
        mock_book.is_displayable = True
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.publisher = 'Test Publisher'
        mock_book.description = 'Test description'
        mock_book.award = None
        mock_book.display_title = 'Test Book Title'
        mock_svc = MagicMock()
        mock_svc.get_award_book_by_id.return_value = mock_book
        MockAwardService.return_value = mock_svc
        response = client.get('/award-book/1')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_award_book_not_found(self, MockAwardService, client):
        mock_svc = MagicMock()
        mock_svc.get_award_book_by_id.return_value = None
        MockAwardService.return_value = mock_svc
        response = client.get('/award-book/99999')
        assert response.status_code == 404

    @patch('app.routes.main.get_or_create_recommendation_service')
    @patch('app.services.award_book_service.AwardBookService')
    def test_award_book_detail_shows_related_books_when_available(self, MockAwardService, mock_get_rec_svc, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Book Title'
        mock_book.title_zh = '测试书名'
        mock_book.is_displayable = True
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.publisher = 'Test Publisher'
        mock_book.description = 'Test description'
        mock_book.award = None
        mock_book.display_title = 'Test Book Title'
        mock_svc = MagicMock()
        mock_svc.get_award_book_by_id.return_value = mock_book
        MockAwardService.return_value = mock_svc

        mock_rec_svc = MagicMock()
        mock_rec_svc.get_similarity_recommendations.return_value = {
            'recommendations': [
                {
                    'id': 2,
                    'title': 'Related Book Title',
                    'title_zh': '相关图书标题',
                    'author': 'Related Author',
                    'year': 2023,
                    'category': 'Fiction',
                    'cover_url': None,
                    'isbn13': '9789999999999',
                }
            ],
            'reason': '同奖项其他年份获奖图书',
        }
        mock_get_rec_svc.return_value = mock_rec_svc

        response = client.get('/award-book/1')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert '<section class="related-award-books"' in html
        assert 'Related Book Title' in html

        mock_rec_svc.get_similarity_recommendations.assert_called_once_with(book_id=1)

    @patch('app.routes.main.get_or_create_recommendation_service')
    @patch('app.services.award_book_service.AwardBookService')
    def test_award_book_detail_hides_related_section_when_empty(self, MockAwardService, mock_get_rec_svc, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test Book Title'
        mock_book.title_zh = '测试书名'
        mock_book.is_displayable = True
        mock_book.author = 'Test Author'
        mock_book.isbn13 = '9781234567890'
        mock_book.publisher = 'Test Publisher'
        mock_book.description = 'Test description'
        mock_book.award = None
        mock_book.display_title = 'Test Book Title'
        mock_svc = MagicMock()
        mock_svc.get_award_book_by_id.return_value = mock_book
        MockAwardService.return_value = mock_svc

        mock_rec_svc = MagicMock()
        mock_rec_svc.get_similarity_recommendations.return_value = {'recommendations': [], 'reason': ''}
        mock_get_rec_svc.return_value = mock_rec_svc

        response = client.get('/award-book/1')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert '<section class="related-award-books"' not in html


class TestBookDetail:
    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    def test_valid_book_index(self, mock_fetch, mock_merge, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/book/0?category=hardcover-fiction')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    def test_invalid_category_fallback(self, mock_fetch, mock_merge, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/book/0?category=nonexistent')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_no_isbn_skips_fetch(self, client, app):
        book = _make_book(isbn13='', isbn10='')
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/book/0')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_book_service_none_returns_empty(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        response = client.get('/book/0')
        assert response.status_code == 404


class TestBookDetailsApi:
    def test_success(self, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/book-details?book_index=0&isbn=9780143127550&category=hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert 'details' in data['data']
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_book_not_found(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/book-details?book_index=0&isbn=9780000000000')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 404
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_missing_isbn(self, client):
        resp = client.get('/api/book-details?book_index=0')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 400


class TestApiCategoryBooks:
    def test_success_with_mock_service(self, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/category-books?category=hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert len(data['data']['books']) == 1
            assert data['data']['category'] == 'hardcover-fiction'
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_monthly_category_returns_frequency_metadata(self, client, app):
        book = _make_book(
            category_id='graphic-books-and-manga',
            category_name='漫画与绘本',
            list_name='Graphic Books and Manga',
            published_date='2026-06-01',
        )
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/category-books?category=graphic-books-and-manga')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert data['data']['update_frequency'] == 'monthly'
            assert data['data']['list_published_date'] == '2026-06-01'
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_weekly_category_returns_frequency_metadata(self, client, app):
        book = _make_book(published_date='2026-07-05')
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/category-books?category=hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert data['data']['update_frequency'] == 'weekly'
            assert data['data']['list_published_date'] == '2026-07-05'
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_service_returns_none(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/category-books?category=hardcover-fiction')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['data']['books'] == []

    def test_service_exception(self, client, app):
        mock_svc = MagicMock()
        mock_svc.get_books_by_category.side_effect = Exception('Service crashed')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/category-books?category=hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert data['data']['books'] == []
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_outer_exception(self, client, app):
        mock_svc = MagicMock()
        mock_svc.get_books_by_category.side_effect = Exception('Error')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/category-books?category=hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestWeeklyReports:
    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        response = client.get('/reports/weekly')
        assert response.status_code == 200

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_with_reports(self, MockWRS, client, app):
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {'id': 1}
        mock_report.content = '{"key": "value"}'

        mock_svc = MagicMock()
        # v0.9.47 自愈机制：route 额外调用 get_or_trigger_current_week_report() 返回 2-tuple
        mock_svc.get_or_trigger_current_week_report.return_value = (mock_report, False)
        mock_svc.get_reports.return_value = [mock_report]
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_empty_reports_triggers_generation(self, MockWRS, client, app):
        mock_svc = MagicMock()
        # v0.9.47 自愈机制：缺失周报时返回 (None, True) 标记后台补生成中
        mock_svc.get_or_trigger_current_week_report.return_value = (None, True)
        mock_svc.get_reports.return_value = []
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            with patch('app.tasks.weekly_report_task.generate_weekly_report') as mock_gen:
                mock_gen.return_value = MagicMock()
                mock_svc.get_reports.return_value = [MagicMock(content='{}')]
                response = client.get('/reports/weekly')
                assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_generation_exception(self, MockWRS, client, app):
        mock_svc = MagicMock()
        # v0.9.47 自愈机制：自愈检查自身出错时返回 (latest, False)
        mock_svc.get_or_trigger_current_week_report.return_value = (None, False)
        mock_svc.get_reports.return_value = []
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            with patch('app.tasks.weekly_report_task.generate_weekly_report', side_effect=Exception('gen error')):
                response = client.get('/reports/weekly')
                assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestWeeklyReportDetail:
    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        response = client.get('/reports/weekly/2024-01-15')
        assert response.status_code == 200

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_report_not_found(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = None
        mock_svc.get_report_by_date.return_value = None
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.routes.main.parse_report_content')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_report_found_success(self, MockWRS, mock_parse, client, app):
        mock_report = MagicMock()
        mock_report.id = 1
        mock_report.title = 'Test Report'
        mock_report.summary = 'Test summary'
        mock_report.conclusion = 'Test conclusion'
        mock_report.next_week_outlook = 'Outlook'
        mock_report.market_events = 'Events'
        mock_report.strategy_adjustments = 'Strategy'
        mock_report.generated_at = '2024-01-15'
        mock_report.view_count = 0
        mock_report.export_count = 0
        mock_report.version = 1
        mock_report.is_draft = False
        mock_report.is_favorite = False

        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        mock_parse.return_value = {'summary': 'test'}
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15')
            assert response.status_code == 200
            mock_svc.record_report_view.assert_called_once()
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_report_fallback_to_get_by_date(self, MockWRS, client, app):
        mock_report = MagicMock()
        mock_report.id = 2
        mock_report.title = 'Fallback Report'
        mock_report.summary = 'Fallback summary'
        mock_report.conclusion = ''
        mock_report.next_week_outlook = ''
        mock_report.market_events = ''
        mock_report.strategy_adjustments = ''
        mock_report.generated_at = '2024-01-15'
        mock_report.view_count = 0
        mock_report.export_count = 0
        mock_report.version = 1
        mock_report.is_draft = False
        mock_report.is_favorite = False

        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = None
        mock_svc.get_report_by_date.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            with patch('app.routes.main.parse_report_content', return_value={}):
                response = client.get('/reports/weekly/2024-01-15')
                assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_report_view_exception(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.side_effect = Exception('db error')
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15')
            assert response.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestExportWeeklyReport:
    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        response = client.get('/reports/weekly/2024-01-15/export')
        assert response.status_code == 200

    def test_invalid_date(self, client, app):
        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/invalid-date/export')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_report_not_found(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = None
        mock_svc.get_report_by_date.return_value = None
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15/export')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_unsupported_format(self, MockWRS, client, app):
        mock_report = MagicMock()
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15/export?format=csv')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('flask.send_file')
    @patch('app.services.export_service.ExportService')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_pdf_export_success(self, MockWRS, MockES, mock_send_file, client, app):
        mock_report = MagicMock()
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_export_svc = MagicMock()
        mock_export_svc.export_weekly_report_pdf.return_value = BytesIO(b'pdf content')
        MockES.return_value = mock_export_svc

        mock_send_file.return_value = MagicMock(status_code=200)

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15/export?format=pdf')
            mock_svc.record_report_export.assert_called_once()
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.export_service.ExportService')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_pdf_export_buffer_none(self, MockWRS, MockES, client, app):
        mock_report = MagicMock()
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_export_svc = MagicMock()
        mock_export_svc.export_weekly_report_pdf.return_value = None
        MockES.return_value = mock_export_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15/export?format=pdf')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.export_service.ExportService')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_excel_export_buffer_none(self, MockWRS, MockES, client, app):
        mock_report = MagicMock()
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_export_svc = MagicMock()
        mock_export_svc.export_weekly_report_excel.return_value = None
        MockES.return_value = mock_export_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15/export?format=excel')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.export_service.ExportService')
    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_export_exception(self, MockWRS, MockES, client, app):
        mock_svc = MagicMock()
        mock_svc.get_report_by_week_end.side_effect = Exception('export error')
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            response = client.get('/reports/weekly/2024-01-15/export?format=pdf')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestSetLanguage:
    def test_sets_cookie_en(self, client):
        response = client.get('/set-language?lang=en&next=/')
        assert response.status_code == 302
        cookie_val = _parse_cookie_value(response, 'lang')
        assert cookie_val == 'en'

    def test_sets_cookie_zh(self, client):
        response = client.get('/set-language?lang=zh&next=/about')
        assert response.status_code == 302
        cookie_val = _parse_cookie_value(response, 'lang')
        assert cookie_val == 'zh'

    def test_invalid_lang_defaults_to_en(self, client):
        response = client.get('/set-language?lang=fr&next=/')
        cookie_val = _parse_cookie_value(response, 'lang')
        assert cookie_val == 'en'

    def test_default_lang_is_en(self, client):
        response = client.get('/set-language?next=/')
        cookie_val = _parse_cookie_value(response, 'lang')
        assert cookie_val == 'en'

    def test_unsafe_redirect_to_root(self, client):
        response = client.get('/set-language?lang=en&next=https://evil.com')
        assert response.status_code == 302
        assert 'evil.com' not in response.location or response.location.endswith('/')


class TestIndexRoute:
    def test_external_api_error_graceful_degradation(self, client, app):
        from app.utils.exceptions import ExternalAPIError

        mock_svc = MagicMock()
        mock_svc.get_books_by_category.side_effect = ExternalAPIError('API failed', api_name='book_service')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_search_truncation(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            long_query = 'a' * 200
            response = client.get(f'/?search={long_query}')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_publisher_filter_applied(self, client, app):
        book = _make_book(publisher='Penguin')
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/?publisher=Penguin')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_sort_applied(self, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/?sort=weeks_desc')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_sort_preserves_nyt_rank_and_original_detail_target(self, client, app):
        books = [
            _make_book(rank=1, title='Current Number One', weeks_on_list=1, rank_last_week='0'),
            _make_book(
                id='9780062796200',
                isbn13='9780062796200',
                rank=8,
                title='Long Runner',
                weeks_on_list=80,
                rank_last_week='10',
            ),
        ]
        mock_svc = _mock_book_service(books)
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            # 列表视图已下线，只保留网格视图：断言改为网格卡片标记
            response = client.get('/?sort=weeks_desc')
            soup = BeautifulSoup(response.get_data(as_text=True), 'html.parser')
            first_card = soup.select_one('#books-grid .card')
            item_list = next(
                json.loads(script.string)
                for script in soup.select('script[type="application/ld+json"]')
                if 'ItemList' in script.string
            )

            assert first_card.select_one('.card-title').get_text(strip=True) == 'Long Runner'
            assert first_card.select_one('.card-badge').get_text(strip=True) == '8'
            assert first_card.select_one('a')['href'].startswith('/book/7?')
            assert item_list['itemListElement'][0]['item']['url'].endswith('/book/7?category=hardcover-fiction')
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_returning_book_is_not_labeled_new(self, client, app):
        book = _make_book(rank=4, weeks_on_list=12, rank_last_week='0')
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/')
            soup = BeautifulSoup(response.get_data(as_text=True), 'html.parser')
            badge = soup.select_one('#books-grid .rank-change')

            assert badge.get_text(strip=True) == '↩ RETURN'
            assert 'NEW' not in badge.get_text(strip=True)
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_publishers_list_extraction(self, client, app):
        books = [
            _make_book(publisher='Penguin'),
            _make_book(publisher='HarperCollins', isbn13='9780062796200'),
        ]
        mock_svc = _mock_book_service(books)
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/')
            assert response.status_code == 200
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_monthly_category_shows_hint(self, client, app):
        book = _make_book(
            category_id='graphic-books-and-manga',
            category_name='漫画与绘本',
            list_name='Graphic Books and Manga',
            published_date='2026-06-01',
        )
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/?category=graphic-books-and-manga&lang=zh')
            assert response.status_code == 200
            assert '月榜 · 每月更新 · 榜单日期 2026-06-01'.encode() in response.data
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_weekly_category_hides_monthly_hint(self, client, app):
        mock_svc = _mock_book_service([_make_book(published_date='2026-07-05')])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/?category=hardcover-fiction&lang=zh')
            assert response.status_code == 200
            assert '月榜 · 每月更新'.encode() not in response.data
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


def _make_award_book(**overrides):
    """构造 _load_recent_award_books 会读取到的 AwardBook 替身"""
    book = MagicMock()
    book.id = 1
    book.display_title = 'Satantango'
    book.title_zh = '撒旦探戈'
    book.author = 'László Krasznahorkai'
    book.publisher = 'New Directions'
    book.isbn13 = '9780811219297'
    book.year = 2025
    book.category = '文学'
    book.cover_local_path = ''
    book.cover_original_url = ''
    book.award = MagicMock()
    book.award.name = '诺贝尔文学奖'
    book.award.name_en = 'Nobel Prize in Literature'
    for key, value in overrides.items():
        setattr(book, key, value)
    return book


def _seed_bilingual_award(app, db):
    """一条中英齐全的奖项 + 获奖书：奖项名/国家/类别与书名两语都有值，才能验出选错字段。"""
    from app.models.schemas import Award, AwardBook

    with app.app_context():
        award = Award(name='布克奖', name_en='Booker Prize', country='英国', established_year=1969)
        db.session.add(award)
        db.session.flush()
        book = AwardBook(
            award_id=award.id,
            year=2024,
            category='小说',
            title='The Hunger',
            title_zh='饥饿游戏',
            author='Suzanne Collins',
            publisher='Scholastic',
            # 引号 + 换行：移动端 JSON-LD 早先是手拼字符串（只 replace 了引号），这两个字符
            # 正好让整段 JSON 解析失败，留着当回归样本。
            description='An "English" blurb.\nSecond line.',
            description_zh='一段中文简介。',
            isbn13='9780439023528',
            is_displayable=True,
            verification_status='verified',
        )
        db.session.add(book)
        db.session.commit()
        return book.id


class TestRankingsPage:
    """派生榜单页 /rankings"""

    @staticmethod
    def _install_book_service(app, books):
        mock_svc = _mock_book_service(books)
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        return mock_svc

    @staticmethod
    def _remove_book_service(app):
        with app.app_context():
            app.extensions.pop('book_service', None)

    def test_detects_same_book_across_categories_with_different_isbn(self, client, app):
        """同一本书在各分类榜使用不同 ISBN，仍应被识别为跨榜"""
        category_ids = list(app.config['CATEGORIES'])

        def books_for_category(category, **kwargs):
            index = category_ids.index(category)
            isbn = f'97810000000{index:02d}'
            return [
                _make_book(
                    title='My Friends',
                    author='Fredrik Backman',
                    id=isbn,
                    isbn13=isbn,
                    category_id=category,
                    rank=index + 1,
                )
            ]

        mock_svc = _mock_book_service([])
        mock_svc.get_books_by_category.side_effect = books_for_category
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            response = client.get('/rankings?lang=zh')
            html = response.get_data(as_text=True)
            assert response.status_code == 200
            assert '跨榜现象级' in html
            assert 'My Friends' in html
            assert 'Fredrik Backman' in html
        finally:
            self._remove_book_service(app)

    def test_ranking_titles_follow_locale_on_both_ends(self, client, app):
        """主书名按 locale 选：EN 页显示原名、ZH 页显示译名，桌面与移动模板各自成立。

        templates/mobile/rankings.html 是桌面版的平行副本，有自己的一套书名标记；
        上一轮只改了桌面版，生产实测才暴露出移动端仍在显示中文书名 —— 故两端各断言一次。
        """
        self._install_book_service(
            app,
            [_make_book(title='My Friends', title_zh='我的朋友', author='Fredrik Backman', rank=1)],
        )
        ends = {
            'desktop': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'},
            'mobile': {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'},
        }
        markers = {
            'cross': {'desktop': 'cross-title', 'mobile': 'm-book-title'},
            'publishers': {'desktop': 'publisher-books', 'mobile': 'm-publisher-desc'},
        }
        try:
            for tab in ('cross', 'publishers'):
                for label, headers in ends.items():
                    en = client.get(f'/rankings?tab={tab}&lang=en', headers=headers).get_data(as_text=True)
                    assert markers[tab][label] in en, f'{label}/{tab} 未渲染预期模板'
                    assert 'My Friends' in en, f'{label}/{tab} EN 页没有英文原名'
                    assert '我的朋友' not in en, f'{label}/{tab} EN 页泄漏了中文译名'

                    zh = client.get(f'/rankings?tab={tab}&lang=zh', headers=headers).get_data(as_text=True)
                    assert '我的朋友' in zh, f'{label}/{tab} ZH 页没有中文译名'
        finally:
            self._remove_book_service(app)

    def test_invalid_tab_falls_back_to_cross(self, client, app):
        self._install_book_service(app, [])
        try:
            response = client.get('/rankings?tab=nonsense&lang=zh')
            assert response.status_code == 200
            assert '跨榜现象级' in response.get_data(as_text=True)
        finally:
            self._remove_book_service(app)

    def test_publishers_tab_lists_publisher(self, client, app):
        books = [_make_book(title='Atlas', author='A Author', publisher='Penguin Random House (Hybrid)', rank=2)]
        self._install_book_service(app, books)
        try:
            response = client.get('/rankings?tab=publishers&lang=zh')
            html = response.get_data(as_text=True)
            assert response.status_code == 200
            assert 'Penguin Random House' in html
            assert '厂牌榜' in html
        finally:
            self._remove_book_service(app)

    @patch('app.services.award_book_service.AwardBookService')
    def test_overlooked_tab_lists_unlisted_award_winner(self, mock_service_cls, client, app):
        self._install_book_service(app, [_make_book(title='Some Other Book', author='Someone')])
        mock_service_cls.return_value.get_award_books.return_value = ([_make_award_book()], 1)
        try:
            response = client.get('/rankings?tab=overlooked&lang=zh')
            html = response.get_data(as_text=True)
            assert response.status_code == 200
            assert '撒旦探戈' in html
            assert '诺贝尔文学奖' in html
        finally:
            self._remove_book_service(app)

    @patch('app.services.award_book_service.AwardBookService')
    def test_overlooked_tab_hides_award_winner_currently_on_list(self, mock_service_cls, client, app):
        self._install_book_service(app, [_make_book(title='Satantango', author='László Krasznahorkai')])
        mock_service_cls.return_value.get_award_books.return_value = ([_make_award_book()], 1)
        try:
            response = client.get('/rankings?tab=overlooked&lang=zh')
            html = response.get_data(as_text=True)
            assert response.status_code == 200
            assert '撒旦探戈' not in html
            assert '暂无遗珠' in html
        finally:
            self._remove_book_service(app)

    def test_empty_data_renders_empty_state(self, client, app):
        self._install_book_service(app, [])
        try:
            response = client.get('/rankings?lang=zh')
            html = response.get_data(as_text=True)
            assert response.status_code == 200
            assert '本周没有跨榜的书' in html
        finally:
            self._remove_book_service(app)

    def test_longevity_tab_includes_single_list_long_runner(self, client, app):
        """长销常青榜收录只守着一个分类榜的长销书；跨榜现象级则不收录它"""

        def books_for_category(category, **kwargs):
            if category != 'hardcover-fiction':
                return []
            return [_make_book(title='Atlas', author='A Author', weeks_on_list=120, rank=5)]

        mock_svc = _mock_book_service([])
        mock_svc.get_books_by_category.side_effect = books_for_category
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            longevity = client.get('/rankings?tab=longevity&lang=zh')
            html = longevity.get_data(as_text=True)
            assert longevity.status_code == 200
            assert '长销常青榜' in html
            assert 'Atlas' in html
            assert '120' in html

            cross = client.get('/rankings?tab=cross&lang=zh')
            assert '本周没有跨榜的书' in cross.get_data(as_text=True)
        finally:
            self._remove_book_service(app)


DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.5'


class TestAwardPagesLocaleLabels:
    """奖项页的中英显示（#227）：奖项名/国家/类别，以及详情页书名与 JSON-LD。"""

    @staticmethod
    def _visible_text(html: str) -> str:
        """只看渲染后可见文本：`?award=布克奖` 这类中文筛选键合法地留在属性里，不算泄漏。"""
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'textarea', 'noscript', 'template']):
            tag.decompose()
        return soup.get_text(' ', strip=True)

    # 一个测试只测一种 locale：`db` fixture 整个测试期间保留一个 app context，
    # flask-babel 把解析结果缓存在该 context 上，同一测试里第二次换 ?lang= 仍会拿到
    # 第一次的 locale（实测：先 ?lang=en 再 ?lang=zh，第二次仍是 en）。

    def test_awards_list_page_shows_english_labels_on_both_ends(self, client, app, db):
        _seed_bilingual_award(app, db)
        for ua in (DESKTOP_UA, MOBILE_UA):
            html = client.get('/awards?lang=en', headers={'User-Agent': ua}).get_data(as_text=True)
            text = self._visible_text(html)
            assert 'Booker Prize' in text, f'{ua[:20]} 英文奖项页未显示英文名'
            assert '布克奖' not in text, f'{ua[:20]} 英文奖项页泄漏中文奖项名'
            assert 'Fiction' in text, f'{ua[:20]} 英文奖项页未显示英文类别'
            assert '小说' not in text, f'{ua[:20]} 英文奖项页泄漏中文类别'
        desktop = self._visible_text(
            client.get('/awards?lang=en', headers={'User-Agent': DESKTOP_UA}).get_data(as_text=True)
        )
        assert 'United Kingdom' in desktop, '桌面英文奖项页未显示英文国家名'
        assert '英国' not in desktop, '国家未经 award_term 仍在输出中文'

    def test_awards_list_page_keeps_chinese_labels_on_zh(self, client, app, db):
        """反向：中文页不得因为"顺手用英文字段"而丢掉中文标签。"""
        _seed_bilingual_award(app, db)
        for ua in (DESKTOP_UA, MOBILE_UA):
            html = client.get('/awards?lang=zh', headers={'User-Agent': ua}).get_data(as_text=True)
            text = self._visible_text(html)
            assert '布克奖' in text, f'{ua[:20]} 中文奖项页丢了中文奖项名'
            assert '小说' in text, f'{ua[:20]} 中文奖项页丢了中文类别'

    @staticmethod
    def _book_jsonld(html: str) -> dict:
        """取页面里 @type=Book 的那段 ld+json 并解析。

        解析这一步本身就是断言：移动端早先手拼 JSON，书名/简介里的引号与换行会直接产出
        非法 JSON-LD。base.html 可能先输出一段站点级 ld+json，所以按 @type 挑。
        """
        for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError as exc:
                raise AssertionError(f'ld+json 无法解析：{exc}') from exc
            if isinstance(data, dict) and data.get('@type') == 'Book':
                return data
            if isinstance(data, dict) and data.get('@graph'):
                for node in data['@graph']:
                    if node.get('@type') == 'Book':
                        return node
        raise AssertionError('页面没有 @type=Book 的 ld+json')

    def test_award_book_detail_english_title_and_jsonld(self, client, app, db):
        """英文详情页：可见书名、<title> 与 JSON-LD name 都用原文。

        移动端 structured_data 是独立 block，看不见 content 里的 {% set display_title %}，
        "name" 曾一直是空串；改由视图层传 shown_title 后两端一致。桌面端 data-en/data-zh
        是原文/译文切换对的合法载体，所以"不出现中文书名"只对移动端断言。
        """
        book_id = _seed_bilingual_award(app, db)
        for ua in (DESKTOP_UA, MOBILE_UA):
            en = client.get(f'/award-book/{book_id}?lang=en', headers={'User-Agent': ua}).get_data(as_text=True)
            data = self._book_jsonld(en)
            assert data['name'] == 'The Hunger', f'{ua[:20]} JSON-LD name 未跟随 locale'
            assert data['description'].startswith('An "English" blurb.'), f'{ua[:20]} 英文页简介未取原文'
            assert 'The Hunger - BookRank' in en, f'{ua[:20]} <title> 未本地化'
        mobile_en = client.get(f'/award-book/{book_id}?lang=en', headers={'User-Agent': MOBILE_UA}).get_data(
            as_text=True
        )
        assert '饥饿游戏' not in mobile_en, '移动英文详情页泄漏中文书名'

    def test_award_book_detail_chinese_title_and_jsonld(self, client, app, db):
        """反向：中文详情页要出中文书名，且 JSON-LD name 非空（跨 block 取不到值即空串）。"""
        book_id = _seed_bilingual_award(app, db)
        for ua in (DESKTOP_UA, MOBILE_UA):
            zh = client.get(f'/award-book/{book_id}?lang=zh', headers={'User-Agent': ua}).get_data(as_text=True)
            assert self._book_jsonld(zh)['name'] == '饥饿游戏', f'{ua[:20]} 中文页 JSON-LD name 丢失'
            assert '饥饿游戏 - BookRank' in zh, f'{ua[:20]} 中文页 <title> 丢失'


class TestBookDetailSsrLocale:
    """桌面 /book/<i> 的 **SSR 文本**也要按 locale（#236）。

    分类/语言/简介原先由 book-i18n.js 在加载后改写，所以浏览器里"看着是英文"，
    但爬虫与无 JS 访客拿到的仍是 英语/精装小说/中文简介。故本用例不看渲染结果，
    只看响应体里那一段值本身。
    """

    @staticmethod
    def _book():
        return _make_book(
            title='The Calamity Club',
            title_zh='灾难俱乐部',
            category_name='精装小说',
            list_name='Hardcover Fiction',
            language='英语',
            description='An English blurb about the book.',
            description_zh='中文简介。',
        )

    @staticmethod
    def _meta_values(html: str) -> list[str]:
        soup = BeautifulSoup(html, 'html.parser')
        return [(e.get_text() or '').strip() for e in soup.select('.meta-value')]

    @staticmethod
    def _book_ld(html: str) -> dict:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(tag.get_text())
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get('@type') == 'Book':
                return data
        raise AssertionError('页面没有 @type=Book 的 ld+json')

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_english_ssr_values_are_english(self, mock_svc, _mock_fetch, _mock_merge, client, app):
        mock_svc.return_value = _mock_book_service([self._book()])
        html = client.get('/book/0?category=hardcover-fiction&lang=en').get_data(as_text=True)
        values = self._meta_values(html)
        assert 'English' in values, f'语言项 SSR 仍是中文: {values}'
        assert 'Hardcover Fiction' in values, f'分类项 SSR 仍是中文: {values}'
        assert '英语' not in values and '精装小说' not in values
        # 只断言结构化数据：可见的「图书简介」面板本就同时带译文与原文，由前端按语言切显隐
        assert self._book_ld(html)['description'].startswith('An English blurb'), '英文页 JSON-LD 用了中文简介'

        mob = client.get(
            '/book/0?category=hardcover-fiction&lang=en',
            headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'},
        ).get_data(as_text=True)
        assert 'm-meta-row' in mob, '移动端模板未渲染'
        soup = BeautifulSoup(mob, 'html.parser')
        cells = {
            (r.find('dt').get_text(strip=True) or ''): (r.find('dd').get_text(strip=True) or '')
            for r in soup.select('.m-meta-row')
            if r.find('dt') and r.find('dd')
        }
        assert 'Hardcover Fiction' in cells.values(), f'移动英文详情页分类仍是中文: {cells}'
        assert '精装小说' not in cells.values()
        # H1 是页面上最值钱的 SEO 元素，此前无条件取 title_zh，只靠前端改写
        h1 = BeautifulSoup(html, 'html.parser').select_one('.detail-title')
        assert h1 and h1.get_text(strip=True) == 'The Calamity Club', f'英文页 H1: {h1 and h1.get_text()}'
        assert not BeautifulSoup(html, 'html.parser').select_one('.detail-title-en'), '英文页不该挂中文原标题副行'

    @patch('app.routes.main.merge_or_translate_book')
    @patch('app.routes.main.enrich_book_details')
    @patch('app.routes.main.get_service')
    def test_chinese_ssr_values_stay_chinese(self, mock_svc, _mock_fetch, _mock_merge, client, app):
        mock_svc.return_value = _mock_book_service([self._book()])
        html = client.get('/book/0?category=hardcover-fiction&lang=zh').get_data(as_text=True)
        values = self._meta_values(html)
        assert '英语' in values and '精装小说' in values, f'中文页丢了中文标签: {values}'
        soup = BeautifulSoup(html, 'html.parser')
        h1 = soup.select_one('.detail-title')
        assert h1 and h1.get_text(strip=True) == '灾难俱乐部', f'中文页 H1: {h1 and h1.get_text()}'
        assert soup.select_one('.detail-title-en'), '中文页该保留原文书名副行'


class TestNewBooksPublisherNamesFollowLocale:
    """#232：新书页的出版社显示名两端都要跟 locale。

    Publisher 行本来就有 name_en，只是显示位无条件取了 name —— 侧栏、筛选下拉、
    每社书列标题三处同理。
    """

    @staticmethod
    def _modules():
        from unittest.mock import MagicMock

        pub = MagicMock()
        pub.id = 42
        pub.name = '企鹅兰登'
        pub.name_en = 'Penguin Random House'
        pub.website = 'https://example.invalid'
        modules = MagicMock()
        modules.publisher_manager.get_publishers.return_value = [pub]
        modules.publisher_manager.get_publisher_book_counts.return_value = {42: 3}
        modules.query_service.get_categories.return_value = [{'name': '小说', 'count': 3}]
        modules.query_service.get_new_books.return_value = ([], 0)
        modules.query_service.get_statistics.return_value = {
            'total_books': 3,
            'total_publishers': 1,
            'active_publishers': 1,
            'recent_books_7d': 3,
            'top_categories': [],
        }
        modules.query_service.search_books.return_value = ([], 0)
        return modules

    @patch('app.routes.main.get_new_book_modules')
    def test_english_page_shows_english_publisher_names(self, mock_modules, client) -> None:
        mock_modules.return_value = self._modules()
        soup = BeautifulSoup(
            client.get('/new-books?lang=en').get_data(as_text=True),
            'html.parser',
        )
        names = [
            e.get_text(strip=True)
            for e in soup.select('.browse-section-title, select[name="publisher"] option[value="42"]')
        ]
        assert 'Penguin Random House' in names, f'英文页出版社名仍是中文: {names[:8]}'
        assert '企鹅兰登' not in names

    @patch('app.routes.main.get_new_book_modules')
    def test_chinese_page_keeps_chinese_publisher_names(self, mock_modules, client) -> None:
        mock_modules.return_value = self._modules()
        soup = BeautifulSoup(
            client.get('/new-books?lang=zh').get_data(as_text=True),
            'html.parser',
        )
        names = [
            e.get_text(strip=True)
            for e in soup.select('.browse-section-title, select[name="publisher"] option[value="42"]')
        ]
        assert '企鹅兰登' in names, f'中文页丢了中文出版社名: {names[:8]}'
        assert 'Penguin Random House' not in names


class TestAwardBuyLinksParsing:
    """`AwardBook.buy_links` 是**裸 JSON 文本列**（模型上没有解析器）。

    回归：桌面模板此前直接 `{% for link in book.buy_links %}`，迭代字符串会逐字符
    产出 link，`link.url` 变成单个字符 → href 为空/无效。现在路由只在视图内解析，
    数据库里的原始列保持不变。
    """

    def test_parses_json_text_into_url_and_name(self) -> None:
        from app.routes.main import _parse_award_buy_links

        raw = json.dumps(
            [
                {'name': 'Amazon', 'url': 'https://www.amazon.com/dp/123'},
                {'name': 'Bookshop', 'url': 'http://bookshop.org/p/1'},
            ]
        )
        links = _parse_award_buy_links(raw)
        assert [link['name'] for link in links] == ['Amazon', 'Bookshop']
        assert links[0]['url'] == 'https://www.amazon.com/dp/123'
        assert links[1]['url'] == 'http://bookshop.org/p/1'

    def test_accepts_already_parsed_list(self) -> None:
        from app.routes.main import _parse_award_buy_links

        links = _parse_award_buy_links([{'name': 'Amazon', 'url': 'https://amazon.com'}])
        assert links == [{'name': 'Amazon', 'url': 'https://amazon.com'}]

    def test_missing_name_falls_back_to_localized_buy_label(self) -> None:
        from app.routes.main import _parse_award_buy_links

        links = _parse_award_buy_links([{'url': 'https://amazon.com'}])
        assert len(links) == 1
        assert links[0]['name'], '缺少 name 时应回退到本地化「购买」文案，绝不渲染空标签'
        assert links[0]['url'] == 'https://amazon.com'

    def test_malformed_json_does_not_raise_and_yields_no_links(self) -> None:
        from app.routes.main import _parse_award_buy_links

        assert _parse_award_buy_links('{not json') == []
        assert _parse_award_buy_links('"a string"') == []
        assert _parse_award_buy_links('42') == []
        assert _parse_award_buy_links('') == []

    def test_rejects_non_http_and_non_dict_entries(self) -> None:
        from app.routes.main import _parse_award_buy_links

        raw = json.dumps(
            [
                {'name': 'JS', 'url': 'javascript:alert(1)'},
                {'name': 'Empty', 'url': ''},
                {'name': 'Relative', 'url': '/book/1'},
                'not-a-dict',
                {'name': 'Good', 'url': 'https://ok.example/book'},
            ]
        )
        links = _parse_award_buy_links(raw)
        assert links == [{'name': 'Good', 'url': 'https://ok.example/book'}], (
            '只保留 http(s) 且元素为 dict 的条目，避免空 href / 非安全协议'
        )

    def test_route_does_not_mutate_stored_raw_column(self, client, app, db) -> None:
        """路由解析必须只发生在视图内：原始列字节级不变。"""
        from app.models.schemas import Award, AwardBook

        raw = json.dumps([{'name': 'Amazon', 'url': 'https://amazon.com/dp/9'}])
        with app.app_context():
            award = Award(name='测试奖', name_en='Test Award', country='美国', established_year=2000)
            db.session.add(award)
            db.session.flush()
            book = AwardBook(award_id=award.id, year=2024, title='Raw Title', author='A Author', buy_links=raw)
            db.session.add(book)
            db.session.commit()
            book_id = book.id

        client.get(f'/award-book/{book_id}')

        with app.app_context():
            stored = db.session.get(AwardBook, book_id)
            assert stored.buy_links == raw, '原始 buy_links 列必须逐字节保持不变'


def _new_books_modules():
    stats = {
        'total_books': 0,
        'total_publishers': 0,
        'active_publishers': 0,
        'recent_books_7d': 0,
        'top_categories': [],
    }
    modules = MagicMock()
    pm, qs = modules.publisher_manager, modules.query_service
    pm.get_publishers.return_value = []
    pm.get_publisher_book_counts.return_value = {}
    qs.get_categories.return_value = []
    qs.get_statistics.return_value = stats
    qs.get_new_books.return_value = ([], 0)
    qs.search_books.return_value = ([], 0)
    return modules, stats


@pytest.mark.parametrize(
    'raw,expected,searching',
    [
        (None, 'all', False),
        ('', 'all', False),
        ('nope', 'all', True),
        (' published ', 'published', False),
        ('upcoming', 'upcoming', True),
        (' pending ', 'pending', False),
    ],
)
def test_new_books_publication_status_parse_and_query(app, raw, expected, searching):
    args = {'search': 'q'} if searching else {'publisher': '1'}
    if raw is not None:
        args['publication_status'] = raw
    with app.app_context(), patch('app.routes.main.get_sync_request_gate') as gate:
        gate.return_value.seed_static_data.return_value = None
        parsed = _parse_new_books_params(MultiDict(args))
        assert parsed['selected_publication_status'] == expected
        modules, _stats = _new_books_modules()
        _load_new_books_data(modules, parsed)
    query = modules.query_service.search_books if searching else modules.query_service.get_new_books
    assert query.call_args.kwargs['publication_status'] == expected


@pytest.mark.parametrize('mode', ['main', 'stats', 'counts', 'empty'])
def test_new_books_load_failures_are_independent(app, mode):
    params = {
        'selected_publisher': 1,
        'selected_category': '',
        'selected_days': 30,
        'search_query': '',
        'page': 1,
        'per_page': 20,
        'view_mode': 'grid',
        'selected_publication_status': 'published',
    }
    with app.app_context(), patch('app.routes.main.get_sync_request_gate') as gate:
        gate.return_value.seed_static_data.return_value = None
        modules, stats = _new_books_modules()
        kept = [{'title': 'Kept'}]
        if mode != 'empty':
            modules.query_service.get_new_books.return_value = (kept, 1)
        if mode == 'main':
            modules.query_service.get_new_books.side_effect = SQLAlchemyError('books')
        elif mode == 'stats':
            modules.query_service.get_statistics.side_effect = SQLAlchemyError('stats')
        elif mode == 'counts':
            modules.publisher_manager.get_publisher_book_counts.side_effect = SQLAlchemyError('counts')
        data = _load_new_books_data(modules, params)
    ok_books = kept if mode in ('stats', 'counts') else []
    ok_total = 1 if mode in ('stats', 'counts') else (None if mode == 'main' else 0)
    assert data['books'] == ok_books
    assert data['total'] == ok_total
    assert data['total_pages'] == ok_total
    assert data['data_load_failed'] is (mode == 'main')
    assert data['stats'] is (None if mode == 'stats' else stats)
    assert data['stats_unavailable'] is (mode == 'stats')
    assert data['publisher_counts_unavailable'] is (mode == 'counts')
    assert data['publisher_book_counts'] == (None if mode == 'counts' else {})


@pytest.mark.parametrize(
    'counts,searching,n_pubs',
    [('pm', False, 2), ({}, True, 6), ('raise', False, 6), ('raise', True, 2)],
)
def test_publisher_sections_use_one_filtered_batch(app, db, counts, searching, n_pubs):
    from datetime import date, datetime

    from app.models.new_book import NewBook, Publisher
    from app.services.new_book.query_service import NewBookQueryService

    token, fixed = 'ZebraToken', datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
    pubs = [
        Publisher(name=f'P{i}', name_en=f'E{i}', crawler_class='HouseCrawler', is_active=True) for i in range(n_pubs)
    ]
    db.session.add_all(pubs)
    db.session.flush()
    a, b = pubs[0], pubs[1]
    specs = [
        (a, f'{token} A', 'Fiction', date(2026, 9, 10)),
        (b, f'{token} B1', 'Fiction', date(2026, 9, 11)),
        (b, f'{token} B2', 'Fiction', date(2026, 9, 12)),
        (a, f'{token} cat', 'Poetry', date(2026, 9, 12)),
        (a, 'soon', 'Fiction', date(2026, 10, 10)),
        (b, f'{token} old', 'Fiction', date(2020, 1, 1)),
    ]
    rows = [
        NewBook(
            publisher_id=pub.id,
            title=title,
            author='Ada',
            isbn13=f'978100{i:07d}',
            category=cat,
            publication_date=day,
            created_at=fixed,
            is_displayable=True,
        )
        for i, (pub, title, cat, day) in enumerate(specs, start=1)
    ]
    db.session.add_all(rows)
    db.session.commit()
    params = {
        'selected_publisher': None,
        'selected_category': 'Fiction',
        'selected_days': 30,
        'search_query': token if searching else '',
        'page': 1,
        'per_page': 20,
        'view_mode': 'grid',
        'selected_publication_status': 'published',
    }

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    with (
        app.app_context(),
        patch('app.routes.main.get_sync_request_gate') as gate,
        patch('app.services.new_book.query_service.datetime', FrozenDateTime),
    ):
        gate.return_value.seed_static_data.return_value = None
        modules, _stats = _new_books_modules()
        service = NewBookQueryService(MagicMock())
        modules.query_service = service
        service.get_new_books = MagicMock(wraps=service.get_new_books)
        service.search_books = MagicMock(wraps=service.search_books)
        modules.publisher_manager.get_publishers.return_value = pubs
        pm = modules.publisher_manager
        if counts == 'raise':
            pm.get_publisher_book_counts.side_effect = SQLAlchemyError('counts')
            expected_counts = None
        elif counts == {}:
            pm.get_publisher_book_counts.return_value = {}
            expected_counts = {}
        else:
            expected_counts = {a.id: 999, b.id: 0}
            pm.get_publisher_book_counts.return_value = expected_counts
        data = _load_new_books_data(modules, params)
    used = service.search_books if searching else service.get_new_books
    idle = service.get_new_books if searching else service.search_books
    second = used.call_args_list[1]
    per_page = second.kwargs.get('per_page', second.args[2] if len(second.args) > 2 else None)
    assert used.call_count == 2 and idle.call_count == 0 and per_page == 300
    assert second.kwargs['category'] == 'Fiction'
    assert second.kwargs['days'] == 30
    assert second.kwargs['publication_status'] == 'published'
    assert [part['publisher'].id for part in data['publisher_sections']] == [b.id, a.id]
    assert [len(part['books']) for part in data['publisher_sections']] == [2, 1]
    got = {book.id for part in data['publisher_sections'] for book in part['books']}
    assert got == {book.id for book in data['books']} == {rows[0].id, rows[1].id, rows[2].id}
    assert data['publisher_book_counts'] == expected_counts
    assert data['publisher_counts_unavailable'] is (counts == 'raise')
    assert data['publishers_unavailable'] is False
    assert data['publisher_sections_unavailable'] is False
    assert data['data_load_failed'] is False


def test_publisher_kind_uses_exact_crawler_class(app):
    from app.models.new_book import Publisher

    specs = [
        ('Renamed Books', 'GoogleBooksCrawler', 'provider'),
        ('Open Shelf', 'OpenLibraryCrawler', 'provider'),
        ('HarperCollins Google', 'HarperCollinsGoogleCrawler', 'publisher'),
        ('City House', 'CityHouseCrawler', 'publisher'),
    ]
    pubs = []
    for i, (name, crawler, _kind) in enumerate(specs, start=1):
        pub = Publisher(name=name, name_en=f'{name} EN', crawler_class=crawler, is_active=True)
        pub.id = i
        pubs.append(pub)
    params = {
        'selected_publisher': None,
        'selected_category': '',
        'selected_days': 7,
        'search_query': '',
        'page': 1,
        'per_page': 20,
        'view_mode': 'grid',
        'selected_publication_status': 'all',
    }
    with app.app_context(), patch('app.routes.main.get_sync_request_gate') as gate:
        gate.return_value.seed_static_data.return_value = None
        modules, _stats = _new_books_modules()
        modules.publisher_manager.get_publishers.return_value = pubs
        data = _load_new_books_data(modules, params)
    assert data['publisher_kind'] == {i: kind for i, (*_rest, kind) in enumerate(specs, start=1)}
    assert modules.query_service.get_new_books.call_count == 2
    assert data['publishers_unavailable'] is False


@pytest.mark.parametrize('mode', ['publishers', 'sections'])
def test_publisher_and_section_failures_set_flags(app, mode):
    from types import SimpleNamespace

    from app.models.new_book import Publisher

    kept = SimpleNamespace(id=5, title='Kept', author='Ada', publisher_id=4)
    pub = Publisher(name='House', name_en='House', crawler_class='HouseCrawler', is_active=True)
    pub.id = 4
    params = {
        'selected_publisher': None,
        'selected_category': '',
        'selected_days': 30,
        'search_query': '',
        'page': 1,
        'per_page': 20,
        'view_mode': 'grid',
        'selected_publication_status': 'all',
    }
    with app.app_context(), patch('app.routes.main.get_sync_request_gate') as gate:
        gate.return_value.seed_static_data.return_value = None
        modules, _stats = _new_books_modules()
        modules.publisher_manager.get_publishers.return_value = [pub]
        if mode == 'publishers':
            modules.publisher_manager.get_publishers.side_effect = SQLAlchemyError('publishers')
            modules.query_service.get_new_books.return_value = ([kept], 1)
        else:
            modules.query_service.get_new_books.side_effect = [
                ([kept], 1),
                SQLAlchemyError('sections'),
            ]
        data = _load_new_books_data(modules, params)
    assert data['books'] == [kept] and data['data_load_failed'] is False
    assert data['publishers'] == ([] if mode == 'publishers' else [pub])
    assert data['publishers_unavailable'] is (mode == 'publishers')
    assert data['publisher_sections_unavailable'] is (mode == 'sections')
    assert data['publisher_sections'] == []


from sqlalchemy import event

from app.models.schemas import Award, AwardBook
from app.utils import ExternalAPIError


def _norm_sql(statement):
    return ' '.join(statement.lower().split())


def _round2_sql_fault(mode, statement):
    sql = _norm_sql(statement)
    if mode == 'books':
        return 'from award_books' in sql and 'group by' not in sql
    if mode == 'counts':
        return 'group by award_books.award_id' in sql
    if mode == 'awards':
        return ' from awards' in sql and ' where ' not in sql
    if mode == 'selected':
        return ' where ' in sql and 'awards.name' in sql
    if mode == 'detail' or mode == 'awardfail':
        return sql.startswith('select') and 'award_books' in sql
    return False


def _listen_sql(engine, mode):
    def _before(conn, cursor, statement, parameters, context, executemany):
        if _round2_sql_fault(mode, statement):
            raise SQLAlchemyError('round2 SELECT unavailable')

    event.listen(engine, 'before_cursor_execute', _before)
    return _before


def _capture_adaptive(monkeypatch):
    captured = {}

    def _render(template, **kwargs):
        captured['template'] = template
        captured.update(kwargs)
        return 'captured'

    monkeypatch.setattr('app.routes.main.render_adaptive', _render)
    return captured


@pytest.mark.parametrize('mode', ['books', 'counts', 'awards', 'selected', 'ok', 'empty'])
def test_awards_real_sql_failure_versus_empty(mode, db, app, monkeypatch):
    """Genuine SELECT faults stay distinct from a successful empty year."""
    if mode != 'empty':
        award = Award(name='Round2 Visible', wikidata_id='Q9')
        db.session.add(award)
        db.session.flush()
        db.session.add(
            AwardBook(
                award_id=award.id,
                title='Kept',
                author='A',
                year=2026,
                isbn13='9782026000009',
                is_displayable=True,
            )
        )
        db.session.commit()
    captured = _capture_adaptive(monkeypatch)
    listener = _listen_sql(db.engine, mode) if mode in {'books', 'counts', 'awards', 'selected'} else None
    try:
        path = '/awards?year=2026'
        if mode == 'selected':
            path += '&award=Round2%20Visible'
        resp = app.test_client().get(path)
    finally:
        if listener is not None:
            event.remove(db.engine, 'before_cursor_execute', listener)
    assert resp.status_code == 200 and resp.get_data(as_text=True) == 'captured'
    failed = mode in {'books', 'selected'}
    assert captured['data_load_failed'] is failed
    assert captured['award_counts_unavailable'] is (mode == 'counts')
    assert captured['awards_unavailable'] is (mode == 'awards')
    if failed:
        assert captured['total_books'] is None and captured['total_pages'] is None
    elif mode == 'empty':
        assert captured['books'] == [] and captured['total_books'] == 0 and captured['total_pages'] == 1
    else:
        assert [row['title'] for row in captured['books']] == ['Kept']
        assert captured['total_books'] == 1 and captured['total_pages'] == 1
    if mode == 'counts':
        assert captured['awards'] and all(row.book_count is None for row in captured['awards'])
    if mode == 'awards':
        assert captured['awards'] == []


@pytest.mark.parametrize('mode', ['fault', 'missing'])
def test_award_book_unknown_real_sql_versus_missing(mode, db, app, monkeypatch):
    captured = _capture_adaptive(monkeypatch)
    listener = _listen_sql(db.engine, 'detail') if mode == 'fault' else None
    try:
        resp = app.test_client().get('/award-book/999?return_to=/awards%3Fyear%3D2026')
    finally:
        if listener is not None:
            event.remove(db.engine, 'before_cursor_execute', listener)
    assert captured['back_url'] == '/awards?year=2026'
    if mode == 'fault':
        assert resp.status_code == 500
        message = captured['message']
        assert '暂时无法加载' in message and '不存在' not in message
    else:
        assert resp.status_code == 404


@pytest.mark.parametrize('mode', ['empty', 'nytfail', 'awardfail'])
def test_rankings_empty_versus_nyt_and_award_faults(mode, db, app, monkeypatch):
    categories = list(app.config['CATEGORIES'])
    first = categories[0]

    def _boundary(category, auto_translate=False, notify_refresh=False, report_failures=False):
        if mode == 'nytfail' and category == first:
            raise ExternalAPIError('offline', api_name='book_service')
        return [], None

    monkeypatch.setattr('app.routes.main._get_books_for_category', _boundary)
    captured = _capture_adaptive(monkeypatch)
    listener = _listen_sql(db.engine, 'awardfail') if mode == 'awardfail' else None
    try:
        resp = app.test_client().get('/rankings')
    finally:
        if listener is not None:
            event.remove(db.engine, 'before_cursor_execute', listener)
    assert resp.status_code == 200 and resp.get_data(as_text=True) == 'captured'
    assert captured['rankings_nyt_unavailable_count'] == (1 if mode == 'nytfail' else 0)
    assert captured['rankings_awards_unavailable'] is (mode == 'awardfail')
    assert captured['cross_entries'] == []
    assert captured['longevity_entries'] == []
    assert captured['overlooked_entries'] == []
    assert captured['publisher_entries'] == []


@pytest.mark.parametrize('path', ['/reports/weekly', '/reports/weekly/2026-01-01'])
@pytest.mark.parametrize('mode', ['fault', 'empty'])
def test_weekly_report_read_routes(app, db, path, mode):
    from sqlalchemy.exc import SQLAlchemyError

    captured = {}

    def render_adaptive(template, **kwargs):
        captured['template'] = template
        captured.update(kwargs)
        return 'captured'

    def listener(conn, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        if mode == 'fault' and sql.lstrip().startswith('select') and 'weekly_reports' in sql:
            raise SQLAlchemyError('weekly SQL unavailable')

    event.listen(db.engine, 'before_cursor_execute', listener)
    try:
        with (
            patch('app.routes.main.get_service', return_value=MagicMock()),
            patch('app.routes.main.render_adaptive', side_effect=render_adaptive),
            patch(
                'app.services.weekly_report_service.WeeklyReportService.get_or_trigger_current_week_report',
                return_value=(None, False),
            ),
            patch('app.services.weekly_report_service.WeeklyReportService.record_report_view') as record,
        ):
            resp = app.test_client().get(path)
    finally:
        event.remove(db.engine, 'before_cursor_execute', listener)
    if mode == 'fault':
        assert resp.status_code == 500
        assert captured['template'] == 'error.html'
        assert captured['back_url'] == '/reports/weekly'
        if path == '/reports/weekly':
            assert captured['message'] == '周报加载失败，请稍后再试'
        else:
            assert captured['message'] == '周报加载失败，请稍后再试'
        return
    record.assert_not_called()
    if path == '/reports/weekly':
        assert resp.status_code == 200 and resp.get_data(as_text=True) == 'captured'
        assert captured['reports'] == [] and captured['is_generating'] is False
    else:
        assert resp.status_code == 200
        assert captured['template'] == 'error.html'
        assert captured['message'] == '周报不存在'


def test_load_new_books_data_sql_stays_flat_for_two_and_six_publishers(app, db, monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from sqlalchemy import event
    from werkzeug.datastructures import ImmutableMultiDict

    from app.models.new_book import NewBook, Publisher
    from app.routes.main import _load_new_books_data, _parse_new_books_params, get_sync_request_gate
    from app.services.new_book.publisher_manager import PublisherManager
    from app.services.new_book.query_service import NewBookQueryService

    monkeypatch.setattr(get_sync_request_gate(), 'seed_static_data', lambda *_args, **_kwargs: None)
    pipeline = MagicMock()
    modules = SimpleNamespace(
        query_service=NewBookQueryService(pipeline),
        publisher_manager=PublisherManager(),
        translation_pipeline=pipeline,
        sync_engine=MagicMock(),
    )
    params = _parse_new_books_params(
        ImmutableMultiDict(
            [
                ('search', 'FlatSQL'),
                ('category', 'Fiction'),
                ('days', '30'),
                ('publication_status', 'published'),
                ('per_page', '50'),
            ]
        )
    )

    def _measure(n_pubs):
        db.session.query(NewBook).delete()
        db.session.query(Publisher).delete()
        db.session.commit()
        published = datetime.now(UTC).replace(tzinfo=None)
        publishers = [
            Publisher(name=f'FlatPub{i}', name_en=f'FlatPub{i}', crawler_class='FlatCrawler', is_active=True)
            for i in range(n_pubs)
        ]
        db.session.add_all(publishers)
        db.session.flush()
        books = []
        for index, pub in enumerate(publishers):
            for copy in range(3 if index == 0 else 1):
                books.append(
                    NewBook(
                        title='FlatSQL',
                        author='Author',
                        isbn13=f'978{n_pubs}{index:02d}{copy:07d}',
                        publication_date=published,
                        publisher_id=pub.id,
                        category='Fiction',
                    )
                )
        db.session.add_all(books)
        db.session.commit()
        db.session.remove()
        sqls = []

        def _collect(_conn, _cursor, statement, _parameters, _context, _executemany):
            text = ' '.join(statement.lower().split())
            if text.startswith('select'):
                sqls.append(text)

        event.listen(db.engine, 'before_cursor_execute', _collect)
        try:
            data = _load_new_books_data(modules, params)
        finally:
            event.remove(db.engine, 'before_cursor_execute', _collect)
        db.session.remove()
        return len(sqls), sqls, data

    measured = {n_pubs: _measure(n_pubs) for n_pubs in (2, 6)}
    assert measured[2][0] == measured[6][0] > 0
    for n_pubs, (_total, sqls, data) in measured.items():
        joins = [sql for sql in sqls if 'left outer join' in sql and 'publisher' in sql and 'new_book' in sql]
        assert len(joins) == 2
        for flag in (
            'data_load_failed',
            'stats_unavailable',
            'publishers_unavailable',
            'publisher_counts_unavailable',
            'publisher_sections_unavailable',
        ):
            assert data[flag] is False
        sections = data['publisher_sections']
        assert len(sections) == n_pubs <= 6
        assert [len(section['books']) for section in sections] == [3, *([1] * (n_pubs - 1))]
        assert all(len(section['books']) <= 8 for section in sections)
        main_isbns = {book.isbn13 for book in data['books']}
        section_isbns = {book.isbn13 for section in sections for book in section['books']}
        assert section_isbns == main_isbns
        assert len(main_isbns) == n_pubs + 2
    assert len(measured[2][1]) == len(measured[6][1])
