import time
import logging
from typing import Any, Optional

import requests

from .api_utils import (
    create_session_with_retry, _get_api_cache_service,
    _safe_cache_set, api_retry
)

logger = logging.getLogger(__name__)


class OpenLibraryClient:
    """
    Open Library API 客户端

    Open Library 是由 Internet Archive 维护的免费图书数据库
    优势：完全免费，无需 API Key，支持 ISBN 查询和封面图片

    API 文档：https://openlibrary.org/dev/docs/api/books
    """

    CACHE_TTL = 86400 * 3

    def __init__(self, timeout: int = 10):
        self._base_url = 'https://openlibrary.org'
        self._covers_url = 'https://covers.openlibrary.org'
        self._timeout = timeout
        self._session = create_session_with_retry(max_retries=2)
        self._session.headers.update({
            'User-Agent': 'BookRank/2.0 (bookrank@example.com)'
        })
        self._api_cache = None

    def _get_cache_service(self):
        if self._api_cache is None:
            self._api_cache = _get_api_cache_service()
        return self._api_cache

    @api_retry(max_attempts=2, backoff_factor=1.5)
    def fetch_book_by_isbn(self, isbn: str) -> dict[str, Any]:
        """通过 ISBN 获取图书详情"""
        if not isbn:
            return {}

        cache_service = self._get_cache_service()
        cache_key = f"isbn_{isbn}"

        if cache_service:
            cached = cache_service.get('open_library', cache_key)
            if cached:
                logger.info(f"返回Open Library缓存数据: ISBN {isbn}")
                return cached

        clean_isbn = isbn.replace('-', '').replace(' ', '')

        url = f"{self._base_url}/api/books"
        params = {
            'bibkeys': f'ISBN:{clean_isbn}',
            'format': 'json',
            'jscmd': 'data'
        }

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            key = f'ISBN:{clean_isbn}'
            if key not in data:
                logger.warning(f"No data found for ISBN: {isbn}")
                return {}

            book_data = data[key]
            result = self._parse_book_data(book_data, clean_isbn)

            _safe_cache_set(cache_service, 'open_library', cache_key,
                          result, ttl_seconds=self.CACHE_TTL)

            return result

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch Open Library data for ISBN {isbn}: {e}")
            _safe_cache_set(cache_service, 'open_library', cache_key,
                          {}, ttl_seconds=300, is_error=True,
                          error_message=str(e))
            return {}

    def _parse_book_data(self, book_data: dict[str, Any], isbn: str) -> dict[str, Any]:
        """解析 Open Library 返回的图书数据"""
        authors = []
        if 'authors' in book_data:
            authors = [author.get('name', '') for author in book_data['authors']]

        publish_date = book_data.get('publish_date', 'Unknown')
        publishers = []
        if 'publishers' in book_data:
            publishers = [pub.get('name', '') for pub in book_data['publishers']]

        cover_url = None
        if 'cover' in book_data:
            cover = book_data['cover']
            cover_url = (cover.get('large') or
                        cover.get('medium') or
                        cover.get('small'))

        pages = book_data.get('number_of_pages', 'Unknown')

        description = ''
        if 'description' in book_data:
            desc = book_data['description']
            if isinstance(desc, dict):
                description = desc.get('value', '')
            else:
                description = str(desc)

        return {
            'title': book_data.get('title'),
            'authors': authors,
            'author': ', '.join(authors) if authors else None,
            'publisher': publishers[0] if publishers else None,
            'publish_date': publish_date,
            'pages': pages,
            'description': description or 'No description available.',
            'cover_url': cover_url,
            'isbn_13': isbn if len(isbn) == 13 else None,
            'isbn_10': isbn if len(isbn) == 10 else None,
            'source': 'open_library'
        }

    def get_cover_url(self, isbn: str, size: str = 'L') -> Optional[str]:
        """获取 Open Library 封面图片 URL"""
        if not isbn:
            return None

        clean_isbn = isbn.replace('-', '').replace(' ', '')

        size = size.upper()
        if size not in ['S', 'M', 'L']:
            size = 'L'

        cover_url = f"{self._covers_url}/b/isbn/{clean_isbn}-{size}.jpg"

        try:
            response = self._session.head(cover_url, timeout=5)
            if response.status_code == 200:
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > 100:
                    return cover_url
        except requests.RequestException:
            pass

        return None

    def search_books(self, query: str, limit: int = 10) -> list:
        """搜索图书"""
        url = f"{self._base_url}/search.json"
        params = {
            'q': query,
            'limit': limit
        }

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            books = []
            for doc in data.get('docs', []):
                book = {
                    'title': doc.get('title'),
                    'authors': doc.get('author_name', []),
                    'author': ', '.join(doc.get('author_name', [])),
                    'first_publish_year': doc.get('first_publish_year'),
                    'isbn': doc.get('isbn', [None])[0] if doc.get('isbn') else None,
                    'cover_id': doc.get('cover_i')
                }
                books.append(book)

            return books

        except requests.RequestException as e:
            logger.warning(f"Failed to search Open Library: {e}")
            return []
