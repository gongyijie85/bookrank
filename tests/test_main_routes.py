"""主路由辅助函数测试"""

import json
from unittest.mock import MagicMock, patch

from app.routes.main import (
    _filter_books_by_publisher,
    _filter_books_by_search,
    _filter_books_by_weeks,
    _is_valid_isbn,
    _parse_report_content,
    _sort_books,
    _update_book_from_google_books,
    _validate_date,
)


class TestIsValidISBN:
    """测试 _is_valid_isbn"""

    def test_valid_isbn13(self):
        assert _is_valid_isbn('9780743273565') is True

    def test_valid_isbn13_with_dashes(self):
        assert _is_valid_isbn('978-0-7432-7356-5') is True

    def test_valid_isbn10(self):
        assert _is_valid_isbn('0743273567') is True

    def test_isbn10_with_x(self):
        assert _is_valid_isbn('080442957X') is True

    def test_none(self):
        assert _is_valid_isbn(None) is False

    def test_empty(self):
        assert _is_valid_isbn('') is False

    def test_invalid(self):
        assert _is_valid_isbn('not-an-isbn') is False

    def test_isbn13_wrong_prefix(self):
        assert _is_valid_isbn('9770743273565') is False


class TestFilterBooksBySearch:
    """测试 _filter_books_by_search"""

    def test_no_query(self):
        books = [{'title': 'Book A', 'author': 'Author A'}]
        assert _filter_books_by_search(books, '') == books

    def test_none_query(self):
        books = [{'title': 'Book A', 'author': 'Author A'}]
        assert _filter_books_by_search(books, None) == books

    def test_empty_books(self):
        assert _filter_books_by_search([], 'test') == []

    def test_match_title(self):
        books = [
            {'title': 'Python Programming', 'author': 'Author A'},
            {'title': 'Java Guide', 'author': 'Author B'},
        ]
        result = _filter_books_by_search(books, 'python')
        assert len(result) == 1
        assert result[0]['title'] == 'Python Programming'

    def test_match_author(self):
        books = [
            {'title': 'Book A', 'author': 'John Smith'},
            {'title': 'Book B', 'author': 'Jane Doe'},
        ]
        result = _filter_books_by_search(books, 'john')
        assert len(result) == 1
        assert result[0]['author'] == 'John Smith'

    def test_case_insensitive(self):
        books = [{'title': 'PYTHON', 'author': 'Author'}]
        result = _filter_books_by_search(books, 'python')
        assert len(result) == 1


class TestFilterBooksByPublisher:
    """测试 _filter_books_by_publisher"""

    def test_no_publisher(self):
        books = [{'publisher': 'Penguin'}]
        assert _filter_books_by_publisher(books, '') == books

    def test_match_publisher(self):
        books = [
            {'publisher': 'Penguin Random House'},
            {'publisher': 'HarperCollins'},
        ]
        result = _filter_books_by_publisher(books, 'penguin')
        assert len(result) == 1

    def test_empty_books(self):
        assert _filter_books_by_publisher([], 'Penguin') == []


class TestFilterBooksByWeeks:
    """测试 _filter_books_by_weeks"""

    def test_new_books(self):
        books = [
            {'weeks_on_list': 1},
            {'weeks_on_list': 5},
        ]
        result = _filter_books_by_weeks(books, 'new')
        assert len(result) == 1
        assert result[0]['weeks_on_list'] == 1

    def test_trending_books(self):
        books = [
            {'weeks_on_list': 1},
            {'weeks_on_list': 3},
            {'weeks_on_list': 10},
        ]
        result = _filter_books_by_weeks(books, 'trending')
        assert len(result) == 1
        assert result[0]['weeks_on_list'] == 3

    def test_classic_books(self):
        books = [
            {'weeks_on_list': 3},
            {'weeks_on_list': 10},
        ]
        result = _filter_books_by_weeks(books, 'classic')
        assert len(result) == 1
        assert result[0]['weeks_on_list'] == 10

    def test_no_filter(self):
        books = [{'weeks_on_list': 1}]
        assert _filter_books_by_weeks(books, '') == books

    def test_unknown_filter(self):
        books = [{'weeks_on_list': 1}]
        assert _filter_books_by_weeks(books, 'unknown') == books


