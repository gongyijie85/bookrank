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
        if not self._api_key or not isbn:
            return {}
        
        url = f"{self._base_url}"
        params = {
            'q': f'isbn:{isbn}',
            'key': self._api_key
        }
        
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
            
            volume_info = data['items'][0]['volumeInfo']
            lang_code = volume_info.get('language', '').lower()
            
            from ..config import Config
            
            return {
                'publication_dt': volume_info.get('publishedDate', 'Unknown'),
                'details': volume_info.get('description', 'No detailed description available.'),
                'page_count': volume_info.get('pageCount', 'Unknown'),
                'language': Config.LANGUAGE_MAP.get(lang_code, lang_code)
            }
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch Google Books data for ISBN {isbn}: {e}")
            return {}


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
