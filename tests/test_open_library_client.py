"""Open Library 客户端测试"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.open_library_client import OpenLibraryClient


@pytest.fixture
def ol_client():
    c = OpenLibraryClient(timeout=10)
    c._session = MagicMock()
    return c


class TestInit:
    def test_default_cache_ttl(self, ol_client):
        assert ol_client._cache_ttl == 86400 * 3

    def test_custom_cache_ttl(self):
        c = OpenLibraryClient(cache_ttl=600)
        assert c._cache_ttl == 600


class TestFetchBookByISBN:
    def test_empty_isbn(self, ol_client):
        assert ol_client.fetch_book_by_isbn('') == {}

    def test_cache_hit(self, ol_client):
        mock_cache = MagicMock()
        mock_cache.get.return_value = {'title': 'Cached Book'}
        ol_client._api_cache = mock_cache

        result = ol_client.fetch_book_by_isbn('9780743273565')
        assert result == {'title': 'Cached Book'}

    def test_api_success(self, ol_client):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        ol_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'ISBN:9780743273565': {
                'title': 'The Great Gatsby',
                'authors': [{'name': 'F. Scott Fitzgerald'}],
                'publishers': [{'name': 'Scribner'}],
                'publish_date': '1925',
                'number_of_pages': 180,
                'cover': {'large': 'https://covers.openlibrary.org/b/id/12345-L.jpg'},
                'description': {'value': 'A classic American novel'},
            }
        }
        mock_resp.raise_for_status = MagicMock()
        ol_client._session.get.return_value = mock_resp

        result = ol_client.fetch_book_by_isbn('9780743273565')
        assert result['title'] == 'The Great Gatsby'
        assert result['author'] == 'F. Scott Fitzgerald'
        assert result['isbn_13'] == '9780743273565'
        assert result['cover_url'] == 'https://covers.openlibrary.org/b/id/12345-L.jpg'

    def test_api_no_data(self, ol_client):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        ol_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        ol_client._session.get.return_value = mock_resp

        result = ol_client.fetch_book_by_isbn('9780000000000')
        assert result == {}

    def test_api_request_exception(self, ol_client):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        ol_client._api_cache = mock_cache

        ol_client._session.get.side_effect = requests.RequestException('Connection error')

        result = ol_client.fetch_book_by_isbn('9780743273565')
        assert result == {}

    def test_isbn_with_dashes(self, ol_client):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        ol_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'ISBN:9780743273565': {
                'title': 'Book',
                'authors': [],
                'publish_date': '2024',
            }
        }
        mock_resp.raise_for_status = MagicMock()
        ol_client._session.get.return_value = mock_resp

        result = ol_client.fetch_book_by_isbn('978-0-7432-7356-5')
        assert result['title'] == 'Book'


class TestParseBookData:
    def test_full_data(self, ol_client):
        data = {
            'title': 'Test Book',
            'authors': [{'name': 'Author A'}, {'name': 'Author B'}],
            'publishers': [{'name': 'Publisher A'}],
            'publish_date': '2024',
            'number_of_pages': 300,
            'cover': {'medium': 'https://covers.openlibrary.org/b/id/123-M.jpg'},
            'description': 'A great book',
        }
        result = ol_client._parse_book_data(data, '9780000000001')
        assert result['title'] == 'Test Book'
        assert result['author'] == 'Author A, Author B'
        assert result['publisher'] == 'Publisher A'
        assert result['isbn_13'] == '9780000000001'
        assert result['isbn_10'] is None

    def test_isbn10(self, ol_client):
        data = {'title': 'Book', 'publish_date': '2024'}
        result = ol_client._parse_book_data(data, '0743273567')
        assert result['isbn_10'] == '0743273567'
        assert result['isbn_13'] is None

    def test_no_authors(self, ol_client):
        data = {'title': 'Book', 'publish_date': '2024'}
        result = ol_client._parse_book_data(data, '9780000000001')
        assert result['author'] is None
        assert result['authors'] == []

    def test_description_dict(self, ol_client):
        data = {'title': 'Book', 'publish_date': '2024', 'description': {'value': 'A description'}}
        result = ol_client._parse_book_data(data, '9780000000001')
        assert result['description'] == 'A description'

    def test_description_string(self, ol_client):
        data = {'title': 'Book', 'publish_date': '2024', 'description': 'A string description'}
        result = ol_client._parse_book_data(data, '9780000000001')
        assert result['description'] == 'A string description'

    def test_no_description(self, ol_client):
        data = {'title': 'Book', 'publish_date': '2024'}
        result = ol_client._parse_book_data(data, '9780000000001')
        assert result['description'] == 'No description available.'

    def test_cover_small(self, ol_client):
        data = {'title': 'Book', 'publish_date': '2024', 'cover': {'small': 'https://covers.example.com/small.jpg'}}
        result = ol_client._parse_book_data(data, '9780000000001')
        assert result['cover_url'] == 'https://covers.example.com/small.jpg'


class TestGetCoverUrl:
    def test_empty_isbn(self, ol_client):
        assert ol_client.get_cover_url('') is None

    def test_cover_available(self, ol_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Length': '5000'}
        ol_client._session.head.return_value = mock_resp

        result = ol_client.get_cover_url('9780743273565')
        assert result is not None
        assert '9780743273565' in result

    def test_cover_too_small(self, ol_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Length': '50'}
        ol_client._session.head.return_value = mock_resp

        result = ol_client.get_cover_url('9780743273565')
        assert result is None

    def test_cover_not_found(self, ol_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        ol_client._session.head.return_value = mock_resp

        result = ol_client.get_cover_url('9780743273565')
        assert result is None

    def test_cover_request_exception(self, ol_client):
        ol_client._session.head.side_effect = requests.RequestException('error')

        result = ol_client.get_cover_url('9780743273565')
        assert result is None

    def test_invalid_size(self, ol_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Length': '5000'}
        ol_client._session.head.return_value = mock_resp

        result = ol_client.get_cover_url('9780743273565', size='XL')
        assert result is not None


class TestGetCoverUrlByTitle:
    def test_empty_title(self, ol_client):
        assert ol_client.get_cover_url_by_title('') is None

    @patch.object(OpenLibraryClient, 'search_books')
    def test_no_results(self, mock_search, ol_client):
        mock_search.return_value = []
        result = ol_client.get_cover_url_by_title('Nonexistent')
        assert result is None

    @patch.object(OpenLibraryClient, 'search_books')
    def test_no_cover_id(self, mock_search, ol_client):
        mock_search.return_value = [{'title': 'Book', 'cover_id': None}]
        result = ol_client.get_cover_url_by_title('Book')
        assert result is None

    @patch.object(OpenLibraryClient, 'search_books')
    def test_cover_found(self, mock_search, ol_client):
        mock_search.return_value = [{'title': 'Book', 'author': 'Author', 'cover_id': 12345}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        ol_client._session.head.return_value = mock_resp

        result = ol_client.get_cover_url_by_title('Book', author='Author')
        assert result is not None

    @patch.object(OpenLibraryClient, 'search_books')
    def test_request_exception(self, mock_search, ol_client):
        mock_search.return_value = [{'title': 'Book', 'cover_id': 12345}]
        ol_client._session.head.side_effect = requests.RequestException('error')

        result = ol_client.get_cover_url_by_title('Book')
        assert result is None


class TestSelectCoverMatch:
    def test_empty_books(self, ol_client):
        assert ol_client._select_cover_match([], 'title') is None

    def test_exact_title_match(self, ol_client):
        books = [{'title': 'The Great Gatsby', 'author': 'Fitzgerald', 'cover_id': 1}]
        result = ol_client._select_cover_match(books, 'The Great Gatsby', 'Fitzgerald')
        assert result is not None

    def test_partial_title_match(self, ol_client):
        books = [{'title': 'The Great Gatsby: A Novel', 'author': 'Fitzgerald', 'cover_id': 1}]
        result = ol_client._select_cover_match(books, 'Great Gatsby', 'Fitzgerald')
        assert result is not None

    def test_no_cover_id_skipped(self, ol_client):
        books = [{'title': 'Book', 'author': 'Author', 'cover_id': None}]
        result = ol_client._select_cover_match(books, 'Book', 'Author')
        assert result is None

    def test_fallback_first_with_cover(self, ol_client):
        books = [
            {'title': 'Different Book', 'author': 'Different Author', 'cover_id': 1},
        ]
        result = ol_client._select_cover_match(books, 'Target Book')
        assert result is not None
        assert result['cover_id'] == 1


class TestNormalizeSearchText:
    def test_normalizes(self):
        assert OpenLibraryClient._normalize_search_text('The Great-Gatsby!') == 'the great gatsby'

    def test_empty(self):
        assert OpenLibraryClient._normalize_search_text('') == ''


class TestSearchBooks:
    def test_success(self, ol_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'docs': [
                {
                    'title': 'Python Book',
                    'author_name': ['John Doe'],
                    'first_publish_year': 2023,
                    'isbn': ['9780000000001'],
                    'cover_i': 123,
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        ol_client._session.get.return_value = mock_resp

        result = ol_client.search_books('Python')
        assert len(result) == 1
        assert result[0]['title'] == 'Python Book'
        assert result[0]['cover_id'] == 123

    def test_no_results(self, ol_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'docs': []}
        mock_resp.raise_for_status = MagicMock()
        ol_client._session.get.return_value = mock_resp

        result = ol_client.search_books('Nonexistent')
        assert result == []

    def test_request_exception(self, ol_client):
        ol_client._session.get.side_effect = requests.RequestException('error')

        result = ol_client.search_books('Python')
        assert result == []
