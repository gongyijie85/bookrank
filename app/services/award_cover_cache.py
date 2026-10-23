"""获奖封面的轻量路径缓存；请求线程不解析或下载远端图片。"""

from pathlib import Path
from typing import cast

from flask import current_app
from sqlalchemy.orm import load_only
from werkzeug.exceptions import NotFound

from ..models.schemas import AwardBook, db
from ..utils.cover_urls import cached_filename_from_path
from .api_utils import MIN_IMAGE_BYTES
from .book_detail_cache import get_detail_cache
from .detail_cache_invalidation import has_uncommitted_cache_writes


def _missing_local_cover(cover_url: str | None) -> bool:
    if not cover_url or not cover_url.startswith('/cache/images/'):
        return True
    filename = cached_filename_from_path(cover_url)
    if not filename:
        return True
    cache_dir = Path(current_app.config.get('IMAGE_CACHE_DIR', Path('cache/images')))
    if not cache_dir.is_absolute():
        cache_dir = Path(current_app.root_path) / cache_dir
    try:
        return (cache_dir / filename).stat().st_size < MIN_IMAGE_BYTES
    except OSError:
        return True


def cached_award_cover(book_id: int) -> str | None:
    """只缓存已存在的本地路径，缺图交由路由排队异步补全。"""
    cache = get_detail_cache()
    key = ('award-cover', book_id)
    shareable = not has_uncommitted_cache_writes()

    def load() -> str | None:
        with db.session.no_autoflush:
            book = db.session.execute(
                db.select(AwardBook)
                .options(load_only(AwardBook.id, AwardBook.cover_local_path))
                .where(AwardBook.id == book_id)
            ).scalar_one_or_none()
        if book is None:
            raise NotFound()
        cover_url = (book.cover_local_path or '').strip()
        return None if _missing_local_cover(cover_url) else cover_url

    if not shareable:
        return load()
    cover_url = cast('str | None', cache.get_or_load(key, load))
    if cover_url and _missing_local_cover(cover_url):
        cache.invalidate_value(key, cover_url, should_invalidate=lambda: _missing_local_cover(cover_url))
        cover_url = cast('str | None', cache.get_or_load(key, load))
    return cover_url
