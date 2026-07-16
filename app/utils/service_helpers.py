import hashlib
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from flask import current_app, request
from sqlalchemy.orm import Session

from ..services import BookService, CacheService, ImageCacheService
from ..services.api_client import GoogleBooksClient
from ..services.zhipu_translation_service import HybridTranslationService
from .error_handler import ErrorCategory, log_error

_background_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='bookrank-bg')


def submit_background_task(fn: Any, *args: Any, **kwargs: Any) -> Future:
    return _background_executor.submit(fn, *args, **kwargs)


def register_service(app: Any, name: str, service: Any) -> None:
    app.extensions[name] = service


def get_service(name: str) -> Any | None:
    """按名称获取已注册服务单例，缺失时返回 None"""
    return current_app.extensions.get(name)


def require_service(name: str, display_name: str = '') -> Any:
    """按名称获取已注册服务单例，缺失时抛出 RuntimeError"""
    service = get_service(name)
    if service is None:
        label = display_name or name.replace('_', ' ')
        raise RuntimeError(f'{label}未初始化，请检查应用配置')
    return service


def get_book_service() -> BookService | None:
    return get_service('book_service')


def get_cache_service() -> CacheService | None:
    return get_service('cache_service')


def get_image_cache_service() -> ImageCacheService | None:
    return get_service('image_cache_service')


def get_translation_service() -> HybridTranslationService | None:
    return get_service('translation_service')


def get_recommendation_service() -> Any | None:
    """获取已注册的 RecommendationService 单例，缺失时返回 None"""
    return get_service('recommendation_service')


def get_smart_search_service() -> Any | None:
    """获取已注册的 SmartSearchService 单例，缺失时返回 None"""
    return get_service('smart_search_service')


def _get_or_create_service(name: str, factory_path: str):
    """获取已注册服务；若未注册则按当前 CATEGORIES 兜底创建"""
    svc = get_service(name)
    if svc is not None:
        return svc
    module_path, class_name = factory_path.rsplit('.', 1)
    module = __import__(module_path, fromlist=[class_name])
    factory = getattr(module, class_name)
    categories = current_app.config.get('CATEGORIES', {})
    return factory(categories)


def get_or_create_recommendation_service() -> Any:
    """获取已注册的 RecommendationService；若未注册则按当前 CATEGORIES 兜底创建"""
    return _get_or_create_service('recommendation_service', 'app.services.recommendation_service.RecommendationService')


def get_or_create_smart_search_service() -> Any:
    """获取已注册的 SmartSearchService；若未注册则按当前 CATEGORIES 兜底创建"""
    return _get_or_create_service('smart_search_service', 'app.services.smart_search_service.SmartSearchService')


def require_book_service() -> BookService:
    return require_service('book_service', '图书服务')


def require_cache_service() -> CacheService:
    return require_service('cache_service', '缓存服务')


def require_translation_service() -> HybridTranslationService:
    return require_service('translation_service', '翻译服务')


def require_image_cache_service() -> ImageCacheService:
    return require_service('image_cache_service', '图片缓存服务')


@contextmanager
def db_transaction() -> Generator[Session]:
    from ..models.database import db

    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_error(ErrorCategory.UNKNOWN, f'数据库事务失败，已回滚: {e}')
        raise


def get_or_create_google_books_client() -> GoogleBooksClient:
    """获取 GoogleBooksClient，若未初始化则创建兜底实例"""
    client = get_google_books_client()
    if client:
        return client
    from ..config import Config
    from ..services.google_books_client import GoogleBooksClient

    return GoogleBooksClient(
        api_key=Config.GOOGLE_API_KEY,
        base_url='https://www.googleapis.com/books/v1/volumes',
    )


def get_google_books_client() -> GoogleBooksClient | None:
    book_service = get_book_service()
    if book_service and hasattr(book_service, '_google_client'):
        return book_service._google_client
    return None


def hash_client_ip(raw_ip: str | None = None) -> str | None:
    """对客户端 IP 进行 SHA-256 哈希（隐私保护）"""
    if raw_ip is None:
        raw_ip = request.remote_addr
    if not raw_ip:
        return None
    return hashlib.sha256((raw_ip or 'unknown').encode()).hexdigest()[:16]
