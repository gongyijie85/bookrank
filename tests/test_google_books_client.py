"""Google Books 客户端测试"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.google_books_client import GoogleBooksClient


@pytest.fixture
def client_no_key():
    c = GoogleBooksClient(api_key=None, base_url='https://www.googleapis.com/books/v1/volumes')
    c._session = MagicMock()
    return c


@pytest.fixture
def client_with_key():
    c = GoogleBooksClient(api_key='test-key', base_url='https://www.googleapis.com/books/v1/volumes')
    c._session = MagicMock()
    return c


class TestInit:
    """测试初始化"""

    def test_no_api_key(self, client_no_key):
        assert client_no_key._api_key is None
        assert client_no_key._key_validated is False

    def test_with_api_key(self, client_with_key):
        assert client_with_key._api_key == 'test-key'

    def test_custom_cache_ttl(self):
        c = GoogleBooksClient(api_key='k', base_url='url', cache_ttl=600)
        assert c._cache_ttl == 600

    def test_default_cache_ttl(self, client_no_key):
        assert client_no_key._cache_ttl == 86400


class TestValidateApiKey:
    """测试 _validate_api_key"""

    def test_no_key(self, client_no_key):
        assert client_no_key._validate_api_key() is False

    def test_valid_key(self, client_with_key):
        mock_response = MagicMock()
        mock_response.status_code = 200
        client_with_key._session.get.return_value = mock_response

        assert client_with_key._validate_api_key() is True

    def test_invalid_key_400(self, client_with_key):
        mock_response = MagicMock()
        mock_response.status_code = 400
        client_with_key._session.get.return_value = mock_response

        assert client_with_key._validate_api_key() is False

    def test_unexpected_status(self, client_with_key):
        mock_response = MagicMock()
        mock_response.status_code = 500
        client_with_key._session.get.return_value = mock_response

        assert client_with_key._validate_api_key() is False

    def test_network_error(self, client_with_key):
        client_with_key._session.get.side_effect = Exception('Network error')

        assert client_with_key._validate_api_key() is False

    def test_cached_validation(self, client_no_key):
        client_no_key._key_validated = True
        client_no_key._key_is_valid = True
        assert client_no_key._validate_api_key() is True


class TestBuildParams:
    """测试 _build_params"""

    def test_with_valid_key(self, client_with_key):
        client_with_key._key_is_valid = True
        params = client_with_key._build_params({'q': 'test'})
        assert 'key' in params

    def test_without_valid_key(self, client_no_key):
        client_no_key._key_is_valid = False
        params = client_no_key._build_params({'q': 'test'})
        assert 'key' not in params


class TestFetchBookDetails:
    """测试 fetch_book_details"""

    def test_empty_isbn(self, client_no_key):
        assert client_no_key.fetch_book_details('') == {}

    def test_cache_hit(self, client_no_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = {'title': 'Cached Book'}
        client_no_key._api_cache = mock_cache_service

        result = client_no_key.fetch_book_details('9780743273565')
        assert result == {'title': 'Cached Book'}

    def test_api_success(self, client_no_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_no_key._api_cache = mock_cache_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'volumeInfo': {
                        'title': 'The Great Gatsby',
                        'authors': ['F. Scott Fitzgerald'],
                        'publishedDate': '1925',
                        'description': 'A classic American novel set in the Jazz Age',
                        'pageCount': 180,
                        'language': 'en',
                        'publisher': 'Scribner',
                        'imageLinks': {'thumbnail': 'https://books.google.com/cover.jpg'},
                        'industryIdentifiers': [
                            {'type': 'ISBN_13', 'identifier': '9780743273565'},
                            {'type': 'ISBN_10', 'identifier': '0743273567'},
                        ],
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client_no_key._session.get.return_value = mock_response

        result = client_no_key.fetch_book_details('9780743273565')
        assert result['title'] == 'The Great Gatsby'
        assert result['isbn_13'] == '9780743273565'
        assert result['isbn_10'] == '0743273567'

    def test_api_no_items(self, client_no_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_no_key._api_cache = mock_cache_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'totalItems': 0}
        mock_response.raise_for_status = MagicMock()
        client_no_key._session.get.return_value = mock_response

        result = client_no_key.fetch_book_details('9780000000000')
        assert result == {}

    def test_api_request_exception(self, client_no_key):
        import requests

        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_no_key._api_cache = mock_cache_service

        client_no_key._session.get.side_effect = requests.RequestException('Connection error')

        result = client_no_key.fetch_book_details('9780743273565')
        assert result == {}

    def test_api_429_retry(self, client_no_key):
        """429 响应现在由 except 块处理（返回空结果），不再手动 sleep 重试"""
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_no_key._api_cache = mock_cache_service

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.raise_for_status = MagicMock(side_effect=requests.HTTPError('429 Too Many Requests'))

        client_no_key._session.get.return_value = mock_429

        result = client_no_key.fetch_book_details('9780743273565')
        assert result == {}

    def test_api_400_fallback_no_key(self, client_with_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_with_key._api_cache = mock_cache_service
        client_with_key._key_is_valid = True

        mock_400 = MagicMock()
        mock_400.status_code = 400

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            'items': [
                {
                    'volumeInfo': {
                        'title': 'Book',
                        'authors': ['A'],
                        'publishedDate': '2024',
                        'description': 'A' * 30,
                        'pageCount': 100,
                        'language': 'en',
                        'imageLinks': {},
                        'industryIdentifiers': [],
                    }
                }
            ]
        }
        mock_200.raise_for_status = MagicMock()

        client_with_key._session.get.side_effect = [mock_400, mock_200]

        result = client_with_key.fetch_book_details('9780743273565')
        assert result['title'] == 'Book'


class TestSearchBookByTitle:
    """测试 search_book_by_title"""

    def test_empty_title(self, client_no_key):
        assert client_no_key.search_book_by_title('') == {}

    def test_search_success(self, client_no_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_no_key._api_cache = mock_cache_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'volumeInfo': {
                        'title': 'Python Programming',
                        'authors': ['John Doe'],
                        'publishedDate': '2023',
                        'description': 'A comprehensive guide to Python programming language',
                        'pageCount': 400,
                        'language': 'en',
                        'imageLinks': {},
                        'industryIdentifiers': [],
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client_no_key._session.get.return_value = mock_response

        result = client_no_key.search_book_by_title('Python Programming', author='John Doe')
        assert result['title'] == 'Python Programming'

    def test_search_no_results(self, client_no_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_no_key._api_cache = mock_cache_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'totalItems': 0}
        mock_response.raise_for_status = MagicMock()
        client_no_key._session.get.return_value = mock_response

        result = client_no_key.search_book_by_title('Nonexistent Book')
        assert result == {}

    def test_search_400_fallback(self, client_with_key):
        mock_cache_service = MagicMock()
        mock_cache_service.get.return_value = None
        client_with_key._api_cache = mock_cache_service
        client_with_key._key_is_valid = True

        mock_400 = MagicMock()
        mock_400.status_code = 400

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {'totalItems': 0}
        mock_200.raise_for_status = MagicMock()

        client_with_key._session.get.side_effect = [mock_400, mock_200]

        result = client_with_key.search_book_by_title('Test')
        assert result == {}


class TestParseVolumeInfo:
    """测试 _parse_volume_info"""

    def test_full_info(self, client_no_key):
        volume_info = {
            'title': 'Test Book',
            'authors': ['Author A'],
            'publishedDate': '2024-01-01',
            'description': 'A detailed description of the book that is long enough',
            'pageCount': 300,
            'language': 'en',
            'publisher': 'Test Publisher',
            'imageLinks': {'extraLarge': 'http://books.google.com/cover.jpg'},
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780000000001'},
            ],
        }
        result = client_no_key._parse_volume_info(volume_info)
        assert result['title'] == 'Test Book'
        assert result['isbn_13'] == '9780000000001'
        assert result['cover_url'] == 'https://books.google.com/cover.jpg'

    def test_short_description_uses_subtitle(self, client_no_key):
        volume_info = {
            'title': 'Book',
            'subtitle': 'A Subtitle',
            'authors': [],
            'publishedDate': '2024',
            'description': 'Short',
            'pageCount': 0,
            'language': 'zh',
            'imageLinks': {},
            'industryIdentifiers': [],
            'categories': ['Fiction', 'Science'],
        }
        result = client_no_key._parse_volume_info(volume_info)
        assert 'A Subtitle' in result['details']

    def test_no_description_no_subtitle(self, client_no_key):
        volume_info = {
            'title': 'Book',
            'authors': [],
            'publishedDate': '2024',
            'description': '',
            'pageCount': 0,
            'language': '',
            'imageLinks': {},
            'industryIdentifiers': [],
        }
        result = client_no_key._parse_volume_info(volume_info)
        assert result['details'] == '暂无详细描述'

    def test_http_cover_url_converted(self, client_no_key):
        volume_info = {
            'title': 'Book',
            'authors': [],
            'publishedDate': '2024',
            'description': 'A' * 30,
            'pageCount': 0,
            'language': 'en',
            'imageLinks': {'thumbnail': 'http://books.google.com/cover.jpg'},
            'industryIdentifiers': [],
        }
        result = client_no_key._parse_volume_info(volume_info)
        assert result['cover_url'].startswith('https://')

    def test_no_image_links(self, client_no_key):
        volume_info = {
            'title': 'Book',
            'authors': [],
            'publishedDate': '2024',
            'description': 'A' * 30,
            'pageCount': 0,
            'language': 'en',
            'imageLinks': {},
            'industryIdentifiers': [],
        }
        result = client_no_key._parse_volume_info(volume_info)
        assert result['cover_url'] is None


class TestExtractISBN:
    """测试 _extract_isbn"""

    def test_found_isbn13(self, client_no_key):
        volume_info = {
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780000000001'},
                {'type': 'ISBN_10', 'identifier': '0000000001'},
            ]
        }
        assert client_no_key._extract_isbn(volume_info, 'ISBN_13') == '9780000000001'

    def test_found_isbn10(self, client_no_key):
        volume_info = {
            'industryIdentifiers': [
                {'type': 'ISBN_10', 'identifier': '0000000001'},
            ]
        }
        assert client_no_key._extract_isbn(volume_info, 'ISBN_10') == '0000000001'

    def test_not_found(self, client_no_key):
        volume_info = {'industryIdentifiers': []}
        assert client_no_key._extract_isbn(volume_info, 'ISBN_13') is None

    def test_no_identifiers(self, client_no_key):
        volume_info = {}
        assert client_no_key._extract_isbn(volume_info, 'ISBN_13') is None


class TestGetCoverUrl:
    """测试 get_cover_url"""

    def test_no_params(self, client_no_key):
        result = client_no_key.get_cover_url()
        assert result is None

    @patch.object(GoogleBooksClient, 'fetch_book_details')
    def test_by_isbn_with_cover(self, mock_fetch, client_no_key):
        mock_fetch.return_value = {'cover_url': 'https://example.com/cover.jpg'}
        result = client_no_key.get_cover_url(isbn='9780743273565')
        assert result == 'https://example.com/cover.jpg'

    @patch.object(GoogleBooksClient, 'fetch_book_details')
    def test_by_isbn_no_cover(self, mock_fetch, client_no_key):
        mock_fetch.return_value = {'cover_url': None}
        with patch.object(client_no_key, 'search_book_by_title', return_value={'cover_url': None}):
            result = client_no_key.get_cover_url(isbn='9780743273565', title='Test')
            assert result is None

    @patch.object(GoogleBooksClient, 'search_book_by_title')
    def test_by_title_with_cover(self, mock_search, client_no_key):
        mock_search.return_value = {'cover_url': 'https://example.com/cover.jpg'}
        result = client_no_key.get_cover_url(title='Test Book')
        assert result == 'https://example.com/cover.jpg'
