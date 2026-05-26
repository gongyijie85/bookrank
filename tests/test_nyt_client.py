"""NYT API 客户端测试"""

from unittest.mock import MagicMock

import pytest
import requests

from app.services.nyt_client import NYTApiClient
from app.utils.exceptions import APIException, APIRateLimitException
from app.utils.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    rl = MagicMock(spec=RateLimiter)
    rl.is_allowed.return_value = True
    rl.get_retry_after.return_value = 60
    return rl


@pytest.fixture
def nyt_client(rate_limiter):
    c = NYTApiClient(
        api_key='test-key', base_url='https://api.nytimes.com/svc/books/v3/lists', rate_limiter=rate_limiter
    )
    c._session = MagicMock()
    return c


@pytest.fixture
def nyt_client_no_key(rate_limiter):
    c = NYTApiClient(api_key='', base_url='https://api.nytimes.com/svc/books/v3/lists', rate_limiter=rate_limiter)
    c._session = MagicMock()
    return c


class TestInit:
    def test_default_cache_ttl(self, nyt_client):
        assert nyt_client._cache_ttl == 86400 * 7

    def test_custom_cache_ttl(self, rate_limiter):
        c = NYTApiClient(api_key='k', base_url='url', rate_limiter=rate_limiter, cache_ttl=600)
        assert c._cache_ttl == 600


class TestValidateApiKey:
    def test_no_key(self, nyt_client_no_key):
        assert nyt_client_no_key._validate_api_key() is False

    def test_valid_key(self, nyt_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        nyt_client._session.get.return_value = mock_resp
        assert nyt_client._validate_api_key() is True

    def test_invalid_key_401(self, nyt_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        nyt_client._session.get.return_value = mock_resp
        assert nyt_client._validate_api_key() is False

    def test_unexpected_status(self, nyt_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        nyt_client._session.get.return_value = mock_resp
        assert nyt_client._validate_api_key() is False

    def test_network_error(self, nyt_client):
        nyt_client._session.get.side_effect = Exception('Network error')
        assert nyt_client._validate_api_key() is False

    def test_cached_validation(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        assert nyt_client._validate_api_key() is True


class TestFetchBooks:
    def test_no_api_key(self, nyt_client_no_key):
        with pytest.raises(APIException, match='not configured'):
            nyt_client_no_key.fetch_books('hardcover-fiction')

    def test_invalid_key(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = False
        with pytest.raises(APIException, match='invalid'):
            nyt_client.fetch_books('hardcover-fiction')

    def test_cache_hit(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = {'results': []}
        nyt_client._api_cache = mock_cache

        result = nyt_client.fetch_books('hardcover-fiction')
        assert result == {'results': []}

    def test_cache_hit_error_skipped(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = {'error': 'something'}
        nyt_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'results': [{'books': []}]}
        mock_resp.raise_for_status = MagicMock()
        nyt_client._session.get.return_value = mock_resp

        result = nyt_client.fetch_books('hardcover-fiction')
        assert result is not None

    def test_rate_limited(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        nyt_client._rate_limiter.is_allowed.return_value = False
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        nyt_client._api_cache = mock_cache

        with pytest.raises(APIRateLimitException):
            nyt_client.fetch_books('hardcover-fiction')

    def test_api_success(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        nyt_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'results': [{'books': []}]}
        mock_resp.raise_for_status = MagicMock()
        nyt_client._session.get.return_value = mock_resp

        result = nyt_client.fetch_books('hardcover-fiction')
        assert result == {'results': [{'books': []}]}

    def test_api_401(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        nyt_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        nyt_client._session.get.return_value = mock_resp

        with pytest.raises(APIException, match='authentication failed'):
            nyt_client.fetch_books('hardcover-fiction')

    def test_api_429(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        nyt_client._api_cache = mock_cache

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {'Retry-After': '30'}
        nyt_client._session.get.return_value = mock_resp

        with pytest.raises(APIRateLimitException):
            nyt_client.fetch_books('hardcover-fiction')

    def test_api_timeout(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        nyt_client._api_cache = mock_cache

        nyt_client._session.get.side_effect = requests.Timeout('timeout')

        with pytest.raises(APIException, match='timeout'):
            nyt_client.fetch_books('hardcover-fiction')

    def test_api_request_exception(self, nyt_client):
        nyt_client._key_validated = True
        nyt_client._key_is_valid = True
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        nyt_client._api_cache = mock_cache

        nyt_client._session.get.side_effect = requests.RequestException('connection error')

        with pytest.raises(APIException, match='failed'):
            nyt_client.fetch_books('hardcover-fiction')
