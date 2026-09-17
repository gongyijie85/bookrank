"""
NewBookIngestor 单元测试

测试深模块「新书入库」的去重、字段合并、新建与 ORM 持久化逻辑。
这些逻辑从 SyncEngine 的 _save_book / _update_book_fields 提取而来，
测试不再经由 SyncEngine，而是直接面向入库模块的稳定接口
（save_book / update_book_fields），隔离外部依赖。
"""

from datetime import date
from unittest.mock import MagicMock, patch

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


class _QueryBomb:
    """任何属性访问即爆炸：用于断言预载上下文内零 DB 查询。"""

    def __getattr__(self, name: str):
        raise AssertionError(f'不应触发 DB 查询: NewBook.query.{name}')


class TestPreloadedLookup:
    """批级预载索引（性能评审 N+1：每本书最多 3 次去重查询 → 1 次预载）"""

    def test_preloaded_hit_makes_no_queries(self, ingestor, sample_publisher, db):
        """上下文内去重查找走内存索引，零查询（回归：逐本 3 次往返）"""
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

        with ingestor.preloaded_lookup(sample_publisher):
            with patch.object(NewBook, 'query', _QueryBomb()):
                result = ingestor.save_book(sample_publisher, book_info, translate=False)
        assert result is SaveOutcome.SKIPPED
        assert NewBook.query.count() == 1

    def test_preloaded_title_author_hit(self, ingestor, sample_publisher, db):
        """无 ISBN 的书靠 (title, author) 键命中索引。"""
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='No ISBN Book',
            author='Some Author',
            description='same',
        )
        db.session.add(existing)
        db.session.commit()

        book_info = BookInfo(title='No ISBN Book', author='Some Author', description='same')
        with ingestor.preloaded_lookup(sample_publisher):
            with patch.object(NewBook, 'query', _QueryBomb()):
                result = ingestor.save_book(sample_publisher, book_info, translate=False)
        assert result is SaveOutcome.SKIPPED

    def test_same_batch_duplicate_hits_inserted_book(self, ingestor, sample_publisher, sample_book_info, db):
        """同批第二本重复书命中回填索引（等价原 autoflush 后查询命中的语义）。"""
        duplicate = BookInfo(
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='A test book description',
        )

        with ingestor.preloaded_lookup(sample_publisher):
            first = ingestor.save_book(sample_publisher, sample_book_info, translate=False, auto_commit=False)
            second = ingestor.save_book(sample_publisher, duplicate, translate=False, auto_commit=False)

        assert first is SaveOutcome.ADDED
        assert second is not SaveOutcome.ADDED
        assert NewBook.query.count() == 1

    def test_context_exit_falls_back_to_queries(self, ingestor, sample_publisher, db):
        """退出上下文后恢复逐本查询路径（单本调用 / 测试场景兼容）。"""
        book_info = BookInfo(
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='same',
            cover_url='https://same.com',
        )
        with ingestor.preloaded_lookup(sample_publisher):
            ingestor.save_book(sample_publisher, book_info, translate=False)

        # 上下文外再存同书：走回退查询路径命中 → SKIPPED
        result = ingestor.save_book(sample_publisher, book_info, translate=False)
        assert result is SaveOutcome.SKIPPED
        assert NewBook.query.count() == 1

    def test_index_is_thread_local(self, ingestor, sample_publisher, sample_book_info, db):
        """预载状态线程隔离：其他线程未进入上下文时不受索引影响。"""
        from threading import Thread

        with ingestor.preloaded_lookup(sample_publisher):
            errors: list[str] = []

            def _other_thread() -> None:
                # 另一线程无索引 → 应走回退路径（不会命中本线程索引）
                if ingestor._local.index is not None:
                    errors.append('其他线程不应看到索引')

            t = Thread(target=_other_thread)
            t.start()
            t.join(timeout=5)

            assert errors == []
            assert ingestor._local.index is not None


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
