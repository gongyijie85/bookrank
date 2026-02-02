import time
import logging
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from functools import wraps

import requests

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


class NYTApiClient:
    """纽约时报API客户端"""
    
    def __init__(self, api_key: str, base_url: str, rate_limiter: RateLimiter, timeout: int = 15):
        self._api_key = api_key
        self._base_url = base_url
        self._rate_limiter = rate_limiter
        self._timeout = timeout
        self._session = requests.Session()
    
    @retry(max_attempts=3, backoff_factor=2.0)
    def fetch_books(self, category_id: str) -> Dict[str, Any]:
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
        
        # 检查限流
        if not self._rate_limiter.is_allowed():
            retry_after = self._rate_limiter.get_retry_after()
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
            
            # 处理限流响应
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                raise APIRateLimitException("API rate limited", retry_after)
            
            response.raise_for_status()
            return response.json()
            
        except requests.Timeout:
            raise APIException(f"Request timeout for {category_id}", 504)
        except requests.RequestException as e:
            raise APIException(f"API request failed: {str(e)}", 502)


class GoogleBooksClient:
    """Google Books API客户端"""
    
    def __init__(self, api_key: Optional[str], base_url: str, timeout: int = 8):
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._session = requests.Session()
    
    @retry(max_attempts=2, backoff_factor=1.5)
    def fetch_book_details(self, isbn: str) -> Dict[str, Any]:
        """
        获取图书详细信息
        
        Args:
            isbn: 图书ISBN
            
        Returns:
            图书详细信息字典
        """
        if not isbn:
            return {}
        
        url = f"{self._base_url}"
        params = {
            'q': f'isbn:{isbn}'
        }
        # API Key 是可选的
        if self._api_key:
            params['key'] = self._api_key
        
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if 'items' not in data or len(data['items']) == 0:
                return {}
            
            return self._parse_volume_info(data['items'][0]['volumeInfo'])
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch Google Books data for ISBN {isbn}: {e}")
            return {}
    
    @retry(max_attempts=2, backoff_factor=1.5)
    def search_book_by_title(self, title: str, author: str = None) -> Dict[str, Any]:
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
        
        url = f"{self._base_url}"
        # 构建搜索查询
        query = f'intitle:{title}'
        if author:
            query += f' inauthor:{author}'
        
        params = {
            'q': query,
            'maxResults': 1
        }
        if self._api_key:
            params['key'] = self._api_key
        
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if 'items' not in data or len(data['items']) == 0:
                return {}
            
            return self._parse_volume_info(data['items'][0]['volumeInfo'])
            
        except requests.RequestException as e:
            logger.warning(f"Failed to search Google Books for '{title}': {e}")
            return {}
    
    def _parse_volume_info(self, volume_info: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Google Books API 返回的 volumeInfo"""
        lang_code = volume_info.get('language', '').lower()
        
        from ..config import Config
        
        # 获取封面图片URL（优先使用大尺寸的）
        image_links = volume_info.get('imageLinks', {})
        cover_url = (image_links.get('extraLarge') or 
                    image_links.get('large') or 
                    image_links.get('medium') or 
                    image_links.get('small') or 
                    image_links.get('thumbnail') or 
                    image_links.get('smallThumbnail'))
        
        # 处理 HTTP 图片URL（转换为HTTPS）
        if cover_url and cover_url.startswith('http:'):
            cover_url = 'https:' + cover_url[5:]
        
        return {
            'title': volume_info.get('title'),
            'authors': volume_info.get('authors', []),
            'publication_dt': volume_info.get('publishedDate', 'Unknown'),
            'details': volume_info.get('description', 'No detailed description available.'),
            'page_count': volume_info.get('pageCount', 'Unknown'),
            'language': Config.LANGUAGE_MAP.get(lang_code, lang_code),
            'cover_url': cover_url,
            'isbn_13': self._extract_isbn(volume_info, 'ISBN_13'),
            'isbn_10': self._extract_isbn(volume_info, 'ISBN_10'),
            'publisher': volume_info.get('publisher')
        }
    
    def _extract_isbn(self, volume_info: Dict[str, Any], isbn_type: str) -> Optional[str]:
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
        # 优先使用ISBN搜索
        if isbn:
            details = self.fetch_book_details(isbn)
            if details and details.get('cover_url'):
                return details['cover_url']
        
        # 如果ISBN搜索失败，使用书名搜索
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
    
    def __init__(self, timeout: int = 10):
        self._base_url = 'https://openlibrary.org'
        self._covers_url = 'https://covers.openlibrary.org'
        self._timeout = timeout
        self._session = requests.Session()
        # 设置请求头，避免被阻止
        self._session.headers.update({
            'User-Agent': 'BookRank/1.0 (bookrank@example.com)'
        })
    
    @retry(max_attempts=2, backoff_factor=1.5)
    def fetch_book_by_isbn(self, isbn: str) -> Dict[str, Any]:
        """
        通过 ISBN 获取图书详情
        
        Args:
            isbn: 图书 ISBN-10 或 ISBN-13
            
        Returns:
            图书详细信息字典
        """
        if not isbn:
            return {}
        
        # 清理 ISBN（移除连字符和空格）
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
            
            # Open Library 返回的键格式为 "ISBN:xxxx"
            key = f'ISBN:{clean_isbn}'
            if key not in data:
                logger.warning(f"No data found for ISBN: {isbn}")
                return {}
            
            book_data = data[key]
            return self._parse_book_data(book_data, clean_isbn)
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch Open Library data for ISBN {isbn}: {e}")
            return {}
    
    def _parse_book_data(self, book_data: Dict[str, Any], isbn: str) -> Dict[str, Any]:
        """解析 Open Library 返回的图书数据"""
        
        # 获取作者信息
        authors = []
        if 'authors' in book_data:
            authors = [author.get('name', '') for author in book_data['authors']]
        
        # 获取出版信息
        publish_date = book_data.get('publish_date', 'Unknown')
        publishers = []
        if 'publishers' in book_data:
            publishers = [pub.get('name', '') for pub in book_data['publishers']]
        
        # 获取封面信息
        cover_url = None
        if 'cover' in book_data:
            cover = book_data['cover']
            # 优先使用大封面
            cover_url = (cover.get('large') or 
                        cover.get('medium') or 
                        cover.get('small'))
        
        # 获取页数
        pages = book_data.get('number_of_pages', 'Unknown')
        
        # 获取描述
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
        
        # 清理 ISBN
        clean_isbn = isbn.replace('-', '').replace(' ', '')
        
        # 验证尺寸参数
        size = size.upper()
        if size not in ['S', 'M', 'L']:
            size = 'L'
        
        # 构建封面 URL
        cover_url = f"{self._covers_url}/b/isbn/{clean_isbn}-{size}.jpg"
        
        # 检查封面是否存在（Open Library 会返回 1x1 像素的占位图如果不存在）
        try:
            response = self._session.head(cover_url, timeout=5)
            if response.status_code == 200:
                # 检查内容长度，排除占位图
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


class ImageCacheService:
    """图片缓存服务"""
    
    def __init__(self, cache_dir: Path, default_cover: str = '/static/default-cover.png'):
        self._cache_dir = cache_dir
        self._default_cover = default_cover
        self._cache_dir.mkdir(parents=True, exist_ok=True)
    
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
        
        # 生成安全的文件名
        filename = hashlib.md5(original_url.encode()).hexdigest() + '.jpg'
        cache_path = self._cache_dir / filename
        relative_path = f'/cache/images/{filename}'
        
        # 检查缓存是否有效
        if cache_path.exists():
            try:
                file_age = time.time() - cache_path.stat().st_mtime
                if file_age < ttl:
                    return relative_path
            except OSError:
                pass
        
        # 下载并缓存图片
        try:
            response = requests.get(original_url, timeout=10, stream=True)
            response.raise_for_status()
            
            with open(cache_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            
            return relative_path
            
        except Exception as e:
            logger.warning(f"Failed to cache image from {original_url}: {e}")
            return self._default_cover
