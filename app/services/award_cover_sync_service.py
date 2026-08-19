"""获奖书籍封面自动同步服务（批编排；单书策略在 cover_resolver.CoverResolver）"""

import logging
import threading
import time
from typing import Any

from ..models.schemas import AwardBook, db
from ..utils.error_handler import ErrorCategory, log_error
from .api_utils import ImageCacheService
from .cover_resolver import CoverResolver
from .google_books_client import GoogleBooksClient
from .open_library_client import OpenLibraryClient

logger = logging.getLogger(__name__)

# 模块级互斥锁：调用方（定时任务 / admin 手动触发）各自实例化 Service，
# 实例级 _is_running 标志无法跨实例防重入；进程内共享一把锁才能真正互斥。
_sync_mutex = threading.Lock()
# 最近一次批同步结果（供 /award-covers/status 轮询，异步化后不再同步返回）
_last_result: dict[str, Any] | None = None


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

    def sync_missing_covers(self, batch_size: int = 10, delay: float = 1.5) -> dict:
        """
        同步缺失的获奖书籍封面

        Args:
            batch_size: 每批处理的数量
            delay: 每本书之间的延迟（秒）

        Returns:
            同步结果统计
        """
        global _last_result

        if not _sync_mutex.acquire(blocking=False):
            logger.warning('封面同步已在运行中，跳过')
            return {'status': 'already_running'}

        result: dict[str, str | int | list[str]] = {
            'total_checked': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
        }

        try:
            books_to_update = self._collect_missing_cover_books(batch_size)

            if not books_to_update:
                logger.info('所有获奖书籍都已包含封面信息')
                result['status'] = 'complete'
                return result

            logger.info(f'开始同步 {len(books_to_update)} 本书籍的封面信息')

            # 批末统一提交：循环内 resolve(persist=True, auto_commit=False)
            # 只改属性不逐本 commit（性能评审 #9：每本书一次 commit 的
            # 外部 PG 往返在批同步下成倍放大）
            for i, book in enumerate(books_to_update, 1):
                try:
                    result['total_checked'] += 1
                    resolved = self._resolver.resolve(book, persist=True, auto_commit=False)
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

            db.session.commit()
            result['status'] = 'success'
            logger.info(f'封面同步完成: 更新{result["updated"]}本, 跳过{result["skipped"]}本, 失败{result["failed"]}本')

        except Exception as e:
            result['status'] = 'error'
            result['errors'].append(str(e))
            log_error(ErrorCategory.API_CALL, f'封面同步出错: {e}')
            db.session.rollback()

        finally:
            _last_result = dict(result)
            _sync_mutex.release()

        return result

    def _collect_missing_cover_books(self, batch_size: int) -> list[AwardBook]:
        """筛选缺失封面的候选书（性能评审 #4：稳态下避免全表 ORM 实例化）。

        查找规则（与历史语义一致）：
        1) cover_original_url 为空
        2) cover_local_path 为空/默认封面
        3) cover_local_path 指向的本地缓存文件已丢失（生产临时文件系统重启后）
        第 3 种依赖文件系统，无法用 SQL 判断——先用轻量两列查询筛出候选 id，
        再按需加载完整 ORM 对象（稳态下零实例化、零回源）。
        """
        rows = db.session.execute(
            db.select(AwardBook.id, AwardBook.cover_local_path).where(
                AwardBook.isbn13.isnot(None),
                AwardBook.is_displayable.is_(True),
            )
        ).all()

        candidate_ids: list[int] = []
        for book_id, cover_local_path in rows:
            local_path = (cover_local_path or '').strip()
            # 本地缓存文件仍可用时无需同步（code review #160 修正：统一为
            # "有可用本地封面即跳过"；非 cache 目录路径纯字符串判定即返回）
            if not self._resolver.cached_path_available(local_path):
                candidate_ids.append(book_id)
                if len(candidate_ids) >= batch_size:
                    break

        if not candidate_ids:
            return []
        return AwardBook.query.filter(AwardBook.id.in_(candidate_ids)).order_by(AwardBook.id).all()

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
            'is_syncing': _sync_mutex.locked(),
            'last_result': _last_result,
        }
