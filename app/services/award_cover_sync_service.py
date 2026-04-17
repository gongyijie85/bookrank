"""获奖书籍封面自动同步服务"""
import time
import logging
from typing import Optional

from ..models.schemas import AwardBook, db
from .api_client import GoogleBooksClient, OpenLibraryClient

logger = logging.getLogger(__name__)


class AwardCoverSyncService:
    """获奖书籍封面同步服务"""

    def __init__(self, google_client: GoogleBooksClient, openlibrary_client: Optional[OpenLibraryClient] = None):
        self._google_client = google_client
        self._openlibrary_client = openlibrary_client or OpenLibraryClient()
        self._is_running = False

    def sync_missing_covers(self, batch_size: int = 10, delay: float = 0.5) -> dict:
        """
        同步缺失的获奖书籍封面

        Args:
            batch_size: 每批处理的数量
            delay: 每本书之间的延迟（秒）

        Returns:
            同步结果统计
        """
        if self._is_running:
            logger.warning("封面同步已在运行中，跳过")
            return {'status': 'already_running'}

        self._is_running = True
        result = {
            'total_checked': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }

        try:
            # 查找缺少封面的书籍
            books_to_update = AwardBook.query.filter(
                (AwardBook.cover_original_url == None) | (AwardBook.cover_original_url == ''),
                AwardBook.isbn13 != None,
                AwardBook.is_displayable == True
            ).limit(batch_size).all()

            if not books_to_update:
                logger.info("所有获奖书籍都已包含封面信息")
                result['status'] = 'complete'
                return result

            logger.info(f"开始同步 {len(books_to_update)} 本书籍的封面信息")

            for i, book in enumerate(books_to_update, 1):
                try:
                    result['total_checked'] += 1
                    cover_url = self._fetch_cover_for_book(book)

                    if cover_url:
                        book.cover_original_url = cover_url
                        db.session.commit()
                        result['updated'] += 1
                        logger.info(f"[{i}/{len(books_to_update)}] ✅ {book.title}: 封面已更新")
                    else:
                        result['skipped'] += 1
                        logger.info(f"[{i}/{len(books_to_update)}] ⚠️ {book.title}: 未找到封面")

                    # 避免API限流
                    if i < len(books_to_update):
                        time.sleep(delay)

                except Exception as e:
                    result['failed'] += 1
                    error_msg = f"{book.title}: {str(e)}"
                    result['errors'].append(error_msg)
                    logger.error(f"[{i}/{len(books_to_update)}] ❌ {book.title}: {e}")

            result['status'] = 'success'
            logger.info(f"封面同步完成: 更新{result['updated']}本, 跳过{result['skipped']}本, 失败{result['failed']}本")

        except Exception as e:
            result['status'] = 'error'
            result['errors'].append(str(e))
            logger.error(f"封面同步出错: {e}")
            db.session.rollback()

        finally:
            self._is_running = False

        return result

    def _fetch_cover_for_book(self, book: AwardBook) -> Optional[str]:
        """
        为单本书籍获取封面URL

        Args:
            book: 书籍对象

        Returns:
            封面URL或None
        """
        isbn = book.isbn13
        title = book.title
        author = book.author

        # 方法1：Google Books API（通过ISBN查询）
        if isbn:
            try:
                result = self._google_client.fetch_book_details(isbn)
                if result and result.get('cover_url'):
                    return result['cover_url']
            except Exception as e:
                logger.debug(f"Google Books ISBN查询失败 ({isbn}): {e}")

        # 方法2：Open Library（通过ISBN查询）
        if isbn:
            try:
                ol_cover = self._openlibrary_client.get_cover_url(isbn, size='L')
                if ol_cover:
                    return ol_cover
            except Exception as e:
                logger.debug(f"Open Library查询失败 ({isbn}): {e}")

        # 方法3：Google Books API（通过书名+作者搜索）- 备选方案
        if title and author:
            try:
                result = self._google_client.search_book_by_title(title, author)
                if result and result.get('cover_url'):
                    logger.info(f"通过书名搜索找到封面: {title}")
                    return result['cover_url']
            except Exception as e:
                logger.debug(f"Google Books书名搜索失败 ({title}): {e}")

        return None

    def get_sync_status(self) -> dict:
        """获取同步状态"""
        total = AwardBook.query.filter(AwardBook.is_displayable == True).count()
        has_cover = AwardBook.query.filter(
            AwardBook.cover_original_url != None,
            AwardBook.cover_original_url != '',
            AwardBook.is_displayable == True
        ).count()
        missing = total - has_cover

        return {
            'total_books': total,
            'has_cover': has_cover,
            'missing_cover': missing,
            'coverage_percent': round(has_cover / total * 100, 1) if total > 0 else 0,
            'is_syncing': self._is_running
        }
