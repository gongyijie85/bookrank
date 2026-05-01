from typing import Optional

from flask import current_app

from ..services import BookService, CacheService, ImageCacheService


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
