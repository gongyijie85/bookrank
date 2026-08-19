import gc
import json
import logging
import os
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app

from ...models.database import db
from ...models.new_book import NewBook, Publisher
from ...utils.error_handler import ErrorCategory, log_error
from .. import publisher_data as pd
from ..publisher_crawler import get_crawler_class
from ..publisher_crawler.base_crawler import BaseCrawler, BookInfo, CrawlerConfig, CrawlRequest
from ..publisher_crawler.google_books import GoogleBooksCrawler
from .ingestor import NewBookIngestor, SaveOutcome
from .publisher_manager import PublisherManager
from .translation_pipeline import TranslationPipeline

logger = logging.getLogger(__name__)

# 单家出版社同步硬超时（秒）：超过即熔断、标记失败并继续下一家，
# 避免单家挂起拖死整批同步（宁可漏报不误报）。
_PER_PUBLISHER_TIMEOUT = float(os.environ.get('SYNC_PUBLISHER_TIMEOUT', '600'))

# 首次回填模式的入库上限：防止异常数据导致无界入库。
# 注意：默认 translate=True 时翻译开销大，受单家 600s 熔断约束，
# 一次同步不一定全部入库。回填窗口已收窄到 30 天（维护者决议的"新书"标准，
# 2026-08-07），窗口内记录数有限，正常情况一轮即可入完。
_BACKFILL_MAX_BOOKS = int(os.environ.get('SYNC_BACKFILL_MAX_BOOKS', '2000'))


@dataclass
class IngestStats:
    """一次入库流的统计；total 为尝试计数（含保存失败的尝试）。"""

    total: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0

    def merge_into(self, result: dict[str, Any]) -> None:
        """把本统计累加进调用方的结果字典（两路共用的合并动作）。"""
        for key in ('total', 'added', 'updated', 'skipped', 'errors'):
            result[key] = result.get(key, 0) + getattr(self, key)


