import gc
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from flask import current_app

from ...models.database import db
from ...models.new_book import NewBook, Publisher
from ...utils.error_handler import ErrorCategory, log_error
from .. import publisher_data as pd
from ..publisher_crawler import get_crawler_class
from ..publisher_crawler.base_crawler import BaseCrawler, BookInfo, CrawlerConfig
from .publisher_manager import PublisherManager
from .translation_pipeline import TranslationPipeline

logger = logging.getLogger(__name__)

# 单家出版社同步硬超时（秒）：超过即熔断、标记失败并继续下一家，
# 避免单家挂起拖死整批同步（宁可漏报不误报）。
_PER_PUBLISHER_TIMEOUT = float(os.environ.get('SYNC_PUBLISHER_TIMEOUT', '600'))

# 首次回填模式的入库上限：防止异常数据导致无界入库。
# 注意：默认 translate=True 时翻译开销大，受单家 600s 熔断约束，
# 一次同步不一定全部入库；未入完部分的补齐策略由生产验证（工单 #88）定夺。
_BACKFILL_MAX_BOOKS = int(os.environ.get('SYNC_BACKFILL_MAX_BOOKS', '2000'))


class SyncEngine:
    _GOOGLE_BOOKS_CRAWLERS: set[str] = {
        'GoogleBooksCrawler',
        'SimonSchusterGoogleCrawler',
        'HachetteGoogleCrawler',
        'HarperCollinsGoogleCrawler',
        'MacmillanGoogleCrawler',
        'MacmillanCrawler',
        'PenguinRandomHouseCrawler',
    }

    def __init__(self, publisher_manager: PublisherManager, translation_pipeline: TranslationPipeline) -> None:
        self._publisher_manager = publisher_manager
        self._translation_pipeline = translation_pipeline

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

        # 窗口模式判定（工单 #87）：支持回填的爬虫按该出版社存量书数量选择，
        # 无存量书走首次 180 天全量回填，此后自动回落 14 天增量；爬虫保持无状态
        supports_backfill = getattr(crawler, 'SUPPORTS_BACKFILL', False) is True
        backfill = False
        if supports_backfill:
            existing_count = NewBook.query.filter_by(publisher_id=publisher.id).count()
            backfill = existing_count == 0
            if backfill:
                logger.info('📦 %s 无存量书，启用近 180 天全量回填窗口', publisher.name_en)

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
                fetch_kwargs: dict[str, Any] = {'category': category, 'max_books': effective_max_books}
                if supports_backfill:
                    fetch_kwargs['backfill'] = backfill
                for book_info in crawler.get_new_books(**fetch_kwargs):
                    result['transport_status'] = 'success'
                    result['total'] += 1

                    try:
                        save_result = self._save_book(
                            publisher,
                            book_info,
                            translate,
                            auto_commit=False,
                            touched_books=touched_books,
                        )

                        if save_result == 'added':
                            result['added'] += 1
                        elif save_result == 'updated':
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1

                    except Exception as e:
                        log_error(ErrorCategory.DB_QUERY, f'保存书籍失败: {book_info.title} - {e}')
                        result['errors'] += 1

                    if result['total'] % batch_commit_interval == 0:
                        db.session.commit()

            result['transport_status'] = 'success'
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

            result['language_pack'] = self._translation_pipeline._translate_and_store_language_pack(
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

    def _save_book(
        self,
        publisher: Publisher,
        book_info: BookInfo,
        translate: bool = True,
        auto_commit: bool = True,
        touched_books: list[NewBook] | None = None,
    ) -> str:
        existing = None

        if book_info.isbn13:
            existing = NewBook.query.filter_by(publisher_id=publisher.id, isbn13=book_info.isbn13).first()

        if not existing and book_info.isbn10:
            existing = NewBook.query.filter_by(publisher_id=publisher.id, isbn10=book_info.isbn10).first()

        if not existing:
            existing = NewBook.query.filter_by(
                publisher_id=publisher.id, title=book_info.title, author=book_info.author
            ).first()

        if existing:
            updated = self._update_book_fields(existing, book_info, auto_commit=auto_commit)
            translated = False
            if translate and self._translation_pipeline._translator:
                translated = self._translation_pipeline._translate_book(existing)
            if touched_books is not None:
                touched_books.append(existing)
            if updated:
                return 'updated'
            if translated:
                if auto_commit:
                    db.session.commit()
                return 'updated'
            return 'skipped'

        new_book = NewBook(
            publisher_id=publisher.id,
            title=book_info.title,
            author=book_info.author,
            isbn13=book_info.isbn13,
            isbn10=book_info.isbn10,
            description=book_info.description,
            cover_url=book_info.cover_url,
            category=self._sanitize_category(book_info.category),
            publication_date=self._coerce_publication_date(book_info.publication_date),
            price=book_info.price,
            page_count=book_info.page_count,
            language=book_info.language,
            source_url=book_info.source_url,
        )

        if book_info.buy_links:
            new_book.set_buy_links(book_info.buy_links)

        if translate and self._translation_pipeline._translator:
            self._translation_pipeline._translate_book(new_book)

        db.session.add(new_book)
        if touched_books is not None:
            touched_books.append(new_book)
        if auto_commit:
            db.session.commit()

        return 'added'

    def _update_book_fields(self, book: NewBook, book_info: BookInfo, auto_commit: bool = True) -> bool:
        updated = False

        if book_info.description and book_info.description != book.description:
            book.description = book_info.description
            book.description_zh = None
            updated = True

        if book_info.cover_url and book_info.cover_url != book.cover_url:
            book.cover_url = book_info.cover_url
            updated = True

        category = self._sanitize_category(getattr(book_info, 'category', None))
        if category and category != book.category:
            book.category = category
            updated = True

        publication_date = self._coerce_publication_date(getattr(book_info, 'publication_date', None))
        if publication_date and publication_date != book.publication_date:
            book.publication_date = publication_date
            updated = True

        if book_info.price and book_info.price != book.price:
            book.price = book_info.price
            updated = True

        page_count = getattr(book_info, 'page_count', None)
        if page_count and page_count != book.page_count:
            book.page_count = page_count
            updated = True

        language = getattr(book_info, 'language', None)
        if language and language != book.language:
            book.language = language
            updated = True

        source_url = getattr(book_info, 'source_url', None)
        if source_url and source_url != book.source_url:
            book.source_url = source_url
            updated = True

        if book_info.buy_links:
            book.set_buy_links(book_info.buy_links)
            updated = True

        if updated:
            book.updated_at = datetime.now(UTC)
            if auto_commit:
                db.session.commit()

        return updated

    def seed_from_static_data(self, static_data_dir: str | Path | None = None) -> dict[str, Any]:
        self._publisher_manager.init_publishers()

        data_dir = self._resolve_static_data_dir(static_data_dir)
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
                    book_info = BookInfo(
                        title=title,
                        author=author,
                        isbn13=self._normalize_isbn(row.get('isbn13'), 13),
                        isbn10=self._normalize_isbn(row.get('isbn10'), 10),
                        description=row.get('description'),
                        cover_url=row.get('cover_url'),
                        category=row.get('category'),
                        publication_date=self._parse_static_date(row.get('publication_date')),
                        price=row.get('price'),
                        page_count=self._parse_int(row.get('page_count')),
                        language=row.get('language'),
                        buy_links=row.get('buy_links') if isinstance(row.get('buy_links'), list) else [],  # type: ignore[arg-type]
                        source_url=row.get('source_url'),
                    )
                    save_result = self._save_book(
                        publisher,
                        book_info,
                        translate=False,
                        auto_commit=False,
                        touched_books=touched_books,
                    )
                    result['total'] += 1
                    if save_result == 'added':
                        result['added'] += 1
                    elif save_result == 'updated':
                        result['updated'] += 1
                    else:
                        result['skipped'] += 1
                except Exception as e:
                    log_error(ErrorCategory.CRAWLER, f'静态新书导入失败: {title} - {e}', level='warning')
                    result['errors'] += 1

            try:
                self._translation_pipeline._translate_and_store_language_pack(touched_books, translate=False)
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

        if crawler_class in self._GOOGLE_BOOKS_CRAWLERS:
            api_key = current_app.config.get('GOOGLE_API_KEY') if current_app else None
            if api_key:
                config = CrawlerConfig(api_key=api_key)
                return crawler_cls(config)

        if crawler_class == 'PrhApiCrawler':
            # PRH 官方 API 爬虫：key 缺失时快速失败（返回 None → 该出版社标记失败），
            # 不阻塞其余出版社同步（工单 #86）
            api_key = current_app.config.get('PRH_API_KEY') if current_app else None
            if not api_key:
                log_error(ErrorCategory.CRAWLER, 'PRH_API_KEY 未配置，跳过 PrhApiCrawler', level='error')
                return None
            return crawler_cls(CrawlerConfig(api_key=api_key, request_delay=0.5))

        return crawler_cls()

    @staticmethod
    def _resolve_static_data_dir(static_data_dir: str | Path | None = None) -> Path:
        return pd.resolve_static_data_dir(static_data_dir)

    @staticmethod
    def _normalize_isbn(value: Any, length: int) -> str | None:
        return pd.normalize_isbn(value, length)

    @staticmethod
    def _parse_static_date(value: Any) -> date | None:
        return pd.parse_static_date(value)

    @staticmethod
    def _coerce_publication_date(value: Any) -> date | None:
        return pd.coerce_publication_date(value)

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        return pd.parse_int_safe(value)

    @staticmethod
    def _sanitize_category(category: str | None) -> str | None:
        return pd.sanitize_category(category)