class TestSortBooks:
    """测试 _sort_books"""

    def test_empty_books(self):
        assert _sort_books([], 'rank_change') == []

    def test_sort_by_rank_change(self):
        books = [
            {'rank': 1, 'rank_last_week': '5'},
            {'rank': 3, 'rank_last_week': '3'},
            {'rank': 2, 'rank_last_week': '10'},
        ]
        result = _sort_books(books, 'rank_change')
        assert result[0]['rank'] == 2

    def test_sort_by_weeks_desc(self):
        books = [
            {'weeks_on_list': 2},
            {'weeks_on_list': 10},
            {'weeks_on_list': 5},
        ]
        result = _sort_books(books, 'weeks_desc')
        assert result[0]['weeks_on_list'] == 10

    def test_sort_by_weeks_asc(self):
        books = [
            {'weeks_on_list': 10},
            {'weeks_on_list': 2},
        ]
        result = _sort_books(books, 'weeks_asc')
        assert result[0]['weeks_on_list'] == 2

    def test_no_sort(self):
        books = [{'rank': 5}, {'rank': 1}]
        assert _sort_books(books, '') == books

    def test_rank_change_with_none_last_week(self):
        books = [
            {'rank': 1, 'rank_last_week': None},
            {'rank': 2, 'rank_last_week': '5'},
        ]
        result = _sort_books(books, 'rank_change')
        assert len(result) == 2


class TestValidateDate:
    """测试 _validate_date"""

    def test_valid_date(self):
        is_valid, error, date_obj = _validate_date('2024-01-15')
        assert is_valid is True
        assert error is None
        assert date_obj is not None

    def test_invalid_format(self):
        is_valid, _error, date_obj = _validate_date('2024/01/15')
        assert is_valid is False
        assert date_obj is None

    def test_too_old(self):
        is_valid, _error, _date_obj = _validate_date('2019-01-01')
        assert is_valid is False

    def test_future_date(self):
        is_valid, _error, _date_obj = _validate_date('2099-01-01')
        assert is_valid is False

    def test_empty(self):
        is_valid, _error, _date_obj = _validate_date('')
        assert is_valid is False

    def test_none(self):
        is_valid, _error, _date_obj = _validate_date(None)
        assert is_valid is False

    def test_wrong_length(self):
        is_valid, _error, _date_obj = _validate_date('2024-1-5')
        assert is_valid is False


class TestParseReportContent:
    """测试 _parse_report_content"""

    def test_valid_json(self):
        report = MagicMock()
        report.content = json.dumps({'key': 'value'})
        result = _parse_report_content(report)
        assert result == {'key': 'value'}

    def test_dict_content(self):
        report = MagicMock()
        report.content = {'key': 'value'}
        result = _parse_report_content(report)
        assert result == {'key': 'value'}

    def test_none_report(self):
        assert _parse_report_content(None) is None

    def test_none_content(self):
        report = MagicMock()
        report.content = None
        assert _parse_report_content(report) is None

    def test_invalid_json(self):
        report = MagicMock()
        report.content = 'not json{'
        assert _parse_report_content(report) is None


class TestUpdateBookFromGoogleBooks:
    """测试 _update_book_from_google_books"""

    def test_updates_details(self):
        book = {}
        details = {'details': 'A great book description'}
        with patch('app.routes.main._translate_field_async'):
            _update_book_from_google_books(book, details)
        assert book['details'] == 'A great book description'

    def test_skips_no_description(self):
        book = {}
        details = {'details': 'No detailed description available.'}
        _update_book_from_google_books(book, details)
        assert 'details' not in book

    def test_updates_page_count(self):
        book = {}
        details = {'page_count': 320}
        _update_book_from_google_books(book, details)
        assert book['page_count'] == '320'

    def test_skips_unknown_page_count(self):
        book = {}
        details = {'page_count': 'Unknown'}
        _update_book_from_google_books(book, details)
        assert 'page_count' not in book

    def test_updates_publisher_when_unknown(self):
        book = {'publisher': 'Unknown'}
        details = {'publisher': 'Penguin'}
        _update_book_from_google_books(book, details)
        assert book['publisher'] == 'Penguin'

    def test_keeps_existing_publisher(self):
        book = {'publisher': 'Scribner'}
        details = {'publisher': 'Penguin'}
        _update_book_from_google_books(book, details)
        assert book['publisher'] == 'Scribner'

    def test_updates_cover_url(self):
        book = {}
        details = {'cover_url': 'https://example.com/cover.jpg'}
        _update_book_from_google_books(book, details)
        assert book['cover'] == 'https://example.com/cover.jpg'

    def test_does_not_overwrite_cover(self):
        book = {'cover': 'existing.jpg'}
        details = {'cover_url': 'new.jpg'}
        _update_book_from_google_books(book, details)
        assert book['cover'] == 'existing.jpg'

    def test_updates_isbn13(self):
        book = {}
        details = {'isbn_13': '9780743273565'}
        _update_book_from_google_books(book, details)
        assert book['isbn13'] == '9780743273565'

    def test_updates_publication_dt(self):
        book = {}
        details = {'publication_dt': '2024-01-15'}
        _update_book_from_google_books(book, details)
        assert book['publication_dt'] == '2024-01-15'

    def test_updates_language(self):
        book = {}
        details = {'language': 'English'}
        _update_book_from_google_books(book, details)
        assert book['language'] == 'English'


