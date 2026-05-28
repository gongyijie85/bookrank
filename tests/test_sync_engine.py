"""
SyncEngine 单元测试

测试核心同步流程：出版社同步、批量同步、书籍保存、
去重逻辑、错误处理和状态追踪，所有外部依赖通过 mock 隔离。
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.new_book.sync_engine import SyncEngine
from app.services.publisher_crawler.base_crawler import BookInfo


@pytest.fixture
def publisher_manager():
    return MagicMock()


@pytest.fixture
def translation_pipeline():
    pipeline = MagicMock()
    pipeline._translator = MagicMock()
    pipeline._translate_book.return_value = False
    pipeline._translate_and_store_language_pack.return_value = {}
    return pipeline


@pytest.fixture
def engine(publisher_manager, translation_pipeline):
    return SyncEngine(publisher_manager, translation_pipeline)


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


class TestSyncEngineInit:
    """SyncEngine 初始化测试"""

    def test_init_stores_dependencies(self, publisher_manager, translation_pipeline):
        engine = SyncEngine(publisher_manager, translation_pipeline)
        assert engine._publisher_manager is publisher_manager
        assert engine._translation_pipeline is translation_pipeline

    def test_google_books_crawlers_set(self, engine):
        assert 'GoogleBooksCrawler' in engine._GOOGLE_BOOKS_CRAWLERS
        assert 'MacmillanCrawler' in engine._GOOGLE_BOOKS_CRAWLERS
        assert len(engine._GOOGLE_BOOKS_CRAWLERS) == 6


class TestSyncPublisherBooks:
    """sync_publisher_books 核心同步流程测试"""

    def test_returns_error_when_publisher_not_found(self, engine, publisher_manager, db):
        publisher_manager.get_publisher.return_value = None
        result = engine.sync_publisher_books(999)
        assert result['success'] is False
        assert '出版社不存在' in result['error']

    def test_returns_error_when_publisher_inactive(self, engine, publisher_manager, sample_publisher, db):
        sample_publisher.is_active = False
        publisher_manager.get_publisher.return_value = sample_publisher
        result = engine.sync_publisher_books(sample_publisher.id)
        assert result['success'] is False
        assert '出版社已禁用' in result['error']

    def test_returns_error_when_crawler_unavailable(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher
        with patch.object(engine, 'get_crawler', return_value=None):
            result = engine.sync_publisher_books(sample_publisher.id)
        assert result['success'] is False
        assert '爬虫不可用' in result['error']

    def test_sync_with_empty_crawler(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter([])
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id)

        assert result['success'] is True
        assert result['total'] == 0
        assert result['added'] == 0
        assert sample_publisher.sync_count == 1

    def test_sync_adds_new_books(self, engine, publisher_manager, sample_publisher, sample_book_info, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter([sample_book_info])
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['success'] is True
        assert result['total'] == 1
        assert result['added'] == 1
        assert NewBook.query.count() == 1
        book = NewBook.query.first()
        assert book.title == 'Test Book'
        assert book.isbn13 == '9780000000001'

    def test_sync_skips_duplicate_by_isbn13(self, engine, publisher_manager, sample_publisher, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='A test book description',
            cover_url='https://example.com/cover.jpg',
            category='Fiction',
            publication_date=date(2026, 1, 15),
            price='29.99',
            page_count=300,
            language='en',
            source_url='https://example.com/book',
        )
        existing.set_buy_links([{'name': 'Amazon', 'url': 'https://amazon.com'}])
        db.session.add(existing)
        db.session.commit()

        book_info = BookInfo(
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='A test book description',
            cover_url='https://example.com/cover.jpg',
            category='Fiction',
            publication_date=date(2026, 1, 15),
            price='29.99',
            page_count=300,
            language='en',
            source_url='https://example.com/book',
        )

        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter([book_info])
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['skipped'] == 1
        assert result['added'] == 0
        assert NewBook.query.count() == 1

    def test_sync_updates_existing_book_fields(self, engine, publisher_manager, sample_publisher, sample_book_info, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='Old description',
            cover_url='https://old.com/cover.jpg',
        )
        db.session.add(existing)
        db.session.commit()

        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter([sample_book_info])
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['updated'] == 1
        assert result['added'] == 0
        book = NewBook.query.first()
        assert book.description == 'A test book description'
        assert book.cover_url == 'https://example.com/cover.jpg'

    def test_sync_counts_book_save_error(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter(
            [
                BookInfo(title='OK Book', author='Author A'),
                BookInfo(title='Bad Book', author='Author B'),
            ]
        )
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def fake_save(publisher, book_info, translate=True, auto_commit=True, touched_books=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError('DB failure')
            return 'added'

        with (
            patch.object(engine, 'get_crawler', return_value=mock_crawler),
            patch.object(engine, '_save_book', side_effect=fake_save),
        ):
            result = engine.sync_publisher_books(sample_publisher.id)

        assert result['added'] == 1
        assert result['errors'] == 1

    def test_sync_handles_crawler_context_exception(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.__enter__ = MagicMock(side_effect=RuntimeError('Network error'))
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id)

        assert result['success'] is False
        assert 'Network error' in result['error']

    def test_sync_calls_batch_commit(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        books = [BookInfo(title=f'Book {i}', author=f'Author {i}') for i in range(12)]

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter(books)
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['total'] == 12
        assert result['added'] == 12
        assert NewBook.query.count() == 12

    def test_sync_updates_publisher_sync_count_and_last_sync(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter([])
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id)

        assert sample_publisher.sync_count == 1
        assert sample_publisher.last_sync_at is not None

    def test_sync_passes_translate_flag(self, engine, publisher_manager, sample_publisher, sample_book_info, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = iter([sample_book_info])
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id, translate=True)

        engine._translation_pipeline._translate_and_store_language_pack.assert_called_once()


class TestSyncAllPublishers:
    """sync_all_publishers 批量同步测试"""

    def test_iterates_all_active_publishers(self, engine, publisher_manager, db):
        pub1 = MagicMock(id=1, name_en='Pub1', is_active=True, sync_count=0, last_sync_at=None)
        pub2 = MagicMock(id=2, name_en='Pub2', is_active=True, sync_count=0, last_sync_at=None)
        publisher_manager.get_publishers.return_value = [pub1, pub2]

        with patch.object(engine, 'sync_publisher_books') as mock_sync:
            mock_sync.return_value = {'success': True, 'added': 5, 'updated': 0, 'errors': 0}
            results = engine.sync_all_publishers()

        assert len(results) == 2
        assert mock_sync.call_count == 2

    def test_passes_parameters_through(self, engine, publisher_manager, db):
        pub = MagicMock(id=1, name_en='Pub1', is_active=True, sync_count=0, last_sync_at=None)
        publisher_manager.get_publishers.return_value = [pub]

        with patch.object(engine, 'sync_publisher_books') as mock_sync:
            mock_sync.return_value = {'success': True, 'added': 0, 'updated': 0, 'errors': 0}
            engine.sync_all_publishers(category='Fiction', max_books_per_publisher=20, translate=False)

        mock_sync.assert_called_once_with(1, category='Fiction', max_books=20, translate=False)

    def test_aggregates_results(self, engine, publisher_manager, db):
        pub1 = MagicMock(id=1, name_en='Pub1', is_active=True, sync_count=0, last_sync_at=None)
        pub2 = MagicMock(id=2, name_en='Pub2', is_active=True, sync_count=0, last_sync_at=None)
        publisher_manager.get_publishers.return_value = [pub1, pub2]

        with patch.object(engine, 'sync_publisher_books') as mock_sync:
            mock_sync.side_effect = [
                {'success': True, 'added': 3, 'updated': 1, 'errors': 0},
                {'success': True, 'added': 5, 'updated': 2, 'errors': 1},
            ]
            results = engine.sync_all_publishers()

        assert len(results) == 2

    def test_handles_empty_publisher_list(self, engine, publisher_manager, db):
        publisher_manager.get_publishers.return_value = []

        with patch.object(engine, 'sync_publisher_books') as mock_sync:
            results = engine.sync_all_publishers()

        assert results == []
        mock_sync.assert_not_called()

    def test_batch_size_controls_grouping(self, engine, publisher_manager, db):
        publishers = [
            MagicMock(id=i, name_en=f'Pub{i}', is_active=True, sync_count=0, last_sync_at=None) for i in range(5)
        ]
        publisher_manager.get_publishers.return_value = publishers

        with patch.object(engine, 'sync_publisher_books') as mock_sync:
            mock_sync.return_value = {'success': True, 'added': 0, 'updated': 0, 'errors': 0}
            engine.sync_all_publishers(batch_size=2)

        assert mock_sync.call_count == 5


class TestGetCrawler:
    """get_crawler 爬虫实例化测试"""

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_returns_none_when_class_not_found(self, mock_get_cls, engine):
        mock_get_cls.return_value = None
        result = engine.get_crawler('NonexistentCrawler')
        assert result is None

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_returns_crawler_instance(self, mock_get_cls, engine):
        MockCrawler = MagicMock
        mock_get_cls.return_value = MockCrawler
        result = engine.get_crawler('PenguinCrawler')
        assert result is not None

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_google_crawler_gets_api_key_config(self, mock_get_cls, engine, app_context):
        mock_crawler_cls = MagicMock()
        mock_get_cls.return_value = mock_crawler_cls
        engine.get_crawler('GoogleBooksCrawler')
        mock_crawler_cls.assert_called_once()
        call_args = mock_crawler_cls.call_args
        assert call_args[0][0].api_key == app_context.config['GOOGLE_API_KEY']

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_google_crawler_without_api_key_uses_default(self, mock_get_cls, app):
        mock_crawler_cls = MagicMock()
        mock_get_cls.return_value = mock_crawler_cls

        with app.app_context():
            app.config.pop('GOOGLE_API_KEY', None)
            engine = SyncEngine(MagicMock(), MagicMock())
            engine.get_crawler('GoogleBooksCrawler')
        mock_crawler_cls.assert_called_once_with()


class TestSaveBook:
    """_save_book 保存与去重逻辑测试"""

    def test_adds_new_book(self, engine, sample_publisher, sample_book_info, db):
        result = engine._save_book(sample_publisher, sample_book_info, translate=False)
        assert result == 'added'
        assert NewBook.query.count() == 1
        book = NewBook.query.first()
        assert book.title == 'Test Book'
        assert book.isbn13 == '9780000000001'
        assert book.isbn10 == '0000000001'
        assert book.price == '29.99'
        assert book.page_count == 300

    def test_skips_duplicate_by_isbn13(self, engine, sample_publisher, db):
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

        result = engine._save_book(sample_publisher, book_info, translate=False)
        assert result == 'skipped'
        assert NewBook.query.count() == 1

    def test_skips_duplicate_by_isbn10(self, engine, sample_publisher, db):
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

        result = engine._save_book(sample_publisher, book_info, translate=False)
        assert result == 'skipped'
        assert NewBook.query.count() == 1

    def test_skips_duplicate_by_title_and_author(self, engine, sample_publisher, db):
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

        result = engine._save_book(sample_publisher, book_info, translate=False)
        assert result == 'skipped'
        assert NewBook.query.count() == 1

    def test_updates_existing_book_when_description_changed(self, engine, sample_publisher, sample_book_info, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='Old description',
        )
        db.session.add(existing)
        db.session.commit()

        result = engine._save_book(sample_publisher, sample_book_info, translate=False)
        assert result == 'updated'
        book = NewBook.query.first()
        assert book.description == 'A test book description'
        assert book.description_zh is None

    def test_sets_buy_links(self, engine, sample_publisher, sample_book_info, db):
        engine._save_book(sample_publisher, sample_book_info, translate=False)
        book = NewBook.query.first()
        links = book.get_buy_links()
        assert len(links) == 1
        assert links[0]['name'] == 'Amazon'

    def test_appends_to_touched_books(self, engine, sample_publisher, sample_book_info, db):
        touched = []
        engine._save_book(sample_publisher, sample_book_info, translate=False, touched_books=touched)
        assert len(touched) == 1
        assert touched[0].title == 'Test Book'

    def test_no_auto_commit_when_disabled(self, engine, sample_publisher, sample_book_info, db):
        result = engine._save_book(sample_publisher, sample_book_info, translate=False, auto_commit=False)
        assert result == 'added'
        assert NewBook.query.count() == 1


class TestUpdateBookFields:
    """_update_book_fields 字段更新逻辑测试"""

    def test_updates_changed_fields(self, engine, sample_publisher, db):
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
        updated = engine._update_book_fields(book, book_info)
        assert updated is True
        assert book.description == 'new'
        assert book.description_zh is None
        assert book.cover_url == 'https://new.com'
        assert book.price == '20.00'
        assert book.updated_at is not None

    def test_no_update_when_fields_unchanged(self, engine, sample_publisher, db):
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
        updated = engine._update_book_fields(book, book_info)
        assert updated is False

    def test_updates_buy_links(self, engine, sample_publisher, db):
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
        updated = engine._update_book_fields(book, book_info)
        assert updated is True
        assert book.get_buy_links()[0]['name'] == 'B&N'


class TestEnsureStaticDataSeeded:
    """ensure_static_data_seeded 首次种子逻辑测试"""

    def test_skips_when_books_exist(self, engine, sample_publisher, sample_book_info, db):
        engine._save_book(sample_publisher, sample_book_info, translate=False)

        with patch.object(engine, 'seed_from_static_data') as mock_seed:
            result = engine.ensure_static_data_seeded()
        assert result is None
        mock_seed.assert_not_called()

    def test_calls_seed_when_no_books(self, engine, db):
        with patch.object(engine, 'seed_from_static_data', return_value={'added': 5}) as mock_seed:
            result = engine.ensure_static_data_seeded()
        assert result == {'added': 5}
        mock_seed.assert_called_once()
