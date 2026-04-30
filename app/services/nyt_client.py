import logging
from typing import Any

import requests

from .api_utils import (
    create_session_with_retry, _get_api_cache_service,
    _safe_cache_set, api_retry
)
from ..utils.exceptions import APIRateLimitException, APIException
from ..utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class NYTApiClient:
    """纽约时报API客户端"""

    CACHE_TTL = 86400 * 7

    def __init__(self, api_key: str, base_url: str, rate_limiter: RateLimiter, timeout: int = 15):
        self._api_key = api_key
        self._base_url = base_url
        self._rate_limiter = rate_limiter
        self._timeout = timeout
        self._session = create_session_with_retry(max_retries=3)
        self._api_cache = None
        self._key_validated = False
        self._key_is_valid = False

    def _get_cache_service(self):
        if self._api_cache is None:
            self._api_cache = _get_api_cache_service()
        return self._api_cache

    def _validate_api_key(self) -> bool:
        """验证 NYT API Key 是否有效"""
        if self._key_validated:
            return self._key_is_valid

        if not self._api_key:
            self._key_validated = True
            self._key_is_valid = False
            logger.warning("NYT API Key 未配置")
            return False

        try:
            test_url = f"{self._base_url}/hardcover-fiction.json"
            resp = self._session.get(
                test_url,
                params={"api-key": self._api_key},
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                self._key_is_valid = True
                logger.info("NYT API Key 验证通过")
            elif resp.status_code == 401:
                logger.warning("NYT API Key 无效 (401 Unauthorized)，请检查 .env 中的 NYT_API_KEY")
                self._key_is_valid = False
            else:
                logger.warning("NYT API Key 验证异常 (状态码:%s)", resp.status_code)
                self._key_is_valid = False
        except Exception as e:
            logger.warning("NYT API Key 验证请求失败: %s", e)
            self._key_is_valid = False

        self._key_validated = True
        return self._key_is_valid

    @api_retry(max_attempts=3, backoff_factor=2.0)
    def fetch_books(self, category_id: str) -> dict[str, Any]:
        """获取指定分类的图书数据"""
        if not self._api_key:
            raise APIException("NYT API key not configured", 500)

        if not self._key_validated:
            self._validate_api_key()

        if not self._key_is_valid:
            raise APIException("NYT API key is invalid, please check your NYT_API_KEY in .env", 401)

        cache_service = self._get_cache_service()

        if cache_service:
            cached = cache_service.get('nyt', category_id)
            if cached:
                logger.info("返回NYT缓存数据: %s", category_id)
                return cached

        if not self._rate_limiter.is_allowed():
            retry_after = self._rate_limiter.get_retry_after()

            _safe_cache_set(cache_service, 'nyt', category_id,
                          {'error': 'rate_limit_exceeded'},
                          ttl_seconds=300, is_error=True,
                          error_message=f'Rate limited, retry after {retry_after}s')

            raise APIRateLimitException(
                f"API rate limit exceeded. Retry after {retry_after}s",
                retry_after
            )

        url = f"{self._base_url}/{category_id}.json"

        try:
            response = self._session.get(
                url,
                params={'api-key': self._api_key},
                timeout=self._timeout
            )

            if response.status_code == 401:
                self._key_is_valid = False
                self._key_validated = True
                logger.error("NYT API Key 认证失败 (401)，请检查 .env 中的 NYT_API_KEY")
                raise APIException("NYT API key authentication failed", 401)

            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                raise APIRateLimitException("API rate limited", retry_after)

            response.raise_for_status()
            data = response.json()

            _safe_cache_set(cache_service, 'nyt', category_id, data,
                          ttl_seconds=self.CACHE_TTL)

            return data

        except requests.Timeout:
            raise APIException(f"Request timeout for {category_id}", 504)
        except requests.RequestException as e:
            _safe_cache_set(cache_service, 'nyt', category_id,
                          {'error': str(e)}, ttl_seconds=60,
                          is_error=True, error_message=str(e))
            raise APIException(f"API request failed: {str(e)}", 502)
