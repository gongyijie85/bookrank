"""NewBookIngestor —— 新书入库的深模块。

把新书的去重、字段合并、新建与 ORM 持久化集中在此，对外只暴露
save_book / update_book_fields 两个稳定接口。以往这些逻辑散落在
SyncEngine 上，导致引擎承担了同步编排以外的大量入库规则，接口与
实现一样复杂（浅模块）。提取后，入库规则的复杂度集中在内部，
SyncEngine 只保留同步编排职责，测试可直接针对入库规则。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from enum import Enum
from threading import local as threading_local

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


class _PublisherBookIndex:
    """出版社存量书内存索引：isbn13 / isbn10 / (title, author) 三键。

    批级去重用——一次预载查询替代每本书最多 3 次的逐本往返
    （性能评审 N+1：回填 2000 本 ≈ 6000 次外部 PG round-trip → 1 次预载）。
    """

    def __init__(self, publisher: Publisher) -> None:
        self._by_isbn13: dict[str, NewBook] = {}
        self._by_isbn10: dict[str, NewBook] = {}
        self._by_title_author: dict[tuple[str, str], NewBook] = {}
        for book in NewBook.query.filter_by(publisher_id=publisher.id).all():
            self.add(book)

    def add(self, book: NewBook) -> None:
        """把一本书登记进索引（新建回填用；同键冲突时先登记者胜，等价 first()）。"""
        if book.isbn13:
            self._by_isbn13.setdefault(book.isbn13, book)
        if book.isbn10:
            self._by_isbn10.setdefault(book.isbn10, book)
        self._by_title_author.setdefault((book.title, book.author), book)

    def find(self, book_info: BookInfo) -> NewBook | None:
        """与 _find_existing 同优先级：isbn13 → isbn10 → 标题+作者。"""
        if book_info.isbn13:
            found = self._by_isbn13.get(book_info.isbn13)
            if found is not None:
                return found
        if book_info.isbn10:
            found = self._by_isbn10.get(book_info.isbn10)
            if found is not None:
                return found
        return self._by_title_author.get((book_info.title, book_info.author))


class _IngestorLocal(threading_local):
    """线程隔离的预载索引状态（同步线程与播种线程互不串扰）。"""

    index: _PublisherBookIndex | None = None


class NewBookIngestor:
    def __init__(self, translation_pipeline: TranslationPipeline) -> None:
        self._translation = translation_pipeline
        self._local = _IngestorLocal()

    @contextmanager
    def preloaded_lookup(self, publisher: Publisher) -> Iterator[None]:
        """批级预载上下文：进入时一次查询构建该社存量书索引。

        上下文内的 save_book 去重查找走内存字典（零查询）；新建的书
        回填索引，保持同批后续重复书命中的语义（等价原 autoflush 路径）。
        """
        self._local.index = _PublisherBookIndex(publisher)
        try:
            yield
        finally:
            self._local.index = None

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
        """按优先级（isbn13 → isbn10 → 标题+作者）查找同出版社的存量书。

        处于 preloaded_lookup 上下文时走内存索引（零查询）；
        否则回退逐本查询路径（单本调用 / 未预载场景）。
        """
        index = self._local.index
        if index is not None:
            return index.find(book_info)

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
        # 回填预载索引：同批后续重复书走字典命中（等价原 autoflush 后查询命中的语义）
        index = self._local.index
        if index is not None:
            index.add(new_book)
        if touched_books is not None:
            touched_books.append(new_book)
        if auto_commit:
            db.session.commit()

        return SaveOutcome.ADDED

    @staticmethod
    def _coerce_publication_date(value: date | None) -> date | None:
        return pd.coerce_publication_date(value)
