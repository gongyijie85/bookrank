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
        # 按 key 精确返回：退避标记键（__quota_blocked__）必须为假，
        # 否则「对所有键都返回同一真值」的宽 mock 会被误判成"正在配额退避"而短路。
        mock_cache_service.get.side_effect = lambda _namespace, key: (
            {'title': 'Cached Book'} if key == 'isbn_9780743273565' else None
        )
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
        # 拼不出任何有信息量的描述时留空，**不回填占位串**：
        # 占位串是真值，会让下游「有值即已补全」的判断恒为真，封死详情补齐路径
        # （见 app/utils/api_helpers.py 的 PLACEHOLDER_TEXTS）。
        assert result['details'] == ''

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


class _RecordingCache:
    """最小缓存替身：记录 set/get，用来断言退避标记是否被置上。"""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], object] = {}

    def get(self, namespace: str, key: str):
        return self.store.get((namespace, key))

    def set(self, namespace: str, key: str, data, ttl_seconds: int = 300, **_kwargs) -> None:
        self.store[(namespace, key)] = data


class TestQuotaBackoff:
    """配额耗尽时必须**退避**，而不是按 ISBN 反复重试把 1000 次/天的配额烧穿。

    实测（2026-09-17）：Google Books 默认配额是 1000 次/天/项目，而一次全量刷新就要按
    ISBN 查询 200+ 次。旧实现只把错误按 ISBN 缓存 300 秒 → 每个 ISBN 周期性重试 →
    配额被持续烧穿、当天再也不会恢复，全站 GB 来源字段（language/page_count/
    publication_dt）退化为 Unknown。
    """

    @staticmethod
    def _client_with_cache():
        client = GoogleBooksClient(api_key=None, base_url='https://example.invalid/volumes')
        client._session = MagicMock()
        cache = _RecordingCache()
        client._api_cache = cache
        return client, cache

    @staticmethod
    def _resp(status: int) -> MagicMock:
        response = MagicMock()
        response.status_code = status
        response.json.return_value = {}
        return response

    def test_429_sets_a_shared_backoff_marker(self):
        client, cache = self._client_with_cache()
        client._session.get.return_value = self._resp(429)

        assert client.fetch_book_details('9780000000001') == {}

        assert cache.get('google_books', client._QUOTA_BLOCKED_KEY) is True, '命中 429 后应置上全局退避标记'

    def test_calls_inside_the_backoff_window_skip_the_network(self):
        client, _cache = self._client_with_cache()
        client._session.get.return_value = self._resp(429)
        client.fetch_book_details('9780000000001')
        calls_after_first = client._session.get.call_count

        # 换一个完全不同的 ISBN：退避窗口内必须直接短路，不再打上游
        assert client.fetch_book_details('9780000000002') == {}
        assert client._session.get.call_count == calls_after_first, '退避窗口内不该再请求上游'

    def test_backoff_also_guards_title_search(self):
        client, _cache = self._client_with_cache()
        client._session.get.return_value = self._resp(429)
        client.search_book_by_title('Some Book')
        calls = client._session.get.call_count

        assert client.search_book_by_title('Another Book') == {}
        assert client._session.get.call_count == calls

    def test_successful_lookup_does_not_enter_backoff(self):
        client, cache = self._client_with_cache()
        ok = self._resp(200)
        ok.json.return_value = {'items': [{'volumeInfo': {'title': 'T', 'description': 'x' * 40}}]}
        client._session.get.return_value = ok

        assert client.fetch_book_details('9780000000003')['title'] == 'T'
        assert cache.get('google_books', client._QUOTA_BLOCKED_KEY) is None

    def test_backoff_ttl_is_hours_not_minutes(self):
        """退避太短等于没退避：必须显著长于旧的 300 秒错误缓存。"""
        assert GoogleBooksClient.DEFAULT_QUOTA_BACKOFF_TTL >= 1800
