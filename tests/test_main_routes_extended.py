"""main.py 路由扩展测试 — 覆盖现有测试未覆盖的路由和代码路径"""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

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
    @patch('app.routes.main.get_image_cache_service')
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
        mock_sync.resolve_cover_for_book.return_value = 'https://example.com/cover.jpg'
        MockACSS.return_value = mock_sync
        response = client.get(f'/award-book/{book_id}/cover')
        assert response.status_code == 302
        assert response.location == 'https://example.com/cover.jpg'
        assert 'max-age=3600' in response.headers.get('Cache-Control', '')

    @patch('app.services.award_cover_sync_service.AwardCoverSyncService')
    @patch('app.routes.main.get_image_cache_service')
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
        mock_sync.resolve_cover_for_book.side_effect = Exception('API Error')
        MockACSS.return_value = mock_sync
        response = client.get(f'/award-book/{book_id}/cover')
        assert response.status_code == 302
        assert 'original.jpg' in response.location

    @patch('app.services.award_cover_sync_service.AwardCoverSyncService')
    @patch('app.routes.main.get_image_cache_service')
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
        mock_sync.resolve_cover_for_book.side_effect = Exception('API Error')
        MockACSS.return_value = mock_sync
        response = client.get(f'/award-book/{book_id}/cover')
        assert response.status_code == 302
        assert 'no-store' in response.headers.get('Cache-Control', '')


class TestAwardsPage:
    def test_awards_default_render(self, client):
        response = client.get('/awards')
        assert response.status_code == 200

    def test_awards_with_view_list(self, client):
        response = client.get('/awards?view=list')
        assert response.status_code == 200

    def test_awards_with_invalid_view(self, client):
        response = client.get('/awards?view=invalid')
        assert response.status_code == 200

    def test_awards_with_valid_year(self, client):
        response = client.get('/awards?year=2024')
        assert response.status_code == 200

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
        response = client.get('/awards')
        assert response.status_code == 200

    @patch('app.services.award_book_service.AwardBookService')
    def test_awards_with_award_name_filter(self, MockAwardService, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award.description = 'desc'
        mock_award.book_count = 0

        mock_book = MagicMock()
        mock_book.id = 10
        mock_book.title = 'Test Title'
        mock_book.author = 'Author'
        mock_book.description = 'desc'
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

    @patch('app.services.new_book_service.NewBookService')
    def test_new_books_service_ensure_fails(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.ensure_static_data_seeded.side_effect = Exception('seed error')
        mock_svc.get_publishers.return_value = []
        mock_svc.get_publisher_book_counts.return_value = {}
        mock_svc.get_categories.return_value = []
        mock_svc.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_svc.get_new_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.services.new_book_service.NewBookService')
    def test_new_books_publishers_exception(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.ensure_static_data_seeded.return_value = None
        mock_svc.get_publishers.side_effect = Exception('db error')
        mock_svc.get_publisher_book_counts.return_value = {}
        mock_svc.get_categories.return_value = []
        mock_svc.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_svc.get_new_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.services.new_book_service.NewBookService')
    def test_new_books_categories_exception(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.ensure_static_data_seeded.return_value = None
        mock_svc.get_publishers.return_value = []
        mock_svc.get_publisher_book_counts.return_value = {}
        mock_svc.get_categories.side_effect = Exception('db error')
        mock_svc.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_svc.get_new_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.services.new_book_service.NewBookService')
    def test_new_books_statistics_exception(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.ensure_static_data_seeded.return_value = None
        mock_svc.get_publishers.return_value = []
        mock_svc.get_publisher_book_counts.return_value = {}
        mock_svc.get_categories.return_value = []
        mock_svc.get_statistics.side_effect = Exception('db error')
        mock_svc.get_new_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.services.new_book_service.NewBookService')
    def test_new_books_get_books_exception(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.ensure_static_data_seeded.return_value = None
        mock_svc.get_publishers.return_value = []
        mock_svc.get_publisher_book_counts.return_value = {}
        mock_svc.get_categories.return_value = []
        mock_svc.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_svc.get_new_books.side_effect = Exception('db error')
        MockNBS.return_value = mock_svc
        response = client.get('/new-books')
        assert response.status_code == 200

    @patch('app.services.new_book_service.NewBookService')
    def test_new_books_search_path(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.ensure_static_data_seeded.return_value = None
        mock_svc.get_publishers.return_value = []
        mock_svc.get_publisher_book_counts.return_value = {}
        mock_svc.get_categories.return_value = []
        mock_svc.get_statistics.return_value = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }
        mock_svc.search_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc
        response = client.get('/new-books?search=test')
        assert response.status_code == 200
        mock_svc.search_books.assert_called_once()


class TestNewBookDetail:
    @patch('app.services.new_book_service.NewBookService')
    def test_book_not_found(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.get_book.return_value = None
        MockNBS.return_value = mock_svc
        response = client.get('/new-book/999')
        assert response.status_code == 200

    @patch('app.routes.main.submit_background_task')
    @patch('app.routes.main.get_translation_service')
    @patch('app.services.new_book_service.NewBookService')
    def test_book_found_needs_translation(self, MockNBS, mock_trans, mock_bg, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title_zh = None
        mock_book.description_zh = None
        mock_svc = MagicMock()
        mock_svc.get_book.return_value = mock_book
        MockNBS.return_value = mock_svc
        mock_trans.return_value = MagicMock()

        response = client.get('/new-book/1')
        assert response.status_code == 200
        mock_bg.assert_called_once()

    @patch('app.routes.main.get_translation_service')
    @patch('app.services.new_book_service.NewBookService')
    def test_book_found_already_translated(self, MockNBS, mock_trans, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title_zh = '已翻译'
        mock_book.description_zh = '已翻译描述'
        mock_svc = MagicMock()
        mock_svc.get_book.return_value = mock_book
        MockNBS.return_value = mock_svc

        response = client.get('/new-book/1')
        assert response.status_code == 200

    @patch('app.routes.main.get_translation_service')
    @patch('app.services.new_book_service.NewBookService')
    def test_book_found_no_translation_service(self, MockNBS, mock_trans, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title_zh = None
        mock_book.description_zh = None
        mock_svc = MagicMock()
        mock_svc.get_book.return_value = mock_book
        MockNBS.return_value = mock_svc
        mock_trans.return_value = None

        response = client.get('/new-book/1')
        assert response.status_code == 200

    @patch('app.routes.main.get_translation_service')
    @patch('app.services.new_book_service.NewBookService')
    def test_book_found_partial_translation(self, MockNBS, mock_trans, client):
        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title_zh = '已翻译'
        mock_book.description_zh = None
        mock_svc = MagicMock()
        mock_svc.get_book.return_value = mock_book
        MockNBS.return_value = mock_svc
        mock_trans.return_value = MagicMock()

        response = client.get('/new-book/1')
        assert response.status_code == 200


class TestAwardBookDetail:
    @patch('app.services.award_book_service.AwardBookService')
    def test_award_book_found(self, MockAwardService, client):
        mock_book = MagicMock()
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
        assert response.status_code == 200


class TestBookDetail:
    def test_valid_book_index(self, client, app):
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

    def test_invalid_category_fallback(self, client, app):
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
        assert response.status_code == 200


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