class SyncEngine:
    def __init__(self, publisher_manager: PublisherManager, translation_pipeline: TranslationPipeline) -> None:
        self._publisher_manager = publisher_manager
        self._translation_pipeline = translation_pipeline
        # 入库规则集中到深模块 NewBookIngestor，SyncEngine 只管同步编排。
        self._ingestor = NewBookIngestor(self._translation_pipeline)

    def _ingest_book_stream(
        self,
        book_infos: Iterable[BookInfo],
        publisher: Publisher,
        *,
        translate: bool,
        touched_books: list[NewBook],
        commit_interval: int | None = None,
        on_error: Callable[[Exception, BookInfo], None] | None = None,
    ) -> IngestStats:
        """对 BookInfo 流做保存/计数/错误隔离/可选批量提交（爬虫流与静态流共用）。

        total 统一为尝试计数（含保存失败的尝试，errors 同步 +1）。
        """
        stats = IngestStats()

        # 批级预载：一次查询构建该社存量书索引，消除每本书最多 3 次的
        # 逐本去重往返（性能评审 N+1：回填 2000 本 ≈ 6000 次 → 1 次预载）
        with self._ingestor.preloaded_lookup(publisher):
            for book_info in book_infos:
                stats.total += 1

                try:
                    save_outcome = self._ingestor.save_book(
                        publisher,
                        book_info,
                        translate,
                        auto_commit=False,
                        touched_books=touched_books,
                    )

                    if save_outcome is SaveOutcome.ADDED:
                        stats.added += 1
                    elif save_outcome is SaveOutcome.UPDATED:
                        stats.updated += 1
                    else:
                        stats.skipped += 1

                except Exception as e:
                    if on_error:
                        on_error(e, book_info)
                    else:
                        log_error(ErrorCategory.DB_QUERY, '保存书籍失败: ' + book_info.title + ' - ' + str(e))
                    stats.errors += 1

                if commit_interval is not None and stats.total % commit_interval == 0:
                    db.session.commit()

        return stats

    def sync_publisher_books(
        self,
        publisher_id: int,
        category: str | None = None,
        max_books: int = 50,
        translate: bool = True,
    ) -> dict[str, Any]:
        publisher = self._publisher_manager.get_publisher(publisher_id)
        if not publisher:
            return {'success': False, 'error': '出版社不存在'}

        if not publisher.is_active:
            return {'success': False, 'error': '出版社已禁用'}

        crawler = self.get_crawler(publisher.crawler_class)
        if not crawler:
            return {'success': False, 'error': '爬虫不可用'}

        # #137 fallback_google_enabled 开关接线：Google 系爬虫的同步受开关控制。
        # 跳过不算失败（运维有意关闭），否则 auto_sync 的 24h 节流会被
        # failed_results 判定卡住不更新 last_auto_sync_time，导致每轮 cron 重跑。
        if isinstance(crawler, GoogleBooksCrawler) and not publisher.fallback_google_enabled:
            logger.info(
                '⏭️ %s 的 Google 兜底已关闭（fallback_google_enabled=false），跳过同步',
                publisher.name_en,
            )
            return {
                'success': True,
                'status': 'skipped',
                'publisher': publisher.name_en,
                'reason': 'fallback_google_enabled=false，Google 兜底同步已关闭',
                'total': 0,
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': 0,
            }

        # 窗口模式判定（工单 #87）：支持回填的爬虫按该出版社存量书数量选择，
        # 无存量书走首次回填窗口（爬虫自定窗口天数），此后自动回落增量；爬虫保持无状态
        supports_backfill = crawler.SUPPORTS_BACKFILL is True
        backfill = False
        if supports_backfill:
            existing_count = NewBook.query.filter_by(publisher_id=publisher.id).count()
            backfill = existing_count == 0
            if backfill:
                logger.info('📦 %s 无存量书，启用首次回填窗口', publisher.name_en)

        result: dict[str, Any] = {
            'success': True,
            'status': 'running',
            'transport_status': 'not_started',
            'parse_status': 'not_started',
            'publisher': publisher.name_en,
            'total': 0,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }

        batch_commit_interval = 10
        touched_books: list[NewBook] = []

        try:
            logger.info(f'开始同步 {publisher.name_en} 新书...')

            with crawler:
                # 回填模式放大入库上限，否则拉全量也只能入 30~50 本，
                # 「首次同步一次性补齐」形同虚设（工单 #87）
                effective_max_books = max(max_books, _BACKFILL_MAX_BOOKS) if backfill else max_books
                request = CrawlRequest(
                    category=category,
                    max_books=effective_max_books,
                    backfill=backfill,
                )
                outcome = crawler.get_new_books(request)

                ingest_stats = self._ingest_book_stream(
                    outcome.books,
                    publisher,
                    translate=translate,
                    touched_books=touched_books,
                    commit_interval=batch_commit_interval,
                )
                ingest_stats.merge_into(result)

            result['transport_status'] = 'success'

            # 工单 #83：Google Books 系日期过滤的分类拒绝计数随抓取结果流出，
            # 供 auto_sync 摘要持久化（只测量，不改变行为）。非 Google 系
            # 适配器返回 None（基类声明的接口事实），无需 isinstance 防御。
            if outcome.date_filter_stats:
                result.update(outcome.date_filter_stats)

            if result['total'] == 0:
                # 空结果可能表示“确实没有新书”，也可能表示数据源已经失效；
                # 在没有额外探针确认前，不能把它记录为一次成功同步。
                result['status'] = 'empty'
                result['parse_status'] = 'empty'
                result['success'] = False
                result['error'] = '爬虫返回空结果，未确认数据源有效'
                db.session.rollback()
                return result

            result['parse_status'] = 'partial' if result['errors'] else 'success'
            if result['errors']:
                # 已保存的有效记录可以保留，但本轮不能更新出版社的“最后成功同步”时间。
                result['status'] = 'partial_failure'
                result['success'] = False
                result['error'] = f'部分书籍保存失败，共 {result["errors"]} 条'
            else:
                result['status'] = 'success'

            result['language_pack'] = self._translation_pipeline.persist_language_pack(
                touched_books, translate=translate
            )

            if result['success']:
                publisher.last_sync_at = datetime.now(UTC)
                publisher.sync_count += 1
            db.session.commit()

            logger.info(
                f'同步完成: {publisher.name_en} - '
                f'总计 {result["total"]}, 新增 {result["added"]}, '
                f'更新 {result["updated"]}, 跳过 {result["skipped"]}'
            )

        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'同步失败: {e}')
            db.session.rollback()
            result['success'] = False
            result['status'] = 'request_failed'
            result['transport_status'] = 'failed'
            result['parse_status'] = 'failed'
            result['error'] = str(e)

        return result

    def sync_all_publishers(
        self,
        category: str | None = None,
        max_books_per_publisher: int = 30,
        translate: bool = True,
        batch_size: int = 1,
    ) -> list[dict[str, Any]]:
        results = []
        publishers = self._publisher_manager.get_publishers(active_only=True)

        logger.info(f'开始同步 {len(publishers)} 个出版社...')
        logger.info(f'批处理大小: {batch_size}')

        run_start = time.monotonic()

        for i in range(0, len(publishers), batch_size):
            batch = publishers[i : i + batch_size]
            logger.info(f'处理批次 {i // batch_size + 1}/{(len(publishers) + batch_size - 1) // batch_size}')

            for publisher in batch:
                started = time.monotonic()
                logger.info(f'⏱️ 开始同步出版社: {publisher.name_en}')
                result = self._sync_publisher_with_timeout(
                    publisher, category=category, max_books=max_books_per_publisher, translate=translate
                )
                result['elapsed_seconds'] = round(time.monotonic() - started, 1)
                logger.info(
                    f'⏱️ 出版社同步结束: {publisher.name_en} - '
                    f'status={result.get("status")}, 耗时 {result["elapsed_seconds"]}s'
                )
                results.append(result)

                gc.collect()

        total_added = sum(r.get('added', 0) for r in results)
        total_updated = sum(r.get('updated', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)

        logger.info(
            f'全部同步完成: 新增 {total_added}, 更新 {total_updated}, 错误 {total_errors}, '
            f'总耗时 {time.monotonic() - run_start:.0f}s'
        )

        return results

    def _sync_publisher_with_timeout(
        self,
        publisher: Publisher,
        category: str | None,
        max_books: int,
        translate: bool,
    ) -> dict[str, Any]:
        """在独立线程中同步单家出版社，超时即熔断。

        超时后工作线程无法强制终止，但它使用独立的 scoped session，
        不会阻塞主流程继续同步下一家；其残留请求最终会因各自的
        请求级超时而自行终结。
        """
        app_obj = current_app._get_current_object()

        def _worker() -> dict[str, Any]:
            with app_obj.app_context():
                return self.sync_publisher_books(
                    publisher.id, category=category, max_books=max_books, translate=translate
                )

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f'sync-{publisher.id}')
        future = executor.submit(_worker)
        try:
            return future.result(timeout=_PER_PUBLISHER_TIMEOUT)
        except FutureTimeout:
            logger.error(
                f'⏱️ 出版社同步超时熔断: {publisher.name_en} (超过 {_PER_PUBLISHER_TIMEOUT:.0f}s，标记失败并继续下一家)'
            )
            return {
                'success': False,
                'status': 'timeout',
                'transport_status': 'timeout',
                'parse_status': 'not_started',
                'publisher': publisher.name_en,
                'total': 0,
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': 0,
                'error': f'同步超时（>{_PER_PUBLISHER_TIMEOUT:.0f}s），已熔断跳过',
            }
        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'出版社同步线程异常: {publisher.name_en} - {e}')
            return {
                'success': False,
                'status': 'request_failed',
                'transport_status': 'failed',
                'parse_status': 'failed',
                'publisher': publisher.name_en,
                'total': 0,
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': 0,
                'error': str(e),
            }
        finally:
            # wait=False：超时后不阻塞等待残留工作线程（它无法被强制终止）；
            # 不能用 with 语句，那会在退出时 shutdown(wait=True) 导致熔断失效。
            executor.shutdown(wait=False, cancel_futures=True)

    def seed_from_static_data(self, static_data_dir: str | Path | None = None) -> dict[str, Any]:
        self._publisher_manager.init_publishers()

        data_dir = pd.resolve_static_data_dir(static_data_dir)
        result: dict[str, Any] = {
            'success': True,
            'files_seen': 0,
            'total': 0,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }

        for filename, publisher_name in self._publisher_manager.STATIC_DATA_FILES.items():
            path = data_dir / filename
            if not path.exists():
                continue

            publisher = Publisher.query.filter_by(name_en=publisher_name).first()
            if not publisher:
                logger.warning('静态新书导入跳过，出版社不存在: %s', publisher_name)
                continue

            result['files_seen'] += 1
            try:
                rows = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning('静态新书文件读取失败 %s: %s', path, e)
                result['errors'] += 1
                continue

            if not isinstance(rows, list):
                logger.warning('静态新书文件格式无效: %s', path)
                result['errors'] += 1
                continue

            touched_books: list[NewBook] = []

            def _static_error_log(e: Exception, book_info: BookInfo) -> None:
                log_error(ErrorCategory.CRAWLER, f'静态新书导入失败: {book_info.title} - {e}', level='warning')

            ingest_stats = self._ingest_book_stream(
                self._iter_static_book_infos(rows, result),
                publisher,
                translate=False,
                touched_books=touched_books,
                on_error=_static_error_log,
            )
            ingest_stats.merge_into(result)

            try:
                self._translation_pipeline.persist_language_pack(touched_books, translate=False)
                publisher.last_sync_at = datetime.now(UTC)
                if touched_books:
                    publisher.sync_count = (publisher.sync_count or 0) + 1
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                log_error(ErrorCategory.DB_QUERY, f'静态新书批量提交失败 {filename}: {e}', level='warning')
                result['errors'] += 1

        logger.info(
            '静态新书兜底导入完成: 文件%s个, 新增%s本, 更新%s本, 跳过%s本, 错误%s',
            result['files_seen'],
            result['added'],
            result['updated'],
            result['skipped'],
            result['errors'],
        )
        return result

    def ensure_static_data_seeded(self) -> dict[str, Any] | None:
        existing_books = NewBook.query.filter(NewBook.is_displayable.is_(True)).count()
        if existing_books > 0:
            return None
        return self.seed_from_static_data()

    def get_crawler(self, crawler_class: str) -> BaseCrawler | None:
        crawler_cls = get_crawler_class(crawler_class)
        if not crawler_cls:
            logger.error(f'未找到爬虫类: {crawler_class}')
            return None

        # 配置注入统一走基类声明的接口事实（API_KEY_CONFIG / api_key_required /
        # REQUEST_DELAY），不再按类名字符串分支。
        api_key_config = crawler_cls.API_KEY_CONFIG
        api_key = current_app.config.get(api_key_config) if (api_key_config and current_app) else None

        if api_key_config and not api_key and crawler_cls.api_key_required:
            # 必填 key 的适配器（如 PRH 官方 API）：缺 key 快速失败
            # （返回 None → 该出版社标记失败），不阻塞其余出版社同步（工单 #86）
            log_error(ErrorCategory.CRAWLER, f'{api_key_config} 未配置，跳过 {crawler_class}', level='error')
            return None

        config_kwargs: dict[str, Any] = {}
        if api_key:
            config_kwargs['api_key'] = api_key
        if crawler_cls.REQUEST_DELAY is not None:
            config_kwargs['request_delay'] = crawler_cls.REQUEST_DELAY
        config = CrawlerConfig(**config_kwargs) if config_kwargs else None
        return crawler_cls(config)

    def _iter_static_book_infos(self, rows: list, result: dict[str, Any]) -> Iterator[BookInfo]:
        """静态数据行 → BookInfo 流：非法行计入 skipped，构造异常计入 errors。"""
        for row in rows:
            if not isinstance(row, dict):
                result['skipped'] += 1
                continue

            title = (row.get('title') or '').strip()
            author = (row.get('author') or '').strip()
            if not title or not author:
                result['skipped'] += 1
                continue

            try:
                yield BookInfo(
                    title=title,
                    author=author,
                    isbn13=pd.normalize_isbn(row.get('isbn13'), 13),
                    isbn10=pd.normalize_isbn(row.get('isbn10'), 10),
                    description=row.get('description'),
                    cover_url=row.get('cover_url'),
                    category=row.get('category'),
                    publication_date=pd.parse_static_date(row.get('publication_date')),
                    price=row.get('price'),
                    page_count=pd.parse_int_safe(row.get('page_count')),
                    language=row.get('language'),
                    buy_links=row.get('buy_links') if isinstance(row.get('buy_links'), list) else [],  # type: ignore[arg-type]
                    source_url=row.get('source_url'),
                )
            except Exception as e:
                log_error(ErrorCategory.CRAWLER, f'静态新书导入失败: {title} - {e}', level='warning')
                result['errors'] += 1
