"""封面解析（cover resolution）：获奖书籍封面获取的单一策略入口。

候选 #6：resolve_cover_for_book 与 sync_missing_covers 两条路径的
fetch→cache→persist 链收敛到本模块；批编排（清单/延迟/统计/防重入）
留在 AwardCoverSyncService。
"""

import logging

from ..models.schemas import AwardBook, db
from ..utils.error_handler import ErrorCategory, log_error
from .api_client import GoogleBooksClient, ImageCacheService, OpenLibraryClient

logger = logging.getLogger(__name__)


class CoverResolver:
    """单一封面解析策略：本地文件 → 原 URL 缓存 → 按需回源 → 缓存 → 持久化。"""

    def __init__(
        self,
        google_client: GoogleBooksClient | None,
        openlibrary_client: OpenLibraryClient,
        image_cache: ImageCacheService | None,
    ) -> None:
        self._google_client = google_client
        self._openlibrary_client = openlibrary_client
        self._image_cache = image_cache

    def resolve(self, book: AwardBook, persist: bool = True) -> str | None:
        """解析单本获奖书籍的最佳封面 URL，并尽量回写缓存结果。"""
        local_path = (book.cover_local_path or '').strip()
        if self.cached_path_available(local_path):
            return local_path

        cover_url = (book.cover_original_url or '').strip()
        if cover_url:
            cached_cover = self._cache_cover(cover_url)
            if cached_cover:
                if persist and cached_cover != book.cover_local_path:
                    book.cover_local_path = cached_cover
                    db.session.commit()
                return cached_cover

            if not self._should_refresh_cover_source(cover_url):
                return cover_url

        fetched_cover = self._fetch_cover_for_book(book)
        if not fetched_cover:
            return cover_url or None

        cached_cover = self._cache_cover(fetched_cover)
        if persist:
            book.cover_original_url = fetched_cover
            book.cover_local_path = cached_cover
            db.session.commit()

        return cached_cover or fetched_cover

    def cached_path_available(self, local_path: str) -> bool:
        """本地封面文件是否仍可用；探测逻辑全量委托给缓存模块。"""
        if not self._image_cache:
            return True
        return self._image_cache.is_cached_file_present(local_path)

    def _fetch_cover_for_book(self, book: AwardBook) -> str | None:
        """为单本书籍获取封面 URL（OL ISBN → OL 书名 → Google ISBN → Google 书名）。"""
        isbn = book.isbn13
        title = book.title
        author = book.author

        # 方法1：Open Library（通过ISBN查询，无需 API Key）
        if isbn:
            try:
                ol_cover = self._openlibrary_client.get_cover_url(isbn, size='L')
                if ol_cover:
                    return ol_cover
            except Exception as e:
                log_error(ErrorCategory.API_CALL, f'Open Library ISBN查询失败 ({isbn}): {e}', level='warning')

        # 方法2：Open Library（通过书名+作者搜索 cover_id）
        if title:
            try:
                ol_cover = self._openlibrary_client.get_cover_url_by_title(title, author, size='L')
                if ol_cover:
                    logger.info(f'通过Open Library书名搜索找到封面: {title}')
                    return ol_cover
            except Exception as e:
                log_error(ErrorCategory.API_CALL, f'Open Library书名搜索失败 ({title}): {e}', level='warning')

        if not self._google_client:
            return None

        # 方法3：Google Books API（通过ISBN查询）
        if isbn:
            try:
                result = self._google_client.fetch_book_details(isbn)
                if result and result.get('cover_url'):
                    return result['cover_url']  # type: ignore[no-any-return]
            except Exception as e:
                log_error(ErrorCategory.API_CALL, f'Google Books ISBN查询失败 ({isbn}): {e}', level='warning')

        # 方法4：Google Books API（通过书名+作者搜索）- 备选方案
        if title and author:
            try:
                result = self._google_client.search_book_by_title(title, author)
                if result and result.get('cover_url'):
                    logger.info(f'通过书名搜索找到封面: {title}')
                    return result['cover_url']  # type: ignore[no-any-return]
            except Exception as e:
                log_error(ErrorCategory.API_CALL, f'Google Books书名搜索失败 ({title}): {e}', level='warning')

        return None

    @staticmethod
    def _should_refresh_cover_source(cover_url: str) -> bool:
        """Open Library ISBN URLs may 404; refresh them when cache validation fails."""
        return 'covers.openlibrary.org' in cover_url

    def _cache_cover(self, cover_url: str) -> str | None:
        """下载封面到本地缓存，失败时保留原始 URL 作为前端兜底。"""
        if not self._image_cache:
            return None

        try:
            cached_path = self._image_cache.get_cached_image_url(cover_url, ttl=86400 * 365)
            if cached_path and cached_path != '/static/default-cover.png':
                return cached_path
        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'封面缓存失败 ({cover_url}): {e}', level='warning')

        return None
