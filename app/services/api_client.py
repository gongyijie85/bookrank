"""
API 客户端兼容入口

各客户端已拆分到独立模块：
- NYTApiClient → .nyt_client
- GoogleBooksClient → .google_books_client
- OpenLibraryClient → .open_library_client
- WikidataClient → .wikidata_client
- ImageCacheService → .api_utils
- 公共工具函数 → .api_utils

此文件保持向后兼容，所有旧导入路径继续有效。
"""

from .api_utils import (
    create_session_with_retry,
    _get_api_cache_service,
    _safe_cache_set,
    api_retry,
    ImageCacheService,
)
from .nyt_client import NYTApiClient
from .google_books_client import GoogleBooksClient
from .open_library_client import OpenLibraryClient
from .wikidata_client import WikidataClient

__all__ = [
    'create_session_with_retry',
    '_get_api_cache_service',
    '_safe_cache_set',
    'api_retry',
    'ImageCacheService',
    'NYTApiClient',
    'GoogleBooksClient',
    'OpenLibraryClient',
    'WikidataClient',
]