class TestMainRoutes:
    """测试主路由端点"""

    def test_index_page(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_index_with_category(self, client):
        response = client.get('/?category=hardcover-fiction')
        assert response.status_code == 200

    def test_index_with_search(self, client):
        response = client.get('/?search=python')
        assert response.status_code == 200

    def test_index_with_view_grid(self, client):
        response = client.get('/?view=grid')
        assert response.status_code == 200

    def test_index_with_invalid_view(self, client):
        response = client.get('/?view=invalid')
        assert response.status_code == 200

    def test_index_with_publisher_filter(self, client):
        response = client.get('/?publisher=Penguin')
        assert response.status_code == 200

    def test_index_with_weeks_filter(self, client):
        response = client.get('/?weeks=new')
        assert response.status_code == 200

    def test_index_with_sort(self, client):
        response = client.get('/?sort=rank_change')
        assert response.status_code == 200

    def test_favicon(self, client):
        response = client.get('/favicon.ico')
        assert response.status_code in (200, 404)

    def test_about_page(self, client):
        response = client.get('/about')
        assert response.status_code == 200

    def test_publishers_page(self, client):
        response = client.get('/publishers')
        assert response.status_code == 200

    def test_cache_management_page(self, client):
        response = client.get('/cache-management')
        assert response.status_code == 200

    def test_analytics_dashboard_page(self, client):
        response = client.get('/analytics')
        assert response.status_code == 200

    def test_set_language_en(self, client):
        response = client.get('/set-language?lang=en&next=/')
        assert response.status_code == 302

    def test_set_language_zh(self, client):
        response = client.get('/set-language?lang=zh&next=/')
        assert response.status_code == 302

    def test_set_language_invalid(self, client):
        response = client.get('/set-language?lang=fr&next=/')
        assert response.status_code == 302

    def test_set_language_unsafe_redirect(self, client):
        response = client.get('/set-language?lang=en&next=https://evil.com')
        assert response.status_code == 302

    def test_cached_image_invalid_filename(self, client):
        response = client.get('/cache/images/../../../etc/passwd')
        assert response.status_code == 404

    def test_cached_image_invalid_format(self, client):
        response = client.get('/cache/images/test.png')
        assert response.status_code == 404

    def test_book_details_api_missing_params(self, client):
        response = client.get('/api/book-details')
        json.loads(response.data)
        assert response.status_code == 400

    def test_api_category_books(self, client):
        response = client.get('/api/category-books?category=hardcover-fiction')
        assert response.status_code == 200

    def test_api_category_books_invalid(self, client):
        response = client.get('/api/category-books?category=invalid')
        assert response.status_code == 400

    def test_weekly_reports_page(self, client):
        response = client.get('/reports/weekly')
        assert response.status_code == 200

    def test_weekly_report_detail_invalid_date(self, client):
        response = client.get('/reports/weekly/invalid-date')
        assert response.status_code == 200

    def test_weekly_report_detail_future_date(self, client):
        response = client.get('/reports/weekly/2099-01-01')
        assert response.status_code == 200

    def test_new_books_page(self, client):
        response = client.get('/new-books')
        assert response.status_code == 200

    def test_awards_page(self, client):
        response = client.get('/awards')
        assert response.status_code == 200

    def test_book_detail_invalid_index(self, client):
        response = client.get('/book/99999')
        assert response.status_code == 200

    def test_book_detail_negative_index(self, client):
        response = client.get('/book/-1')
        assert response.status_code in (200, 404)
