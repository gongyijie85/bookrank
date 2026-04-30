import time
import logging
from typing import Any, Optional

import requests

from .api_utils import (
    create_session_with_retry, _get_api_cache_service,
    _safe_cache_set, api_retry
)

logger = logging.getLogger(__name__)


class GoogleBooksClient:
    """Google Books API客户端"""

    CACHE_TTL = 86400

    def __init__(self, api_key: Optional[str], base_url: str, timeout: int = 8):
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._session = create_session_with_retry(max_retries=2)
        self._api_cache = None
        self._key_validated = False
        self._key_is_valid = False

    def _get_cache_service(self):
        if self._api_cache is None:
            self._api_cache = _get_api_cache_service()
        return self._api_cache

    def _validate_api_key(self) -> bool:
        """验证 Google Books API Key 是否有效"""
        if self._key_validated:
            return self._key_is_valid

        if not self._api_key:
            self._key_validated = True
            self._key_is_valid = False
            return False

        try:
            resp = self._session.get(
                self._base_url,
                params={"q": "test", "maxResults": 1, "key": self._api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                self._key_is_valid = True
                logger.info("Google Books API Key 验证通过")
            elif resp.status_code == 400:
                logger.warning("Google Books API Key 无效，降级为无Key模式（配额较低）")
                self._key_is_valid = False
            else:
                logger.warning("Google Books API Key 验证异常 (状态码:%s)，降级为无Key模式", resp.status_code)
                self._key_is_valid = False
        except Exception as e:
            logger.warning("Google Books API Key 验证失败: %s，降级为无Key模式", e)
            self._key_is_valid = False

        self._key_validated = True
        return self._key_is_valid

    def _build_params(self, base_params: dict[str, Any]) -> dict[str, Any]:
        """构建请求参数，仅在Key有效时附加"""
        if self._key_is_valid and self._api_key:
            base_params["key"] = self._api_key
        return base_params

    @api_retry(max_attempts=2, backoff_factor=1.5)
    def fetch_book_details(self, isbn: str) -> dict[str, Any]:
        """获取图书详细信息"""
        if not isbn:
            return {}

        self._validate_api_key()

        cache_service = self._get_cache_service()
        cache_key = f"isbn_{isbn}"

        if cache_service:
            cached = cache_service.get('google_books', cache_key)
            if cached:
                logger.info("返回Google Books缓存数据: ISBN %s", isbn)
                return cached

        params = self._build_params({'q': f'isbn:{isbn}'})

        try:
            response = self._session.get(
                self._base_url,
                params=params,
                timeout=self._timeout
            )

            if response.status_code == 429:
                logger.warning("Google Books API 限流 (429)，等待2秒后重试...")
                time.sleep(2)
                response = self._session.get(
                    self._base_url,
                    params=params,
                    timeout=self._timeout
                )

            if response.status_code == 400 and self._key_is_valid:
                logger.warning("Google Books API Key 可能已失效，尝试无Key模式")
                self._key_is_valid = False
                params.pop("key", None)
                response = self._session.get(
                    self._base_url,
                    params=params,
                    timeout=self._timeout
                )

            response.raise_for_status()
            data = response.json()

            if 'items' not in data or len(data['items']) == 0:
                _safe_cache_set(cache_service, 'google_books', cache_key,
                              {}, ttl_seconds=self.CACHE_TTL)
                return {}

            result = self._parse_volume_info(data['items'][0]['volumeInfo'])

            _safe_cache_set(cache_service, 'google_books', cache_key,
                          result, ttl_seconds=self.CACHE_TTL)

            return result

        except requests.RequestException as e:
            logger.warning("Failed to fetch Google Books data for ISBN %s: %s", isbn, e)
            _safe_cache_set(cache_service, 'google_books', cache_key,
                          {}, ttl_seconds=300, is_error=True,
                          error_message=str(e))
            return {}

    @api_retry(max_attempts=2, backoff_factor=1.5)
    def search_book_by_title(self, title: str, author: str = None) -> dict[str, Any]:
        """根据书名搜索图书"""
        if not title:
            return {}

        self._validate_api_key()

        cache_key = f"title_{title.lower()}_{author.lower() if author else 'none'}"
        cache_service = self._get_cache_service()

        if cache_service:
            cached = cache_service.get('google_books', cache_key)
            if cached:
                logger.info("返回Google Books缓存搜索结果: '%s'", title)
                return cached

        query = f'intitle:{title}'
        if author:
            query += f' inauthor:{author}'

        params = self._build_params({'q': query, 'maxResults': 1})

        try:
            response = self._session.get(
                self._base_url,
                params=params,
                timeout=self._timeout
            )

            if response.status_code == 400 and self._key_is_valid:
                self._key_is_valid = False
                params.pop("key", None)
                response = self._session.get(
                    self._base_url,
                    params=params,
                    timeout=self._timeout
                )

            response.raise_for_status()
            data = response.json()

            if 'items' not in data or len(data['items']) == 0:
                _safe_cache_set(cache_service, 'google_books', cache_key,
                              {}, ttl_seconds=self.CACHE_TTL)
                return {}

            result = self._parse_volume_info(data['items'][0]['volumeInfo'])

            _safe_cache_set(cache_service, 'google_books', cache_key,
                          result, ttl_seconds=self.CACHE_TTL)

            return result

        except requests.RequestException as e:
            logger.warning("Failed to search Google Books for '%s': %s", title, e)
            _safe_cache_set(cache_service, 'google_books', cache_key,
                          {}, ttl_seconds=300, is_error=True,
                          error_message=str(e))
            return {}

    def _parse_volume_info(self, volume_info: dict[str, Any]) -> dict[str, Any]:
        """解析 Google Books API 返回的 volumeInfo"""
        lang_code = volume_info.get('language', '').lower()

        from ..config import Config

        image_links = volume_info.get('imageLinks', {})
        cover_url = (image_links.get('extraLarge') or
                    image_links.get('large') or
                    image_links.get('medium') or
                    image_links.get('small') or
                    image_links.get('thumbnail') or
                    image_links.get('smallThumbnail'))

        if cover_url and cover_url.startswith('http:'):
            cover_url = 'https:' + cover_url[5:]

        details = volume_info.get('description', '')
        if not details or len(details) < 20:
            subtitle = volume_info.get('subtitle', '')
            categories = volume_info.get('categories', [])
            parts = [p for p in [subtitle, ', '.join(categories[:3]) if categories else ''] if p]
            if parts:
                details = ' | '.join(parts)
            else:
                details = '暂无详细描述'

        return {
            'title': volume_info.get('title'),
            'authors': volume_info.get('authors', []),
            'publication_dt': volume_info.get('publishedDate', 'Unknown'),
            'details': details,
            'page_count': volume_info.get('pageCount', 'Unknown'),
            'language': Config.LANGUAGE_MAP.get(lang_code, lang_code),
            'cover_url': cover_url,
            'isbn_13': self._extract_isbn(volume_info, 'ISBN_13'),
            'isbn_10': self._extract_isbn(volume_info, 'ISBN_10'),
            'publisher': volume_info.get('publisher')
        }

    def _extract_isbn(self, volume_info: dict[str, Any], isbn_type: str) -> Optional[str]:
        """从 volumeInfo 中提取 ISBN"""
        identifiers = volume_info.get('industryIdentifiers', [])
        for identifier in identifiers:
            if identifier.get('type') == isbn_type:
                return identifier.get('identifier')
        return None

    def get_cover_url(self, isbn: str = None, title: str = None, author: str = None) -> Optional[str]:
        """获取图书封面URL"""
        if isbn:
            details = self.fetch_book_details(isbn)
            if details and details.get('cover_url'):
                return details['cover_url']

        if title:
            details = self.search_book_by_title(title, author)
            if details and details.get('cover_url'):
                return details['cover_url']

        return None
