from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import current_app

from ..services import BookService, CacheService, ImageCacheService

_background_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='bookrank-bg')


def submit_background_task(fn, *args, **kwargs):
    """提交后台任务到线程池（替代裸 daemon 线程）"""
    return _background_executor.submit(fn, *args, **kwargs)


def get_book_service() -> Optional[BookService]:
    return current_app.extensions.get('book_service')


def get_cache_service() -> Optional[CacheService]:
    return current_app.extensions.get('cache_service')


def get_image_cache_service() -> Optional[ImageCacheService]:
    return current_app.extensions.get('image_cache_service')


def require_book_service() -> BookService:
    service = get_book_service()
    if service is None:
        raise RuntimeError("图书服务未初始化，请检查应用配置")
    return service


@contextmanager
def db_transaction():
    """统一数据库事务管理：自动 commit/rollback，异常时回滚并记录日志"""
    from ..models.database import db
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"数据库事务失败，已回滚: {e}")
        raise


def get_google_books_client():
    """获取 Google Books API 客户端"""
    book_service = get_book_service()
    if book_service and hasattr(book_service, '_google_client'):
        return book_service._google_client
    return None
