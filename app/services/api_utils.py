import time
import hashlib
import logging
from pathlib import Path
from collections import OrderedDict
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..utils.exceptions import APIRateLimitException, APIException

logger = logging.getLogger(__name__)


def create_session_with_retry(max_retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """创建配置了重试机制的 requests Session"""
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


def api_retry(max_attempts: int = 3, backoff_factor: float = 2.0):
    """基于 tenacity 的 API 重试装饰器（替代自定义 retry）"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_factor, min=1, max=30),
        retry=retry_if_exception_type((requests.RequestException,)),
        reraise=True,
    )


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
        """获取缓存的图片URL"""
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
