import logging
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

from ...models.database import db
from ...models.new_book import NewBook, Publisher
from ..book_language_pack import BookLanguagePack
from ..cache_service import CacheService
from .publisher_manager import PublisherManager
from .query_service import NewBookQueryService
from .sync_engine import SyncEngine
from .translation_pipeline import TranslationPipeline

logger = logging.getLogger(__name__)


class NewBookService:
    DEFAULT_PUBLISHERS = PublisherManager.DEFAULT_PUBLISHERS
    STATIC_DATA_FILES = PublisherManager.STATIC_DATA_FILES
    VALID_CATEGORIES = PublisherManager.VALID_CATEGORIES
    _CRAWLER_MIGRATION = PublisherManager._CRAWLER_MIGRATION

    _instance: 'NewBookService | None' = None
    _cache: CacheService | None
    _translator: Any | None
    _language_pack: BookLanguagePack
    _publisher_manager: PublisherManager
    _translation_pipeline: TranslationPipeline
    _sync_engine: SyncEngine
    _query_service: NewBookQueryService
    _initialized: bool

    def __new__(cls, *args: Any, **kwargs: Any) -> 'NewBookService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(
        self,
        cache_service: CacheService | None = None,
        translation_service: Any | None = None,
        language_pack_path: str | Path | None = None,
    ):
        if hasattr(self, '_initialized') and self._initialized:
            if cache_service and not self._cache:
                self._cache = cache_service
            if translation_service and not self._translator:
                self._translator = translation_service
                self._translation_pipeline._translator = translation_service
            if language_pack_path:
                self._language_pack = BookLanguagePack(language_pack_path)
                self._translation_pipeline._language_pack = self._language_pack
            elif not hasattr(self, '_language_pack'):
                self._language_pack = BookLanguagePack(self._resolve_language_pack_path())
                self._translation_pipeline._language_pack = self._language_pack
            elif getattr(self._language_pack, '_pack_path', None) is None:
                resolved_pack_path = self._resolve_language_pack_path()
                if resolved_pack_path:
                    self._language_pack = BookLanguagePack(resolved_pack_path)
                    self._translation_pipeline._language_pack = self._language_pack
            return
        self._cache = cache_service
        self._translator = translation_service
        self._language_pack = BookLanguagePack(language_pack_path or self._resolve_language_pack_path())
        self._publisher_manager = PublisherManager()
        self._translation_pipeline = TranslationPipeline(self._translator, self._language_pack)
        self._sync_engine = SyncEngine(self._publisher_manager, self._translation_pipeline)
        self._query_service = NewBookQueryService(self._translation_pipeline)
        self._initialized = True

    @staticmethod
    def _resolve_language_pack_path() -> Path | None:
        if has_app_context() and current_app.static_folder:
            return Path(current_app.static_folder) / 'data' / 'book_language_pack.zh.json'
        return None

    def init_publishers(self) -> int:
        return self._publisher_manager.init_publishers()

    def get_publishers(self, active_only: bool = True) -> list[Publisher]:
        return self._publisher_manager.get_publishers(active_only=active_only)

    def get_publisher(self, publisher_id: int) -> Publisher | None:
        return self._publisher_manager.get_publisher(publisher_id=publisher_id)

    def update_publisher_status(self, publisher_id: int, is_active: bool) -> bool:
        return self._publisher_manager.update_publisher_status(publisher_id=publisher_id, is_active=is_active)

    def get_publisher_book_counts(self) -> dict[int, int]:
        return self._publisher_manager.get_publisher_book_counts()

    def sync_publisher_books(
        self, publisher_id: int, category: str | None = None, max_books: int = 50, translate: bool = True
    ) -> dict[str, Any]:
        return self._sync_engine.sync_publisher_books(
            publisher_id=publisher_id, category=category, max_books=max_books, translate=translate
        )

    def sync_all_publishers(
        self,
        category: str | None = None,
        max_books_per_publisher: int = 30,
        translate: bool = True,
        batch_size: int = 1,
    ) -> list[dict[str, Any]]:
        return self._sync_engine.sync_all_publishers(
            category=category,
            max_books_per_publisher=max_books_per_publisher,
            translate=translate,
            batch_size=batch_size,
        )

    def seed_from_static_data(self, static_data_dir: str | Path | None = None) -> dict[str, Any]:
        return self._sync_engine.seed_from_static_data(static_data_dir=static_data_dir)

    def ensure_static_data_seeded(self) -> dict[str, Any] | None:
        return self._sync_engine.ensure_static_data_seeded()

    def get_crawler(self, crawler_class: str):
        return self._sync_engine.get_crawler(crawler_class=crawler_class)

    def translate_book_background(self, book_id: int, translation_service: Any) -> None:
        self._translation_pipeline.translate_book_background(book_id=book_id, translation_service=translation_service)

    def get_new_books(
        self,
        publisher_id: int | None = None,
        category: str | None = None,
        days: int = 30,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[NewBook], int]:
        return self._query_service.get_new_books(
            publisher_id=publisher_id, category=category, days=days, page=page, per_page=per_page
        )

    def get_book(self, book_id: int) -> NewBook | None:
        return self._query_service.get_book(book_id=book_id)

    def search_books(
        self,
        keyword: str,
        page: int = 1,
        per_page: int = 20,
        publisher_id: int | None = None,
        category: str | None = None,
        days: int | None = None,
    ) -> tuple[list[NewBook], int]:
        return self._query_service.search_books(
            keyword=keyword, page=page, per_page=per_page, publisher_id=publisher_id, category=category, days=days
        )

    def get_categories(self) -> list[dict[str, str]]:
        return self._query_service.get_categories()

    def get_statistics(self) -> dict[str, Any]:
        return self._query_service.get_statistics()

    def migrate_categories(self) -> dict[str, int]:
        """迁移已有书籍分类数据（英文分类统一为中文），事务控制在 Service 层完成"""
        from ..publisher_data import sanitize_category

        try:
            books = NewBook.query.filter(NewBook.category.isnot(None)).all()
            migrated_count = 0

            for book in books:
                old_category = book.category
                new_category = sanitize_category(old_category)
                if new_category != old_category:
                    book.category = new_category
                    migrated_count += 1

            if migrated_count > 0:
                db.session.commit()

            return {'migrated_count': migrated_count, 'total_checked': len(books)}
        except Exception:
            # 事务失败时回滚并重新抛出，由路由层统一返回 500
            try:
                db.session.rollback()
            except Exception:
                pass
            raise
