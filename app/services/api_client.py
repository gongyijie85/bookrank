import time
import logging
import hashlib
from pathlib import Path
from functools import wraps
from collections import OrderedDict
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..utils.exceptions import APIRateLimitException, APIException
from ..utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, backoff_factor: float = 2.0,
          exceptions=(requests.RequestException,)):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        return wrapper
    return decorator


def create_session_with_retry(max_retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """
    创建配置了重试机制的 requests Session

    Args:
        max_retries: 最大重试次数
        backoff_factor: 退避因子

    Returns:
        配置好的 Session 对象
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )

    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=retry_strategy
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update({
        'User-Agent': 'BookRank/2.0 (https://github.com/gongyijie85/bookrank)',
        'Accept': 'application/json',
    })

    return session


def _get_api_cache_service():
    """获取API缓存服务（公共函数，避免重复代码）"""
    try:
        from .api_cache_service import get_api_cache_service
        return get_api_cache_service()
    except Exception as e:
        logger.warning(f"API缓存服务初始化失败: {e}")
        return None


def _safe_cache_set(cache_service, namespace: str, key: str, data: Any,
                    ttl_seconds: int = 300, is_error: bool = False,
                    error_message: str = '') -> None:
    """安全写入缓存，忽略失败"""
    if not cache_service:
        return
    try:
        cache_service.set(namespace, key, data, ttl_seconds=ttl_seconds,
                         is_error=is_error, error_message=error_message)
    except Exception:
        pass


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
        """获取API缓存服务"""
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

    @retry(max_attempts=3, backoff_factor=2.0)
    def fetch_books(self, category_id: str) -> dict[str, Any]:
        """
        获取指定分类的图书数据

        Args:
            category_id: 分类ID

        Returns:
            API响应数据

        Raises:
            APIRateLimitException: 当API限流时
            APIException: 当API调用失败时
        """
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
        """获取API缓存服务"""
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

    @retry(max_attempts=2, backoff_factor=1.5)
    def fetch_book_details(self, isbn: str) -> dict[str, Any]:
        """
        获取图书详细信息

        Args:
            isbn: 图书ISBN

        Returns:
            图书详细信息字典
        """
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
                wait_time = 2
                logger.warning(f"Google Books API 限流 (429)，等待 {wait_time}秒后重试...")
                time.sleep(wait_time)
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

    @retry(max_attempts=2, backoff_factor=1.5)
    def search_book_by_title(self, title: str, author: str = None) -> dict[str, Any]:
        """
        根据书名搜索图书

        Args:
            title: 图书标题
            author: 作者（可选，用于提高搜索精度）

        Returns:
            图书详细信息字典
        """
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

        # 获取详细描述：优先使用 description，回退到 subtitle 或 categories
        details = volume_info.get('description', '')
        if not details or len(details) < 20:
            # 尝试组合 subtitle + categories 作为描述
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
        """
        获取图书封面URL

        Args:
            isbn: ISBN（优先使用）
            title: 书名（当ISBN搜索失败时使用）
            author: 作者（可选）

        Returns:
            封面图片URL或None
        """
        if isbn:
            details = self.fetch_book_details(isbn)
            if details and details.get('cover_url'):
                return details['cover_url']

        if title:
            details = self.search_book_by_title(title, author)
            if details and details.get('cover_url'):
                return details['cover_url']

        return None


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
        """获取API缓存服务"""
        if self._api_cache is None:
            self._api_cache = _get_api_cache_service()
        return self._api_cache

    @retry(max_attempts=2, backoff_factor=1.5)
    def fetch_book_by_isbn(self, isbn: str) -> dict[str, Any]:
        """
        通过 ISBN 获取图书详情

        Args:
            isbn: 图书 ISBN-10 或 ISBN-13

        Returns:
            图书详细信息字典
        """
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
        """
        获取 Open Library 封面图片 URL

        Args:
            isbn: 图书 ISBN
            size: 图片尺寸 ('S'=小, 'M'=中, 'L'=大)

        Returns:
            封面图片 URL 或 None
        """
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
        """
        搜索图书

        Args:
            query: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            图书列表
        """
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


class WikidataClient:
    """
    Wikidata SPARQL API 客户端

    用于批量获取图书奖项获奖数据
    Wikidata 是维基百科的结构化数据存储库

    API 文档：https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service
    """

    AWARD_IDS = {
        'nebula': 'Q327503',
        'hugo': 'Q162455',
        'booker': 'Q155091',
        'international_booker': 'Q2519161',
        'pulitzer_fiction': 'Q162530',
        'edgar': 'Q532244',
        'nobel_literature': 'Q37922',
    }

    def __init__(self, timeout: int = 60):
        self._base_url = 'https://query.wikidata.org/sparql'
        self._timeout = timeout
        self._session = create_session_with_retry(max_retries=1)
        self._session.headers.update({
            'User-Agent': 'BookRank/2.0 (bookrank@example.com)',
            'Accept': 'application/sparql-results+json'
        })

    @retry(max_attempts=2, backoff_factor=1.5)
    def query_award_winners(self, award_key: str, start_year: int = 2020,
                           end_year: int = 2025, limit: int = 100) -> list:
        """
        查询指定奖项的获奖图书

        Args:
            award_key: 奖项键名 (nebula, hugo, booker 等)
            start_year: 开始年份
            end_year: 结束年份
            limit: 结果数量限制

        Returns:
            获奖图书列表
        """
        award_id = self.AWARD_IDS.get(award_key)
        if not award_id:
            logger.error(f"Unknown award: {award_key}")
            return []

        sparql_query = self._build_sparql_query(award_id, start_year, end_year, limit)

        try:
            response = self._session.get(
                self._base_url,
                params={'query': sparql_query, 'format': 'json'},
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_sparql_results(data, award_key)

        except requests.RequestException as e:
            logger.warning(f"Failed to query Wikidata for {award_key}: {e}")
            return []

    def _build_sparql_query(self, award_id: str, start_year: int,
                           end_year: int, limit: int) -> str:
        """构建 SPARQL 查询语句"""
        return f"""
        SELECT DISTINCT ?book ?bookLabel ?author ?authorLabel ?isbn13 ?isbn10
                        ?publicationDate ?year ?publisher ?publisherLabel
        WHERE {{
          ?book wdt:P31 wd:Q7725634 ;
                wdt:P166 wd:{award_id} ;
                wdt:P1476 ?bookLabel ;
                wdt:P50 ?author ;
                wdt:P577 ?publicationDate .

          ?author rdfs:label ?authorLabel .
          FILTER(LANG(?authorLabel) = "en")

          OPTIONAL {{ ?book wdt:P212 ?isbn13 }}
          OPTIONAL {{ ?book wdt:P957 ?isbn10 }}

          OPTIONAL {{
            ?book wdt:P123 ?publisher .
            ?publisher rdfs:label ?publisherLabel .
            FILTER(LANG(?publisherLabel) = "en")
          }}

          BIND(YEAR(?publicationDate) AS ?year)
          FILTER(?year >= {start_year} && ?year <= {end_year})
          FILTER(LANG(?bookLabel) = "en")
        }}
        ORDER BY DESC(?year)
        LIMIT {limit}
        """

    def _parse_sparql_results(self, data: dict, award_key: str) -> list:
        """解析 SPARQL 查询结果"""
        books = []

        bindings = data.get('results', {}).get('bindings', [])

        for binding in bindings:
            book = {
                'award': award_key,
                'wikidata_id': binding.get('book', {}).get('value', '').split('/')[-1],
                'title': binding.get('bookLabel', {}).get('value', ''),
                'author_wikidata_id': binding.get('author', {}).get('value', '').split('/')[-1],
                'author': binding.get('authorLabel', {}).get('value', ''),
                'isbn13': binding.get('isbn13', {}).get('value', ''),
                'isbn10': binding.get('isbn10', {}).get('value', ''),
                'publication_date': binding.get('publicationDate', {}).get('value', ''),
                'year': int(binding.get('year', {}).get('value', 0)),
                'publisher': binding.get('publisherLabel', {}).get('value', ''),
            }
            books.append(book)

        return books

    def get_all_award_books(self, awards: list | None = None, start_year: int = 2020,
                           end_year: int = 2025) -> dict:
        """
        获取多个奖项的获奖图书

        Args:
            awards: 奖项键名列表，None 表示所有奖项
            start_year: 开始年份
            end_year: 结束年份

        Returns:
            按奖项分组的图书字典
        """
        if awards is None:
            awards = list(self.AWARD_IDS.keys())

        results = {}

        for award_key in awards:
            logger.info(f"查询 {award_key} 获奖图书...")
            books = self.query_award_winners(award_key, start_year, end_year)
            results[award_key] = books
            logger.info(f"{award_key}: 找到 {len(books)} 本图书")

            time.sleep(0.5)

        return results

    @retry(max_attempts=2, backoff_factor=1.5)
    def query_award_info(self, award_key: str) -> dict:
        """
        查询奖项的详细信息

        Args:
            award_key: 奖项键名 (nebula, hugo, booker 等)

        Returns:
            奖项信息字典
        """
        award_id = self.AWARD_IDS.get(award_key)
        if not award_id:
            logger.error(f"Unknown award: {award_key}")
            return {}

        sparql_query = self._build_award_info_query(award_id)

        try:
            response = self._session.get(
                self._base_url,
                params={'query': sparql_query, 'format': 'json'},
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_award_info(data, award_key)

        except requests.RequestException as e:
            logger.warning(f"Failed to query award info for {award_key}: {e}")
            return {}

    def _build_award_info_query(self, award_id: str) -> str:
        """构建查询奖项信息的 SPARQL 语句"""
        return f"""
        SELECT DISTINCT ?award ?awardLabel ?awardDescription
                        ?country ?countryLabel
                        ?inception ?categoryCount
        WHERE {{
          BIND(wd:{award_id} AS ?award)

          ?award rdfs:label ?awardLabel .
          FILTER(LANG(?awardLabel) = "en")

          ?award schema:description ?awardDescription .
          FILTER(LANG(?awardDescription) = "en")

          OPTIONAL {{
            ?award wdt:P17 ?country .
            ?country rdfs:label ?countryLabel .
            FILTER(LANG(?countryLabel) = "en")
          }}

          OPTIONAL {{ ?award wdt:P571 ?inception }}
          OPTIONAL {{ ?award wdt:P2517 ?categoryCount }}
        }}
        LIMIT 1
        """

    def _parse_award_info(self, data: dict, award_key: str) -> dict:
        """解析奖项信息查询结果"""
        bindings = data.get('results', {}).get('bindings', [])

        if not bindings:
            logger.warning(f"No award info found for {award_key}")
            return {}

        binding = bindings[0]

        inception = binding.get('inception', {}).get('value', '')
        established_year = None
        if inception:
            try:
                established_year = int(inception[:4])
            except (ValueError, IndexError):
                pass

        category_count = binding.get('categoryCount', {}).get('value', '')
        try:
            category_count = int(category_count) if category_count else None
        except ValueError:
            category_count = None

        return {
            'award_key': award_key,
            'wikidata_id': binding.get('award', {}).get('value', '').split('/')[-1],
            'name_en': binding.get('awardLabel', {}).get('value', ''),
            'description_en': binding.get('awardDescription', {}).get('value', ''),
            'country_en': binding.get('countryLabel', {}).get('value', ''),
            'established_year': established_year,
            'category_count': category_count,
        }

    def get_all_award_info(self, awards: list | None = None) -> dict:
        """
        获取多个奖项的详细信息

        Args:
            awards: 奖项键名列表，None 表示所有奖项

        Returns:
            按奖项键名分组的奖项信息字典
        """
        if awards is None:
            awards = list(self.AWARD_IDS.keys())

        results = {}

        for award_key in awards:
            logger.info(f"查询 {award_key} 奖项信息...")
            info = self.query_award_info(award_key)
            if info:
                results[award_key] = info
                logger.info(f"{award_key}: 获取到奖项信息")
            else:
                logger.warning(f"{award_key}: 未能获取奖项信息")

            time.sleep(0.3)

        return results


class ImageCacheService:
    """图片缓存服务"""

    def __init__(self, cache_dir: Path, default_cover: str = '/static/default-cover.png'):
        self._cache_dir = cache_dir
        self._default_cover = default_cover
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache = OrderedDict()
        self._memory_cache_ttl = 3600
        self._memory_cache_max_size = 1000
        self._session = create_session_with_retry(max_retries=2)

    def get_cached_image_url(self, original_url: str, ttl: int = 3600) -> str:
        """
        获取缓存的图片URL

        Args:
            original_url: 原始图片URL
            ttl: 缓存过期时间（秒）

        Returns:
            缓存后的图片URL或默认封面
        """
        if not original_url:
            return self._default_cover

        current_time = time.time()
        if original_url in self._memory_cache:
            cached_path, timestamp = self._memory_cache[original_url]
            if current_time - timestamp < self._memory_cache_ttl:
                self._memory_cache.move_to_end(original_url)
                logger.info(f"Returning image from memory cache: {original_url}")
                return cached_path
            else:
                del self._memory_cache[original_url]

        filename = hashlib.md5(original_url.encode()).hexdigest() + '.jpg'
        cache_path = self._cache_dir / filename
        relative_path = f'/cache/images/{filename}'

        if cache_path.exists():
            try:
                file_age = time.time() - cache_path.stat().st_mtime
                if file_age < ttl:
                    self._update_memory_cache(original_url, relative_path, current_time)
                    return relative_path
            except OSError as e:
                logger.warning(f"Error checking cache file: {e}")

        try:
            response = self._session.get(original_url, timeout=10, stream=True)
            response.raise_for_status()

            with open(cache_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)

            self._update_memory_cache(original_url, relative_path, current_time)
            return relative_path

        except Exception as e:
            logger.warning(f"Failed to cache image from {original_url}: {e}")
            return self._default_cover

    def _update_memory_cache(self, key: str, value: str, timestamp: float):
        """更新内存缓存，确保不超过最大大小"""
        if key in self._memory_cache:
            del self._memory_cache[key]
        elif len(self._memory_cache) >= self._memory_cache_max_size:
            self._memory_cache.popitem(last=False)
        self._memory_cache[key] = (value, timestamp)
        self._memory_cache.move_to_end(key)
