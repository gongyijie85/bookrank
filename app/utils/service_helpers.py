from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from flask import current_app
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


def get_book_service() -> BookService | None:
    return current_app.extensions.get('book_service')


def get_cache_service() -> CacheService | None:
    return current_app.extensions.get('cache_service')


def get_image_cache_service() -> ImageCacheService | None:
    return current_app.extensions.get('image_cache_service')


def get_translation_service() -> HybridTranslationService | None:
    return current_app.extensions.get('translation_service')


def require_book_service() -> BookService:
    service = get_book_service()
    if service is None:
        raise RuntimeError('图书服务未初始化，请检查应用配置')
    return service


def require_cache_service() -> CacheService:
    service = get_cache_service()
    if service is None:
        raise RuntimeError('缓存服务未初始化，请检查应用配置')
    return service


def require_translation_service() -> HybridTranslationService:
    service = get_translation_service()
    if service is None:
        raise RuntimeError('翻译服务未初始化，请检查应用配置')
    return service


def require_image_cache_service() -> ImageCacheService:
    service = get_image_cache_service()
    if service is None:
        raise RuntimeError('图片缓存服务未初始化，请检查应用配置')
    return service


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


def get_google_books_client() -> GoogleBooksClient | None:
    book_service = get_book_service()
    if book_service and hasattr(book_service, '_google_client'):
        return book_service._google_client
    return None
