"""NewBookIngestor —— 新书入库的深模块。

把新书的去重、字段合并、新建与 ORM 持久化集中在此，对外只暴露
save_book / update_book_fields 两个稳定接口。以往这些逻辑散落在
SyncEngine 上，导致引擎承担了同步编排以外的大量入库规则，接口与
实现一样复杂（浅模块）。提取后，入库规则的复杂度集中在内部，
SyncEngine 只保留同步编排职责，测试可直接针对入库规则。
"""

from datetime import UTC, date, datetime
from enum import Enum

from ...models.database import db
from ...models.new_book import NewBook, Publisher
from .. import publisher_data as pd
from ..publisher_crawler.base_crawler import BookInfo
from .translation_pipeline import TranslationPipeline


class SaveOutcome(Enum):
    """save_book 的返回结果类型，替代裸字符串常量。"""

    ADDED = 'added'
    UPDATED = 'updated'
    SKIPPED = 'skipped'


class NewBookIngestor:
    def __init__(self, translation_pipeline: TranslationPipeline) -> None:
        self._translation = translation_pipeline

    def save_book(
        self,
        publisher: Publisher,
        book_info: BookInfo,
        translate: bool = True,
        auto_commit: bool = True,
        touched_books: list[NewBook] | None = None,
    ) -> SaveOutcome:
        """保存一本书：先去重，命中则合并字段，否则新建。"""
        existing = self._find_existing(publisher, book_info)
        if existing:
            return self._merge_existing(existing, publisher, book_info, translate, auto_commit, touched_books)
        return self._insert_new(publisher, book_info, translate, auto_commit, touched_books)

    def update_book_fields(self, book: NewBook, book_info: BookInfo, auto_commit: bool = True) -> bool:
        """按 book_info 更新已存在书籍的字段，返回是否有实际变更。"""
        updated = False

        if book_info.description and book_info.description != book.description:
            book.description = book_info.description
            book.description_zh = None
            updated = True

        if book_info.cover_url and book_info.cover_url != book.cover_url:
            book.cover_url = book_info.cover_url
            updated = True

        category = pd.sanitize_category(getattr(book_info, 'category', None))
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

    def _find_existing(self, publisher: Publisher, book_info: BookInfo) -> NewBook | None:
        """按优先级（isbn13 → isbn10 → 标题+作者）查找同出版社的存量书。"""
        if book_info.isbn13:
            existing = NewBook.query.filter_by(publisher_id=publisher.id, isbn13=book_info.isbn13).first()
            if existing:
                return existing

        if book_info.isbn10:
            existing = NewBook.query.filter_by(publisher_id=publisher.id, isbn10=book_info.isbn10).first()
            if existing:
                return existing

        return NewBook.query.filter_by(
            publisher_id=publisher.id, title=book_info.title, author=book_info.author
        ).first()

    def _merge_existing(
        self,
        existing: NewBook,
        publisher: Publisher,
        book_info: BookInfo,
        translate: bool,
        auto_commit: bool,
        touched_books: list[NewBook] | None,
    ) -> SaveOutcome:
        updated = self.update_book_fields(existing, book_info, auto_commit=auto_commit)
        translated = False
        if translate and self._translation.translator_enabled:
            translated = self._translation.translate_book(existing)
        if touched_books is not None:
            touched_books.append(existing)
        if updated:
            return SaveOutcome.UPDATED
        if translated:
            if auto_commit:
                db.session.commit()
            return SaveOutcome.UPDATED
        return SaveOutcome.SKIPPED

    def _insert_new(
        self,
        publisher: Publisher,
        book_info: BookInfo,
        translate: bool,
        auto_commit: bool,
        touched_books: list[NewBook] | None,
    ) -> SaveOutcome:
        new_book = NewBook(
            publisher_id=publisher.id,
            title=book_info.title,
            author=book_info.author,
            isbn13=book_info.isbn13,
            isbn10=book_info.isbn10,
            description=book_info.description,
            cover_url=book_info.cover_url,
            category=pd.sanitize_category(book_info.category),
            publication_date=self._coerce_publication_date(book_info.publication_date),
            price=book_info.price,
            page_count=book_info.page_count,
            language=book_info.language,
            source_url=book_info.source_url,
        )

        if book_info.buy_links:
            new_book.set_buy_links(book_info.buy_links)

        if translate and self._translation.translator_enabled:
            self._translation.translate_book(new_book)

        db.session.add(new_book)
        if touched_books is not None:
            touched_books.append(new_book)
        if auto_commit:
            db.session.commit()

        return SaveOutcome.ADDED

    @staticmethod
    def _coerce_publication_date(value: date | None) -> date | None:
        return pd.coerce_publication_date(value)
