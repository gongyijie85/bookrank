import logging
import threading
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path
from typing import Any

import requests
from flask import Flask
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from ..models.book import Book
from ..models.schemas import BookMetadata, db
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.exceptions import APIException, APIRateLimitException, ExternalAPIError
from .api_client import GoogleBooksClient, ImageCacheService, NYTApiClient
from .book_language_pack import BookLanguagePack
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class BookService:
    """图书业务服务"""

    def __init__(
        self,
        nyt_client: NYTApiClient,
        google_client: GoogleBooksClient,
        cache_service: CacheService,
        image_cache: ImageCacheService,
        app: Flask | None = None,
        max_workers: int = 4,
        categories: dict | None = None,
        language_pack_path: str | Path | None = None,
    ):
        self._nyt_client = nyt_client
        self._google_client = google_client
        self._cache = cache_service
        self._image_cache = image_cache
        self._app = app
        self._max_workers = max_workers
        self._categories = categories or {}
        self._language_pack = BookLanguagePack(language_pack_path or self._resolve_language_pack_path(app))

        self._translation_lock = threading.Lock()
        self._translation_thread_active = False
        self._on_data_refreshed_callbacks: weakref.WeakSet[Callable[[], None]] = weakref.WeakSet()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='bookrank-fetch')
        self._isbn_index: dict[str, dict[str, Any]] = {}  # ISBN -> book_data 反向索引

    def on_data_refreshed(self, callback: Callable[[], None]) -> None:
        """注册数据刷新后的回调函数"""
        self._on_data_refreshed_callbacks.add(callback)

    def get_cache_time(self, category_id: str) -> str | None:
        """获取指定分类的缓存更新时间（公开方法替代直接访问 _cache）"""
        cache_key = f'books_{category_id}'
        return self._cache.get_cache_time(cache_key)

    @property
    def cache(self) -> object:
        """公开访问缓存服务实例（只读属性替代直接访问私有 _cache）"""
        return self._cache

    @staticmethod
    def _resolve_language_pack_path(app: Flask | None) -> Path | None:
        if not app or not app.static_folder:
            return None
        return Path(app.static_folder) / 'data' / 'book_language_pack.zh.json'

    def _notify_data_refreshed(self) -> None:
        """通知所有注册的回调：数据已刷新"""
        for callback in self._on_data_refreshed_callbacks:
            try:
                callback()
            except Exception as e:
                log_error(ErrorCategory.CACHE, f'数据刷新回调执行失败: {e}', level='warning')

    def get_book_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        """通过ISBN查找图书数据（先查反向索引 O(1)，再回退遍历缓存）"""
        # 1. 反向索引快速路径
        if isbn in self._isbn_index:
            return self._isbn_index[isbn]

        # 2. 遍历缓存并构建索引
        for category_id in self._categories:
            cache_key = f'books_{category_id}'
            cached_data = self._cache.get(cache_key)
            if not cached_data:
                continue
            for book_data in cached_data:
                isbn13 = book_data.get('isbn13')
                isbn10 = book_data.get('isbn10')
                if isbn13:
                    self._isbn_index[isbn13] = book_data
                if isbn10:
                    self._isbn_index[isbn10] = book_data
                if isbn13 == isbn or isbn10 == isbn:
                    return book_data

        metadata = db.session.get(BookMetadata, isbn)
        if metadata:
            return {
                'title': metadata.title or '',
                'author': metadata.author or '',
                'description': metadata.description_zh or metadata.details or '',
                'isbn13': isbn,
            }
        return None

    def _books_from_cache_data(self, cached_data: list[dict[str, Any]] | None, category_id: str) -> list[Book]:
        if not cached_data:
            return []

        books = []
        for book_data in cached_data:
            try:
                books.append(Book(**book_data))
            except TypeError as e:
                logger.warning(f'Invalid cached book for {category_id}: {e}')
        self._hydrate_language_pack(books)
        return books

    def _hydrate_language_pack(self, books: list[Book]) -> None:
        try:
            self._language_pack.hydrate_books(books)
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'Book language-pack hydration skipped: {e}', level='warning')

    def _get_stale_cached_books(self, cache_key: str, category_id: str) -> list[Book]:
        get_stale = getattr(self._cache, 'get_stale', None)
        cached_data = get_stale(cache_key) if callable(get_stale) else None
        if not cached_data:
            cached_data = self._cache.get(cache_key)

        books = self._books_from_cache_data(cached_data, category_id)
        if books:
            logger.warning(f'Returning stale cached books for {category_id}')
        return books

    def get_books_by_category(
        self,
        category_id: str,
        force_refresh: bool = False,
        auto_translate: bool = True,
        notify_refresh: bool = True,
    ) -> list[Book]:
        """
        获取指定分类的图书列表

        Args:
            category_id: 分类ID
            force_refresh: 是否强制刷新缓存
            auto_translate: 是否启动后台预翻译
            notify_refresh: 是否通知数据刷新回调

        Returns:
            图书列表
        """
        cache_key = f'books_{category_id}'

        # 尝试从缓存获取
        if not force_refresh:
            cached_data = self._cache.get(cache_key)
            if cached_data:
                logger.info(f'Returning cached books for {category_id}')
                return self._books_from_cache_data(cached_data, category_id)

        # 从API获取
        try:
            api_data = self._nyt_client.fetch_books(category_id)
            if isinstance(api_data, dict) and api_data.get('error'):
                raise APIException(f'NYT API returned error for {category_id}: {api_data["error"]}')

            books = self._process_api_response(api_data, category_id)
            if not books:
                stale_books = self._get_stale_cached_books(cache_key, category_id)
                if stale_books:
                    return stale_books
                logger.warning(f'NYT API returned no books for {category_id}')
                return []

            # 缓存结果 - 缓存 TTL 从配置读取
            books_data = [book.to_dict() for book in books]
            cache_ttl = self._app.config.get('BOOK_SERVICE_CACHE_TTL', 86400) if self._app else 86400
            self._cache.set(cache_key, books_data, ttl=cache_ttl)

            logger.info(f'Fetched and cached {len(books)} books for {category_id}')

            if auto_translate:
                # 启动后台预翻译（不阻塞响应）
                self._auto_translate_books(books)

            # 通知数据刷新回调
            if notify_refresh:
                self._notify_data_refreshed()

            return books

        except APIRateLimitException:
            # 限流时返回缓存数据（即使已过期）
            stale_books = self._get_stale_cached_books(cache_key, category_id)
            if stale_books:
                return stale_books
            raise
        except APIException as e:
            logger.error(f'Failed to fetch books for {category_id}: {e}')
            # 返回缓存数据作为降级
            stale_books = self._get_stale_cached_books(cache_key, category_id)
            if stale_books:
                return stale_books
            return []

    def _process_api_response(self, api_data: dict[str, Any], category_id: str) -> list[Book]:
        """
        处理API响应数据

        Args:
            api_data: API响应数据
            category_id: 分类ID

        Returns:
            处理后的图书列表
        """
        results = api_data.get('results', {})
        raw_books = results.get('books', [])
        list_name = results.get('list_name', 'Unknown List')
        published_date = results.get('published_date', 'Unknown')

        category_name = self._categories.get(category_id, category_id)

        isbns = [b.get('primary_isbn13') or b.get('primary_isbn10', '') for b in raw_books]
        translations = self._batch_get_translations(isbns)
        supplements = self._batch_get_supplements(isbns)

        processed_books = []
        for book_data in raw_books:
            try:
                book = self._process_single_book(
                    book_data, category_id, category_name, list_name, published_date, translations, supplements
                )
                if book:
                    processed_books.append(book)
            except (KeyError, TypeError, ValueError) as e:
                logger.error(f'Error processing book: {e}')

        processed_books.sort(key=lambda x: x.rank)
        self._hydrate_language_pack(processed_books)
        return processed_books

    def _batch_get_translations(self, isbns: list[str]) -> dict[str, dict]:
        """批量获取翻译数据，避免在子线程中访问数据库"""
        if not isbns:
            return {}
        return self._language_pack.get_book_metadata_translations(isbns)

    def _batch_get_supplements(self, isbns: list[str]) -> dict[str, dict]:
        """并发获取Google Books补充信息，提升批量查询效率"""
        supplements = {}
        if not isbns:
            return supplements

        valid_isbns = [isbn for isbn in isbns if isbn]
        if not valid_isbns:
            return supplements

        try:
            from concurrent.futures import as_completed

            def _fetch_one(isbn: str) -> tuple[str, dict]:
                try:
                    return isbn, self._google_client.fetch_book_details(isbn)
                except (requests.RequestException, requests.Timeout, ValueError, KeyError):
                    return isbn, {}

            futures = {self._executor.submit(_fetch_one, isbn): isbn for isbn in valid_isbns}
            for future in as_completed(futures):
                isbn, result = future.result()
                supplements[isbn] = result
        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'并发获取补充信息失败，降级为串行: {e}', level='warning')
            for isbn in valid_isbns:
                try:
                    supplements[isbn] = self._google_client.fetch_book_details(isbn)
                except (requests.RequestException, requests.Timeout, ValueError, KeyError):
                    supplements[isbn] = {}

        return supplements

    def _process_single_book(
        self,
        book_data: dict[str, Any],
        category_id: str,
        category_name: str,
        list_name: str,
        published_date: str,
        translations: dict[str, dict],
        supplements: dict[str, dict],
    ) -> Book | None:
        """
        处理单本图书数据

        Args:
            book_data: 原始图书数据
            category_id: 分类ID
            category_name: 分类名称
            list_name: 榜单名称
            published_date: 发布日期
            translations: 翻译数据字典
            supplements: 补充信息字典

        Returns:
            处理后的Book对象
        """
        isbn = book_data.get('primary_isbn13') or book_data.get('primary_isbn10', '')

        supplement = supplements.get(isbn, {})

        book = Book.from_api_response(
            book_data=book_data,
            category_id=category_id,
            category_name=category_name,
            list_name=list_name,
            published_date=published_date,
            supplement=supplement,
        )

        # 保存 NYT 原始图片 URL 作为兜底（缓存失效时使用）
        original_image_url = book_data.get('book_image', '') or ''
        book._original_cover = original_image_url
        book.cover = self._image_cache.get_cached_image_url(original_image_url)

        if isbn in translations:
            trans = translations[isbn]
            book.title_zh = trans.get('title_zh')
            book.description_zh = trans.get('description_zh')
            book.details_zh = trans.get('details_zh')

        return book

    def _run_with_context(self, func: Callable[[], Any]) -> Any:
        """在应用上下文中执行函数（如有app则自动推送上下文）"""
        if self._app:
            with self._app.app_context():
                return func()
        return func()

    @staticmethod
    def _book_value(book: Book | dict[str, Any], attr: str) -> Any:
        return book.get(attr) if isinstance(book, dict) else getattr(book, attr, None)

    @staticmethod
    def _book_isbn(book: Book | dict[str, Any]) -> str:
        return str(BookService._book_value(book, 'isbn13') or BookService._book_value(book, 'isbn10') or '').strip()

    @staticmethod
    def _parse_page_count(value: Any) -> int | None:
        if value in (None, '', 'Unknown', '未知'):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def save_book_metadata(self, book: Book | dict[str, Any]) -> bool:
        """保存NYT图书英文资料到后台元数据表，供后续补齐和排查使用。"""
        isbn = self._book_isbn(book)
        if not isbn:
            return False

        def _save():
            from ..models.database import db
            from ..models.schemas import BookMetadata

            title = str(self._book_value(book, 'title') or isbn)
            author = str(self._book_value(book, 'author') or 'Unknown Author')

            metadata = db.session.get(BookMetadata, isbn)
            if not metadata:
                metadata = BookMetadata(isbn=isbn, title=title, author=author)
                db.session.add(metadata)

            metadata.title = title
            metadata.author = author

            details = self._book_value(book, 'details')
            if details and details != 'No detailed description available.':
                metadata.details = str(details)

            page_count = self._parse_page_count(self._book_value(book, 'page_count'))
            if page_count is not None:
                metadata.page_count = page_count

            language = self._book_value(book, 'language')
            if language and language != 'Unknown':
                metadata.language = str(language)

            publication_date = self._book_value(book, 'publication_dt') or self._book_value(book, 'published_date')
            if publication_date and publication_date != 'Unknown':
                metadata.publication_date = str(publication_date)

            db.session.commit()
            return True

        try:
            return self._run_with_context(_save)
        except (IntegrityError, OperationalError, SQLAlchemyError) as e:
            logger.error(f'保存图书元数据失败: {e}')
            try:
                self._run_with_context(lambda: db.session.rollback())
            except (IntegrityError, OperationalError, SQLAlchemyError):
                pass
            return False

    def save_book_translation(
        self, isbn: str, title_zh: str | None = None, description_zh: str | None = None, details_zh: str | None = None
    ) -> bool:
        """保存图书翻译到数据库"""
        if not isbn:
            return False

        def _save():
            from datetime import datetime

            from ..models.database import db
            from ..models.schemas import BookMetadata

            metadata = db.session.get(BookMetadata, isbn)
            if not metadata:
                metadata = BookMetadata(isbn=isbn, title=isbn, author='Unknown Author')
                db.session.add(metadata)

            if title_zh:
                metadata.title_zh = title_zh
            if description_zh:
                metadata.description_zh = description_zh
            if details_zh:
                metadata.details_zh = details_zh

            metadata.translated_at = datetime.now(UTC)
            db.session.commit()
            logger.info(f'翻译已保存: {isbn}')
            return True

        try:
            return self._run_with_context(_save)
        except (IntegrityError, OperationalError, SQLAlchemyError) as e:
            logger.error(f'保存翻译失败: {e}')
            try:
                self._run_with_context(lambda: db.session.rollback())
            except (IntegrityError, OperationalError, SQLAlchemyError):
                pass
            return False

    @staticmethod
    def _translator_is_available(service: Any | None) -> bool:
        if not service or not hasattr(service, 'translate'):
            return False
        is_available = getattr(service, 'is_available', None)
        if callable(is_available):
            return bool(is_available())
        return True

    def _get_translation_service(self) -> Any | None:
        try:
            from .zhipu_translation_service import get_translation_service

            return get_translation_service(app=self._app)
        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'翻译服务不可用: {e}', level='warning')
            return None

    def _translate_books_now(self, books: list[Book], translator: Any | None = None) -> dict[str, int]:
        service = translator or self._get_translation_service()
        if not self._translator_is_available(service):
            logger.warning('翻译服务不可用，跳过语言包写入')
            return {
                'books_seen': len(books),
                'books_missing': 0,
                'fields_from_pack': 0,
                'fields_stored': 0,
                'fields_translated': 0,
                'failures': 0,
                'pack_writes': 0,
            }

        return self._language_pack.translate_and_store_books(
            books,
            translator=service,
            save_metadata=self.save_book_translation,
        )

    def sync_all_categories(
        self,
        categories: list[str] | None = None,
        force_refresh: bool = True,
        translate: bool = True,
        translator: Any | None = None,
    ) -> list[dict[str, Any]]:
        """强制同步全部NYT分类，补充图书资料，并把翻译写入语言包/数据库。"""
        category_ids = categories or list(self._categories.keys())
        results: list[dict[str, Any]] = []

        for category_id in category_ids:
            category_name = self._categories.get(category_id, category_id)
            try:
                books = self.get_books_by_category(
                    category_id,
                    force_refresh=force_refresh,
                    auto_translate=False,
                    notify_refresh=False,
                )
                metadata_saved = sum(1 for book in books if self.save_book_metadata(book))
                language_pack_stats = (
                    self._translate_books_now(books, translator=translator)
                    if translate
                    else {
                        'books_seen': len(books),
                        'books_missing': 0,
                        'fields_from_pack': 0,
                        'fields_stored': 0,
                        'fields_translated': 0,
                        'failures': 0,
                        'pack_writes': 0,
                    }
                )

                results.append(
                    {
                        'category_id': category_id,
                        'category_name': category_name,
                        'success': True,
                        'books': len(books),
                        'metadata_saved': metadata_saved,
                        'language_pack': language_pack_stats,
                    }
                )
            except Exception as e:
                log_error(ErrorCategory.API_CALL, f'NYT分类同步失败 {category_id}: {e}')
                results.append(
                    {
                        'category_id': category_id,
                        'category_name': category_name,
                        'success': False,
                        'books': 0,
                        'metadata_saved': 0,
                        'language_pack': {},
                        'error': str(e),
                    }
                )

        if any(result.get('success') for result in results):
            self._notify_data_refreshed()

        return results

    def _auto_translate_books(self, books: list[Book]) -> None:
        """
        自动预翻译图书信息（后台异步执行）

        在后台线程中自动翻译图书的标题和描述，
        并保存到数据库，下次访问时直接读取已翻译内容

        Args:
            books: 图书列表
        """
        if self._app and self._app.config.get('TESTING'):
            return
        if self._app is None and getattr(self._language_pack, '_pack_path', None) is None:
            return

        with self._translation_lock:
            if self._translation_thread_active:
                logger.info('预翻译线程已在运行中，跳过重复启动')
                return
            if not books:
                logger.debug('无图书数据，跳过预翻译')
                return
            self._translation_thread_active = True

        def translate_in_background():
            """后台线程执行翻译任务"""
            try:
                stats = self._translate_books_now(books)

                logger.info(
                    '批量预翻译完成: 图书%s本, 翻译字段%s个, 语言包写入%s次',
                    stats.get('books_missing', 0),
                    stats.get('fields_translated', 0),
                    stats.get('pack_writes', 0),
                )

            except (RuntimeError, AttributeError) as e:
                logger.error(f'后台翻译线程异常: {e}')
            finally:
                with self._translation_lock:
                    self._translation_thread_active = False

        thread = threading.Thread(target=translate_in_background, daemon=True)
        thread.start()
        logger.info(f'已启动后台预翻译线程，共 {len(books)} 本图书待处理')

    def search_books(self, keyword: str, categories: list[str] | None = None) -> list[Book]:
        """
        搜索图书

        Args:
            keyword: 搜索关键词
            categories: 要搜索的分类列表，默认为所有分类

        Returns:
            匹配的图书列表
        """
        if not categories:
            categories = list(self._categories.keys())

        results = []
        keyword_lower = keyword.lower()

        for category_id in categories:
            try:
                books = self.get_books_by_category(category_id)
                for book in books:
                    if keyword_lower in book.title.lower() or keyword_lower in book.author.lower():
                        results.append(book)
            except (APIException, APIRateLimitException, ExternalAPIError) as e:
                logger.error(f'Error searching in category {category_id}: {e}')

        return results

    def get_latest_cache_time(self) -> str:
        """获取最新的缓存时间"""
        latest_time = None

        for category_id in self._categories:
            cache_time = self._cache.get_cache_time(f'books_{category_id}')
            if cache_time:
                from datetime import datetime

                try:
                    cache_dt = datetime.strptime(cache_time, '%Y-%m-%d %H:%M:%S')
                    if not latest_time or cache_dt > latest_time:
                        latest_time = cache_dt
                except ValueError:
                    continue

        return latest_time.strftime('%Y-%m-%d %H:%M:%S') if latest_time else '暂无数据'
