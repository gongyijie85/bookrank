"""获奖书籍封面自动同步服务（批编排；单书策略在 cover_resolver.CoverResolver）"""

import logging
import time

from ..models.schemas import AwardBook, db
from ..utils.error_handler import ErrorCategory, log_error
from .api_utils import ImageCacheService
from .cover_resolver import CoverResolver
from .google_books_client import GoogleBooksClient
from .open_library_client import OpenLibraryClient

logger = logging.getLogger(__name__)


class AwardCoverSyncService:
    """获奖书籍封面同步服务：候选筛选、批循环、统计与防重入。"""

    def __init__(
        self,
        google_client: GoogleBooksClient | None,
        openlibrary_client: OpenLibraryClient | None = None,
        image_cache: ImageCacheService | None = None,
    ):
        self._openlibrary_client = openlibrary_client or OpenLibraryClient()
        self._image_cache = image_cache
        self._resolver = CoverResolver(google_client, self._openlibrary_client, image_cache)
        self._is_running = False

    def sync_missing_covers(self, batch_size: int = 10, delay: float = 1.5) -> dict:
        """
        同步缺失的获奖书籍封面

        Args:
            batch_size: 每批处理的数量
            delay: 每本书之间的延迟（秒）

        Returns:
            同步结果统计
        """
        if self._is_running:
            logger.warning('封面同步已在运行中，跳过')
            return {'status': 'already_running'}

        self._is_running = True
        result: dict[str, str | int | list[str]] = {
            'total_checked': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
        }

        try:
            # 查找缺失封面的书籍：
            # 1) cover_original_url 为空
            # 2) cover_local_path 为空/默认封面
            # 3) cover_local_path 指向的本地缓存文件已丢失（生产环境临时文件系统重启后）
            # 第 3 种情况无法用 SQL 判断（依赖文件系统），故先拉取全部展示书再逐个验证文件存在性。
            books_candidates = (
                AwardBook.query.filter(
                    AwardBook.isbn13.isnot(None),
                    AwardBook.is_displayable.is_(True),
                )
                .order_by(AwardBook.id)
                .all()
            )

            books_to_update: list[AwardBook] = []
            for b in books_candidates:
                local_path = (b.cover_local_path or '').strip()
                # 本地缓存文件仍可用时无需同步（code review #160 修正：旧过滤器
                # 对「URL 空 + 本地文件在」的书仍会回源；统一为"有可用本地封面
                # 即跳过"，避免循环内 resolve 本地短路造成虚计 updated）
                if not self._resolver.cached_path_available(local_path):
                    books_to_update.append(b)
                    if len(books_to_update) >= batch_size:
                        break

            if not books_to_update:
                logger.info('所有获奖书籍都已包含封面信息')
                result['status'] = 'complete'
                return result

            logger.info(f'开始同步 {len(books_to_update)} 本书籍的封面信息')

            for i, book in enumerate(books_to_update, 1):
                try:
                    result['total_checked'] += 1
                    resolved = self._resolver.resolve(book, persist=True)
                    if resolved:
                        result['updated'] += 1
                        logger.info(f'[{i}/{len(books_to_update)}] ✅ {book.title}: 封面已更新')
                    else:
                        result['skipped'] += 1
                        logger.info(f'[{i}/{len(books_to_update)}] ⚠️ {book.title}: 未找到封面')

                    # 避免API限流
                    if i < len(books_to_update):
                        time.sleep(delay)

                except Exception as e:
                    result['failed'] += 1
                    error_msg = f'{book.title}: {e!s}'
                    result['errors'].append(error_msg)
                    log_error(ErrorCategory.API_CALL, f'[{i}/{len(books_to_update)}] {book.title}: {e}')

            result['status'] = 'success'
            logger.info(f'封面同步完成: 更新{result["updated"]}本, 跳过{result["skipped"]}本, 失败{result["failed"]}本')

        except Exception as e:
            result['status'] = 'error'
            result['errors'].append(str(e))
            log_error(ErrorCategory.API_CALL, f'封面同步出错: {e}')
            db.session.rollback()

        finally:
            self._is_running = False

        return result

    def get_sync_status(self) -> dict:
        """获取同步状态"""
        total: int = AwardBook.query.filter(AwardBook.is_displayable).count()
        has_cover: int = AwardBook.query.filter(
            AwardBook.cover_original_url.isnot(None), AwardBook.cover_original_url != '', AwardBook.is_displayable
        ).count()
        missing = total - has_cover

        return {
            'total_books': total,
            'has_cover': has_cover,
            'missing_cover': missing,
            'coverage_percent': round(has_cover / total * 100, 1) if total > 0 else 0,
            'is_syncing': self._is_running,
        }
