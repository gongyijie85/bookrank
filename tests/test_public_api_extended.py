"""public_api.py 路由扩展测试 — 覆盖现有测试未覆盖的端点和代码路径"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

from app.models.book import Book


def _make_book(**overrides):
    """构造 Book dataclass 实例"""
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
    svc.get_latest_cache_time.return_value = '2024-01-14'
    svc.search_books.return_value = []
    return svc


class TestGetAllBestsellersExtended:
    """测试 /api/public/bestsellers 的成功和异常路径"""

    def test_success_with_books(self, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert 'books' in data['data']
            assert 'last_updated' in data['data']
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_limit_clamped_to_50(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers?limit=100')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_exception_returns_500(self, client, app):
        mock_svc = MagicMock()
        mock_svc.get_books_by_category.side_effect = Exception('DB error')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestGetBestsellersByCategoryExtended:
    """测试 /api/public/bestsellers/<category> 的各种路径"""

    def test_success(self, client, app):
        book = _make_book()
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert data['data']['category_id'] == 'hardcover-fiction'
            assert data['data']['total'] == 1
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_invalid_category(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/nonexistent')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 400
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/public/bestsellers/hardcover-fiction')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 503

    def test_limit_clamped(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/hardcover-fiction?limit=200')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_exception_returns_500(self, client, app):
        mock_svc = MagicMock()
        mock_svc.get_books_by_category.side_effect = Exception('crash')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/hardcover-fiction')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestSearchBestsellersExtended:
    """测试 /api/public/bestsellers/search 的各种路径"""

    def test_long_keyword(self, client):
        resp = client.get('/api/public/bestsellers/search?keyword=' + 'a' * 101)
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_chinese_keyword(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/search?keyword=测试书名')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/public/bestsellers/search?keyword=python')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 503

    def test_exception_returns_500(self, client, app):
        mock_svc = MagicMock()
        mock_svc.search_books.side_effect = Exception('crash')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/search?keyword=python')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_limit_clamped(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/bestsellers/search?keyword=python&limit=100')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestGetAllAwardsExtended:
    """测试 /api/public/awards 的成功和异常路径"""

    @patch('app.routes.public_api._award_service')
    def test_success(self, mock_award_svc, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award.description = 'A test award'
        mock_award_svc.get_all_awards.return_value = [mock_award]
        mock_award_svc.get_book_counts_by_award.return_value = {1: 5}

        resp = client.get('/api/public/awards')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert len(data['data']['awards']) == 1
        assert data['data']['awards'][0]['book_count'] == 5

    @patch('app.routes.public_api._award_service')
    def test_exception_returns_500(self, mock_award_svc, client):
        mock_award_svc.get_all_awards.side_effect = Exception('DB error')
        resp = client.get('/api/public/awards')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 500

    @patch('app.routes.public_api._award_service')
    def test_empty_awards(self, mock_award_svc, client):
        mock_award_svc.get_all_awards.return_value = []
        mock_award_svc.get_book_counts_by_award.return_value = {}
        resp = client.get('/api/public/awards')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['data']['total'] == 0


class TestGetAwardBooksExtended:
    """测试 /api/public/awards/<award_name> 的各种路径"""

    @patch('app.routes.public_api._award_service')
    def test_success(self, mock_award_svc, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award.description = 'desc'
        mock_award_svc.get_award_by_name.return_value = mock_award

        mock_book = MagicMock()
        mock_book.to_dict.return_value = {'id': 1, 'title': 'Book1'}
        mock_award_svc.get_award_books.return_value = ([mock_book], 1)
        mock_award_svc.get_distinct_years.return_value = [2024]

        resp = client.get('/api/public/awards/TestAward')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['data']['total'] == 1
        assert 'years' in data['data']

    @patch('app.routes.public_api._award_service')
    def test_award_not_found(self, mock_award_svc, client):
        mock_award_svc.get_award_by_name.return_value = None
        resp = client.get('/api/public/awards/Nonexistent')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 404

    @patch('app.routes.public_api._award_service')
    def test_with_year_filter(self, mock_award_svc, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award.description = 'desc'
        mock_award_svc.get_award_by_name.return_value = mock_award
        mock_award_svc.get_award_books.return_value = ([], 0)
        mock_award_svc.get_distinct_years.return_value = [2024]

        resp = client.get('/api/public/awards/TestAward?year=2024&limit=10')
        data = json.loads(resp.data)
        assert data['success'] is True
        mock_award_svc.get_award_books.assert_called_once()

    @patch('app.routes.public_api._award_service')
    def test_exception_returns_500(self, mock_award_svc, client):
        mock_award_svc.get_award_by_name.side_effect = Exception('DB error')
        resp = client.get('/api/public/awards/TestAward')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 500


class TestGetAwardBooksByYearExtended:
    """测试 /api/public/awards/<award_name>/<year> 的各种路径"""

    @patch('app.routes.public_api._award_service')
    def test_success(self, mock_award_svc, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award_svc.get_award_by_name.return_value = mock_award

        mock_book = MagicMock()
        mock_book.to_dict.return_value = {'id': 1, 'title': 'Book1'}
        mock_award_svc.get_award_books.return_value = ([mock_book], 1)

        resp = client.get('/api/public/awards/TestAward/2024')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['data']['year'] == 2024
        assert data['data']['total'] == 1

    @patch('app.routes.public_api._award_service')
    def test_award_not_found(self, mock_award_svc, client):
        mock_award_svc.get_award_by_name.return_value = None
        resp = client.get('/api/public/awards/Nonexistent/2024')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 404

    @patch('app.routes.public_api._award_service')
    def test_no_books_for_year(self, mock_award_svc, client):
        mock_award = MagicMock()
        mock_award.id = 1
        mock_award.name = 'TestAward'
        mock_award.name_en = 'Test Award'
        mock_award_svc.get_award_by_name.return_value = mock_award
        mock_award_svc.get_award_books.return_value = ([], 0)

        resp = client.get('/api/public/awards/TestAward/1900')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 404

    @patch('app.routes.public_api._award_service')
    def test_exception_returns_500(self, mock_award_svc, client):
        mock_award_svc.get_award_by_name.side_effect = Exception('DB error')
        resp = client.get('/api/public/awards/TestAward/2024')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 500


class TestGetBookDetailsExtended:
    """测试 /api/public/book/<isbn> 的各种路径"""

    def test_found_in_bestsellers(self, client, app):
        book = _make_book(isbn13='9780143127550')
        mock_svc = _mock_book_service([book])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            with patch('app.routes.public_api._award_service') as mock_award:
                resp = client.get('/api/public/book/9780143127550')
                data = json.loads(resp.data)
                assert data['success'] is True
                assert data['data']['source'] == 'bestseller'
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.routes.public_api._award_service')
    def test_found_in_awards(self, mock_award_svc, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            mock_award_book = MagicMock()
            mock_award_book.to_dict.return_value = {'id': 1, 'isbn13': '9780143127550'}
            mock_award_svc.find_award_book_by_isbn.return_value = mock_award_book

            resp = client.get('/api/public/book/9780143127550')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert data['data']['source'] == 'award'
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/public/book/9780143127550')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 503

    @patch('app.routes.public_api._award_service')
    def test_exception_returns_500(self, mock_award_svc, client, app):
        mock_svc = MagicMock()
        mock_svc.get_books_by_category.side_effect = Exception('crash')
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            resp = client.get('/api/public/book/9780143127550')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    def test_isbn10_format(self, client, app):
        mock_svc = _mock_book_service([])
        with app.app_context():
            app.extensions['book_service'] = mock_svc
        try:
            with patch('app.routes.public_api._award_service') as mock_award:
                mock_award.find_award_book_by_isbn.return_value = None
                resp = client.get('/api/public/book/014312755X')
                data = json.loads(resp.data)
                assert data['success'] is False
                assert resp.status_code == 404
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestGetWeeklyReportsExtended:
    """测试 /api/public/reports/weekly 的各种路径"""

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/public/reports/weekly')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 503

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_success(self, MockWRS, client, app):
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {'id': 1, 'title': 'Report 1'}
        mock_svc = MagicMock()
        mock_svc.get_reports.return_value = [mock_report]
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly')
            data = json.loads(resp.data)
            assert data['success'] is True
            assert data['data']['total'] == 1
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_exception_returns_500(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_reports.side_effect = Exception('crash')
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_limit_clamped(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_reports.return_value = []
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly?limit=100')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestGetLatestWeeklyReportExtended:
    """测试 /api/public/reports/weekly/latest 的各种路径"""

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/public/reports/weekly/latest')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 503

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_no_report_available(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_latest_report.return_value = None
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly/latest')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 404
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_success(self, MockWRS, client, app):
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {'id': 1}
        mock_svc = MagicMock()
        mock_svc.get_latest_report.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly/latest')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_exception_returns_500(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_latest_report.side_effect = Exception('crash')
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly/latest')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestGetWeeklyReportByDateExtended:
    """测试 /api/public/reports/weekly/<date> 的各种路径"""

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
        resp = client.get('/api/public/reports/weekly/2024-01-15')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 503

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_report_not_found(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_report_by_date.return_value = None
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly/2024-01-15')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 404
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_success(self, MockWRS, client, app):
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {'id': 1}
        mock_svc = MagicMock()
        mock_svc.get_report_by_date.return_value = mock_report
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly/2024-01-15')
            data = json.loads(resp.data)
            assert data['success'] is True
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)

    @patch('app.services.weekly_report_service.WeeklyReportService')
    def test_exception_returns_500(self, MockWRS, client, app):
        mock_svc = MagicMock()
        mock_svc.get_report_by_date.side_effect = Exception('crash')
        MockWRS.return_value = mock_svc

        mock_book_svc = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_book_svc
        try:
            resp = client.get('/api/public/reports/weekly/2024-01-15')
            data = json.loads(resp.data)
            assert data['success'] is False
            assert resp.status_code == 500
        finally:
            with app.app_context():
                app.extensions.pop('book_service', None)


class TestGetNewBooksExtended:
    """测试 /api/public/new-books 的异常路径"""

    @patch('app.services.new_book.NewBookService')
    def test_exception_returns_500(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.get_new_books.side_effect = Exception('DB error')
        MockNBS.return_value = mock_svc
        resp = client.get('/api/public/new-books')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 500

    @patch('app.services.new_book.NewBookService')
    def test_with_publisher_id(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.get_new_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc
        resp = client.get('/api/public/new-books?publisher_id=1')
        data = json.loads(resp.data)
        assert data['success'] is True
        mock_svc.get_new_books.assert_called_once()

    def test_per_page_clamped(self, client, db):
        resp = client.get('/api/public/new-books?per_page=200')
        data = json.loads(resp.data)
        assert data['data']['per_page'] == 50

    def test_page_clamped_min(self, client, db):
        resp = client.get('/api/public/new-books?page=0')
        data = json.loads(resp.data)
        assert data['data']['page'] == 1


class TestGetNewBooksByPublisherExtended:
    """测试 /api/public/new-books/<publisher_name> 的各种路径"""

    @patch('app.services.new_book.NewBookService')
    def test_exception_returns_500(self, MockNBS, client):
        mock_svc = MagicMock()
        mock_svc.get_publishers.side_effect = Exception('DB error')
        MockNBS.return_value = mock_svc
        resp = client.get('/api/public/new-books/TestPublisher')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 500

    @patch('app.services.new_book.NewBookService')
    def test_publisher_found_success(self, MockNBS, client):
        mock_publisher = MagicMock()
        mock_publisher.id = 1
        mock_publisher.name = 'TestPublisher'

        mock_svc = MagicMock()
        mock_svc.get_publishers.return_value = [mock_publisher]
        mock_svc.get_new_books.return_value = ([], 0)
        MockNBS.return_value = mock_svc

        resp = client.get('/api/public/new-books/TestPublisher')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['data']['publisher']['name'] == 'TestPublisher'


class TestGetRecommendationsExtended:
    """测试 /api/public/recommendations 的异常路径"""

    @patch('app.services.recommendation_service.RecommendationService')
    def test_exception_returns_500(self, MockRS, client):
        mock_svc = MagicMock()
        mock_svc.get_smart_recommendations.side_effect = Exception('crash')
        MockRS.return_value = mock_svc
        resp = client.get('/api/public/recommendations')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert resp.status_code == 500

    @patch('app.services.recommendation_service.RecommendationService')
    def test_success_with_limit(self, MockRS, client):
        mock_svc = MagicMock()
        mock_svc.get_smart_recommendations.return_value = {'recommendations': []}
        MockRS.return_value = mock_svc
        resp = client.get('/api/public/recommendations?limit=5')
        data = json.loads(resp.data)
        assert data['success'] is True
        mock_svc.get_smart_recommendations.assert_called_once_with(limit=5)


class TestSerializeNewBookHelper:
    """测试 _serialize_new_book 辅助函数"""

    def test_basic_serialization(self):
        from app.routes.public_api import _serialize_new_book

        mock_book = MagicMock()
        mock_book.id = 1
        mock_book.title = 'Test'
        mock_book.author = 'Author'
        mock_book.isbn13 = '9780000000000'
        mock_book.category = 'fiction'
        mock_book.cover_url = 'https://example.com/cover.jpg'
        mock_book.publication_date = date(2024, 1, 15)
        mock_book.title_zh = None
        mock_book.publisher = None

        result = _serialize_new_book(mock_book)
        assert result['id'] == 1
        assert result['title'] == 'Test'
        assert result['publication_date'] == '2024-01-15'
        assert 'title_zh' not in result
        assert 'publisher' not in result

    def test_with_title_zh(self):
        from app.routes.public_api import _serialize_new_book

        mock_book = MagicMock()
        mock_book.id = 2
        mock_book.title = 'Test2'
        mock_book.author = 'Author2'
        mock_book.isbn13 = '9780000000001'
        mock_book.category = 'nonfiction'
        mock_book.cover_url = None
        mock_book.publication_date = None
        mock_book.title_zh = '测试书名'
        mock_book.publisher = None

        result = _serialize_new_book(mock_book)
        assert result['title_zh'] == '测试书名'
        assert result['publication_date'] is None

    def test_with_publisher_object(self):
        from app.routes.public_api import _serialize_new_book

        mock_publisher = MagicMock()
        mock_publisher.name = 'TestPub'

        mock_book = MagicMock()
        mock_book.id = 3
        mock_book.title = 'Test3'
        mock_book.author = 'Author3'
        mock_book.isbn13 = None
        mock_book.category = None
        mock_book.cover_url = None
        mock_book.publication_date = None
        mock_book.title_zh = None
        mock_book.publisher = mock_publisher

        result = _serialize_new_book(mock_book)
        assert result['publisher'] == 'TestPub'

    def test_with_string_publisher(self):
        from app.routes.public_api import _serialize_new_book

        mock_book = MagicMock()
        mock_book.id = 4
        mock_book.title = 'Test4'
        mock_book.author = 'Author4'
        mock_book.isbn13 = None
        mock_book.category = None
        mock_book.cover_url = None
        mock_book.publication_date = None
        mock_book.title_zh = None
        mock_book.publisher = 'StringPub'

        result = _serialize_new_book(mock_book)
        assert result['publisher'] == 'StringPub'


class TestApiInfoExtended:
    """测试 /api/public/ 端点的更多细节"""

    def test_version(self, client):
        resp = client.get('/api/public/')
        data = json.loads(resp.data)
        assert data['data']['version'] == '1.2.0'

    def test_endpoints_count(self, client):
        resp = client.get('/api/public/')
        data = json.loads(resp.data)
        assert len(data['data']['endpoints']) == 13

    def test_rate_limit_info(self, client):
        resp = client.get('/api/public/')
        data = json.loads(resp.data)
        assert 'rate_limit' in data['data']

    def test_documentation_link(self, client):
        resp = client.get('/api/public/')
        data = json.loads(resp.data)
        assert 'documentation' in data['data']
