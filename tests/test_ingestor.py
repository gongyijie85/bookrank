"""
NewBookIngestor 单元测试

测试深模块「新书入库」的去重、字段合并、新建与 ORM 持久化逻辑。
这些逻辑从 SyncEngine 的 _save_book / _update_book_fields 提取而来，
测试不再经由 SyncEngine，而是直接面向入库模块的稳定接口
（save_book / update_book_fields），隔离外部依赖。
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.new_book.ingestor import NewBookIngestor, SaveOutcome
from app.services.publisher_crawler.base_crawler import BookInfo


@pytest.fixture
def translation_pipeline():
    """哑翻译管线：仅用于注入，测试默认 translate=False 不触发翻译。"""
    return MagicMock()


@pytest.fixture
def ingestor(translation_pipeline):
    return NewBookIngestor(translation_pipeline)


@pytest.fixture
def sample_publisher(db):
    publisher = Publisher(
        name='测试出版社',
        name_en='Test Publisher',
        website='https://example.com',
        crawler_class='PenguinCrawler',
        is_active=True,
        sync_count=0,
    )
    db.session.add(publisher)
    db.session.commit()
    return publisher


@pytest.fixture
def sample_book_info():
    return BookInfo(
        title='Test Book',
        author='Test Author',
        isbn13='9780000000001',
        isbn10='0000000001',
        description='A test book description',
        cover_url='https://example.com/cover.jpg',
        category='Fiction',
        publication_date=date(2026, 1, 15),
        price='29.99',
        page_count=300,
        language='en',
        buy_links=[{'name': 'Amazon', 'url': 'https://amazon.com'}],
        source_url='https://example.com/book',
    )


class TestSaveBook:
    """save_book 保存与去重逻辑测试"""

    def test_adds_new_book(self, ingestor, sample_publisher, sample_book_info, db):
        result = ingestor.save_book(sample_publisher, sample_book_info, translate=False)
        assert result is SaveOutcome.ADDED
        assert NewBook.query.count() == 1
        book = NewBook.query.first()
        assert book.title == 'Test Book'
        assert book.isbn13 == '9780000000001'
        assert book.isbn10 == '0000000001'
        assert book.price == '29.99'
        assert book.page_count == 300

    def test_skips_duplicate_by_isbn13(self, ingestor, sample_publisher, db):
        book_info = BookInfo(
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='same',
            cover_url='https://same.com',
        )
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='same',
            cover_url='https://same.com',
        )
        db.session.add(existing)
        db.session.commit()

        result = ingestor.save_book(sample_publisher, book_info, translate=False)
        assert result is SaveOutcome.SKIPPED
        assert NewBook.query.count() == 1

    def test_skips_duplicate_by_isbn10(self, ingestor, sample_publisher, db):
        book_info = BookInfo(
            title='Test Book',
            author='Test Author',
            isbn10='0000000001',
            description='same',
            cover_url='https://same.com',
        )
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn10='0000000001',
            description='same',
            cover_url='https://same.com',
        )
        db.session.add(existing)
        db.session.commit()

        result = ingestor.save_book(sample_publisher, book_info, translate=False)
        assert result is SaveOutcome.SKIPPED
        assert NewBook.query.count() == 1

    def test_skips_duplicate_by_title_and_author(self, ingestor, sample_publisher, db):
        book_info = BookInfo(
            title='Test Book',
            author='Test Author',
            description='same',
            cover_url='https://same.com',
        )
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            description='same',
            cover_url='https://same.com',
        )
        db.session.add(existing)
        db.session.commit()

        result = ingestor.save_book(sample_publisher, book_info, translate=False)
        assert result is SaveOutcome.SKIPPED
        assert NewBook.query.count() == 1

    def test_updates_existing_book_when_description_changed(self, ingestor, sample_publisher, sample_book_info, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='Old description',
        )
        db.session.add(existing)
        db.session.commit()

        result = ingestor.save_book(sample_publisher, sample_book_info, translate=False)
        assert result is SaveOutcome.UPDATED
        book = NewBook.query.first()
        assert book.description == 'A test book description'
        assert book.description_zh is None

    def test_sets_buy_links(self, ingestor, sample_publisher, sample_book_info, db):
        ingestor.save_book(sample_publisher, sample_book_info, translate=False)
        book = NewBook.query.first()
        links = book.get_buy_links()
        assert len(links) == 1
        assert links[0]['name'] == 'Amazon'

    def test_appends_to_touched_books(self, ingestor, sample_publisher, sample_book_info, db):
        touched = []
        ingestor.save_book(sample_publisher, sample_book_info, translate=False, touched_books=touched)
        assert len(touched) == 1
        assert touched[0].title == 'Test Book'

    def test_no_auto_commit_when_disabled(self, ingestor, sample_publisher, sample_book_info, db):
        result = ingestor.save_book(sample_publisher, sample_book_info, translate=False, auto_commit=False)
        assert result is SaveOutcome.ADDED
        assert NewBook.query.count() == 1


class TestUpdateBookFields:
    """update_book_fields 字段更新逻辑测试"""

    def test_updates_changed_fields(self, ingestor, sample_publisher, db):
        book = NewBook(
            publisher_id=sample_publisher.id,
            title='T',
            author='A',
            description='old',
            cover_url='https://old.com',
            price='10.00',
        )
        db.session.add(book)
        db.session.commit()

        book_info = BookInfo(
            title='T',
            author='A',
            description='new',
            cover_url='https://new.com',
            price='20.00',
        )
        updated = ingestor.update_book_fields(book, book_info)
        assert updated is True
        assert book.description == 'new'
        assert book.description_zh is None
        assert book.cover_url == 'https://new.com'
        assert book.price == '20.00'
        assert book.updated_at is not None

    def test_no_update_when_fields_unchanged(self, ingestor, sample_publisher, db):
        book = NewBook(
            publisher_id=sample_publisher.id,
            title='T',
            author='A',
            description='same',
            cover_url='https://same.com',
        )
        db.session.add(book)
        db.session.commit()

        book_info = BookInfo(
            title='T',
            author='A',
            description='same',
            cover_url='https://same.com',
        )
        updated = ingestor.update_book_fields(book, book_info)
        assert updated is False

    def test_updates_buy_links(self, ingestor, sample_publisher, db):
        book = NewBook(
            publisher_id=sample_publisher.id,
            title='T',
            author='A',
        )
        db.session.add(book)
        db.session.commit()

        book_info = BookInfo(
            title='T',
            author='A',
            buy_links=[{'name': 'B&N', 'url': 'https://bn.com'}],
        )
        updated = ingestor.update_book_fields(book, book_info)
        assert updated is True
        assert book.get_buy_links()[0]['name'] == 'B&N'
