"""
SyncEngine 单元测试

测试核心同步流程：出版社同步、批量同步、书籍保存、
去重逻辑、错误处理和状态追踪，所有外部依赖通过 mock 隔离。
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.new_book.ingestor import SaveOutcome
from app.services.new_book.sync_engine import SyncEngine
from app.services.publisher_crawler.base_crawler import BookInfo, CrawlOutcome


@pytest.fixture
def publisher_manager():
    return MagicMock()


@pytest.fixture
def translation_pipeline():
    pipeline = MagicMock()
    pipeline._translator = MagicMock()
    pipeline.translate_book.return_value = False
    pipeline.persist_language_pack.return_value = {}
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


def _make_crawler_mock(books=(), stats=None):
    """构造符合新接口形状的爬虫 mock：get_new_books 返回 CrawlOutcome。"""
    mock_crawler = MagicMock()
    mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter(books), date_filter_stats=stats)
    mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
    mock_crawler.__exit__ = MagicMock(return_value=False)
    return mock_crawler


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
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([]), date_filter_stats=None)
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id)

        assert result['success'] is False
        assert result['status'] == 'empty'
        assert result['transport_status'] == 'success'
        assert result['parse_status'] == 'empty'
        assert result['total'] == 0
        assert result['added'] == 0
        assert sample_publisher.sync_count == 0
        assert sample_publisher.last_sync_at is None

    def test_sync_adds_new_books(self, engine, publisher_manager, sample_publisher, sample_book_info, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([sample_book_info]), date_filter_stats=None)
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

    def test_date_filter_stats_flow_into_result(
        self, engine, publisher_manager, sample_publisher, sample_book_info, db
    ):
        """工单 #83：Google Books 系爬虫的日期过滤拒绝计数随单家同步结果字典流出"""
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = _make_crawler_mock(
            [sample_book_info],
            stats={
                'traversed_total': 6,
                'rejected_no_date': 2,
                'rejected_unparseable': 1,
                'rejected_out_of_window': 1,
                'rejected_future_placeholder': 1,
                'accepted_year_only': 1,
            },
        )

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['success'] is True
        assert result['traversed_total'] == 6
        assert result['rejected_no_date'] == 2
        assert result['rejected_unparseable'] == 1
        assert result['rejected_out_of_window'] == 1
        assert result['accepted_year_only'] == 1

    def test_crawler_without_real_stats_does_not_pollute_result(
        self, engine, publisher_manager, sample_publisher, sample_book_info, db
    ):
        """非 Google 系适配器的抓取结果不带统计（date_filter_stats=None）时，
        结果字典不应被污染"""
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()  # CrawlOutcome 未带统计时返回 None
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([sample_book_info]), date_filter_stats=None)
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['success'] is True
        assert 'traversed_total' not in result
        assert 'rejected_no_date' not in result

    def test_sync_skips_duplicate_by_isbn13(self, engine, publisher_manager, sample_publisher, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            description='A test book description',
            cover_url='https://example.com/cover.jpg',
            category='小说',  # 已映射的中文分类
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
            category='Fiction',  # 爬虫返回英文分类，会被映射为'小说'
            publication_date=date(2026, 1, 15),
            price='29.99',
            page_count=300,
            language='en',
            source_url='https://example.com/book',
        )

        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([book_info]), date_filter_stats=None)
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
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([sample_book_info]), date_filter_stats=None)
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

        mock_crawler = _make_crawler_mock(
            [
                BookInfo(title='OK Book', author='Author A'),
                BookInfo(title='Bad Book', author='Author B'),
            ]
        )

        call_count = 0

        def fake_save(publisher, book_info, translate=True, auto_commit=True, touched_books=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError('DB failure')
            return SaveOutcome.ADDED

        with (
            patch.object(engine, 'get_crawler', return_value=mock_crawler),
            patch.object(engine._ingestor, 'save_book', side_effect=fake_save),
        ):
            result = engine.sync_publisher_books(sample_publisher.id)

        assert result['added'] == 1
        assert result['errors'] == 1
        assert result['success'] is False
        assert result['status'] == 'partial_failure'
        assert result['parse_status'] == 'partial'
        assert sample_publisher.sync_count == 0
        assert sample_publisher.last_sync_at is None

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
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter(books), date_filter_stats=None)
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
        mock_crawler.get_new_books.return_value = CrawlOutcome(
            books=iter([BookInfo(title='Successful book', author='Author')]), date_filter_stats=None
        )
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id)

        assert sample_publisher.sync_count == 1
        assert sample_publisher.last_sync_at is not None

    def test_sync_marks_crawler_request_failure_without_success_metadata(
        self, engine, publisher_manager, sample_publisher, db
    ):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)
        mock_crawler.get_new_books.side_effect = RuntimeError('upstream timeout')

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            result = engine.sync_publisher_books(sample_publisher.id, translate=False)

        assert result['success'] is False
        assert result['status'] == 'request_failed'
        assert result['transport_status'] == 'failed'
        assert result['parse_status'] == 'failed'
        assert 'upstream timeout' in result['error']
        assert sample_publisher.sync_count == 0
        assert sample_publisher.last_sync_at is None

    def test_sync_passes_translate_flag(self, engine, publisher_manager, sample_publisher, sample_book_info, db):
        publisher_manager.get_publisher.return_value = sample_publisher

        mock_crawler = MagicMock()
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([sample_book_info]), date_filter_stats=None)
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id, translate=True)

        engine._translation_pipeline.persist_language_pack.assert_called_once()


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
        class MockCrawler:
            API_KEY_CONFIG = None
            api_key_required = False
            REQUEST_DELAY = None

            def __init__(self, config=None):
                self.config = config

        mock_get_cls.return_value = MockCrawler
        result = engine.get_crawler('PenguinCrawler')
        assert result is not None

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_google_crawler_gets_api_key_config(self, mock_get_cls, engine, app_context):
        mock_crawler_cls = MagicMock()
        mock_crawler_cls.API_KEY_CONFIG = 'GOOGLE_API_KEY'
        mock_crawler_cls.api_key_required = False
        mock_crawler_cls.REQUEST_DELAY = None
        mock_get_cls.return_value = mock_crawler_cls
        app_context.config['GOOGLE_API_KEY'] = 'test-google-key'
        engine.get_crawler('GoogleBooksCrawler')
        mock_crawler_cls.assert_called_once()
        call_args = mock_crawler_cls.call_args
        assert call_args[0][0].api_key == 'test-google-key'

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_penguin_random_house_crawler_gets_api_key_config(self, mock_get_cls, engine, app_context):
        mock_crawler_cls = MagicMock()
        mock_crawler_cls.API_KEY_CONFIG = 'GOOGLE_API_KEY'
        mock_crawler_cls.api_key_required = False
        mock_crawler_cls.REQUEST_DELAY = None
        mock_get_cls.return_value = mock_crawler_cls
        app_context.config['GOOGLE_API_KEY'] = 'test-google-key'
        engine.get_crawler('PenguinRandomHouseCrawler')
        mock_crawler_cls.assert_called_once()
        call_args = mock_crawler_cls.call_args
        assert call_args[0][0].api_key == 'test-google-key'

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_google_crawler_without_api_key_uses_default(self, mock_get_cls, app):
        mock_crawler_cls = MagicMock()
        mock_crawler_cls.API_KEY_CONFIG = 'GOOGLE_API_KEY'
        mock_crawler_cls.api_key_required = False
        mock_crawler_cls.REQUEST_DELAY = None
        mock_get_cls.return_value = mock_crawler_cls

        with app.app_context():
            app.config.pop('GOOGLE_API_KEY', None)
            engine = SyncEngine(MagicMock(), MagicMock())
            engine.get_crawler('GoogleBooksCrawler')
        mock_crawler_cls.assert_called_once_with(None)

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_prh_api_crawler_gets_api_key_config(self, mock_get_cls, engine, app_context):
        """PRH_API_KEY 存在时注入配置（工单 #86）"""
        mock_crawler_cls = MagicMock()
        mock_crawler_cls.API_KEY_CONFIG = 'PRH_API_KEY'
        mock_crawler_cls.api_key_required = True
        mock_crawler_cls.REQUEST_DELAY = 0.5
        mock_get_cls.return_value = mock_crawler_cls
        app_context.config['PRH_API_KEY'] = 'test-prh-key'
        engine.get_crawler('PrhApiCrawler')
        mock_crawler_cls.assert_called_once()
        call_args = mock_crawler_cls.call_args
        assert call_args[0][0].api_key == 'test-prh-key'
        assert call_args[0][0].request_delay == 0.5

    @patch('app.services.new_book.sync_engine.get_crawler_class')
    def test_prh_api_crawler_without_api_key_returns_none(self, mock_get_cls, app):
        """PRH_API_KEY 缺失时快速失败返回 None，不实例化爬虫（工单 #86）"""
        mock_crawler_cls = MagicMock()
        mock_crawler_cls.API_KEY_CONFIG = 'PRH_API_KEY'
        mock_crawler_cls.api_key_required = True
        mock_crawler_cls.REQUEST_DELAY = 0.5
        mock_get_cls.return_value = mock_crawler_cls

        with app.app_context():
            app.config.pop('PRH_API_KEY', None)
            engine = SyncEngine(MagicMock(), MagicMock())
            result = engine.get_crawler('PrhApiCrawler')
        assert result is None
        mock_crawler_cls.assert_not_called()


class TestBackfillWindowSelection:
    """窗口模式判定：按出版社存量书数量选回填/增量并传入爬虫（工单 #87）"""

    @staticmethod
    def _backfill_capable_crawler():
        mock_crawler = MagicMock()
        mock_crawler.SUPPORTS_BACKFILL = True
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([]), date_filter_stats=None)
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)
        return mock_crawler

    def test_zero_existing_books_triggers_backfill(self, engine, publisher_manager, sample_publisher, db):
        publisher_manager.get_publisher.return_value = sample_publisher
        mock_crawler = self._backfill_capable_crawler()

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id)

        request = mock_crawler.get_new_books.call_args[0][0]
        assert request.backfill is True

    def test_existing_books_falls_back_to_incremental(self, engine, publisher_manager, sample_publisher, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Existing Book',
            author='Someone',
            description='d',
            cover_url='https://example.com/c.jpg',
        )
        db.session.add(existing)
        db.session.commit()
        publisher_manager.get_publisher.return_value = sample_publisher
        mock_crawler = self._backfill_capable_crawler()

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id)

        request = mock_crawler.get_new_books.call_args[0][0]
        assert request.backfill is False

    def test_crawler_without_backfill_support_gets_backfill_false(
        self, engine, publisher_manager, sample_publisher, db
    ):
        publisher_manager.get_publisher.return_value = sample_publisher
        mock_crawler = MagicMock()
        mock_crawler.SUPPORTS_BACKFILL = False
        mock_crawler.get_new_books.return_value = CrawlOutcome(books=iter([]), date_filter_stats=None)
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id)

        request = mock_crawler.get_new_books.call_args[0][0]
        assert request.backfill is False

    def test_backfill_expands_max_books_cap(self, engine, publisher_manager, sample_publisher, db, monkeypatch):
        """回填模式放大入库上限，否则拉全量也只能入默认额度（工单 #87）"""
        import app.services.new_book.sync_engine as se_mod

        monkeypatch.setattr(se_mod, '_BACKFILL_MAX_BOOKS', 500)
        publisher_manager.get_publisher.return_value = sample_publisher
        mock_crawler = self._backfill_capable_crawler()

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id, max_books=30)

        request = mock_crawler.get_new_books.call_args[0][0]
        assert request.max_books == 500

    def test_incremental_keeps_requested_max_books(self, engine, publisher_manager, sample_publisher, db):
        existing = NewBook(
            publisher_id=sample_publisher.id,
            title='Existing Book',
            author='Someone',
            description='d',
            cover_url='https://example.com/c.jpg',
        )
        db.session.add(existing)
        db.session.commit()
        publisher_manager.get_publisher.return_value = sample_publisher
        mock_crawler = self._backfill_capable_crawler()

        with patch.object(engine, 'get_crawler', return_value=mock_crawler):
            engine.sync_publisher_books(sample_publisher.id, max_books=30)

        request = mock_crawler.get_new_books.call_args[0][0]
        assert request.max_books == 30


class TestEnsureStaticDataSeeded:
    """ensure_static_data_seeded 首次种子逻辑测试"""

    def test_skips_when_books_exist(self, engine, sample_publisher, sample_book_info, db):
        engine._ingestor.save_book(sample_publisher, sample_book_info, translate=False)

        with patch.object(engine, 'seed_from_static_data') as mock_seed:
            result = engine.ensure_static_data_seeded()
        assert result is None
        mock_seed.assert_not_called()

    def test_calls_seed_when_no_books(self, engine, db):
        with patch.object(engine, 'seed_from_static_data', return_value={'added': 5}) as mock_seed:
            result = engine.ensure_static_data_seeded()
        assert result == {'added': 5}
        mock_seed.assert_called_once()


class TestSyncPublisherWithTimeout:
    """单家出版社同步熔断（_sync_publisher_with_timeout）测试"""

    def test_returns_worker_result_on_success(self, engine, sample_publisher, db):
        expected = {'success': True, 'status': 'success', 'added': 3}
        with patch.object(engine, 'sync_publisher_books', return_value=expected):
            result = engine._sync_publisher_with_timeout(sample_publisher, None, 50, False)
        assert result == expected

    def test_times_out_and_returns_timeout_result(self, engine, sample_publisher, db):
        import time as _time

        import app.services.new_book.sync_engine as sync_engine_module

        def slow_sync(*args, **kwargs):
            _time.sleep(2)
            return {'success': True}

        with (
            patch.object(sync_engine_module, '_PER_PUBLISHER_TIMEOUT', 0.2),
            patch.object(engine, 'sync_publisher_books', side_effect=slow_sync),
        ):
            result = engine._sync_publisher_with_timeout(sample_publisher, None, 50, False)

        assert result['success'] is False
        assert result['status'] == 'timeout'
        assert result['publisher'] == sample_publisher.name_en
        assert '超时' in result['error']


class TestSeedFromStaticData:
    """静态兜底导入与 ensure 跳过路径（由门面测试迁移而来）"""

    def test_seed_from_static_data_and_ensure_skips_afterwards(self, db, tmp_path):
        """测试从静态新书 JSON 兜底导入，已有书后 ensure 直接跳过"""
        import json

        from app.services.book_language_pack import BookLanguagePack
        from app.services.new_book.publisher_manager import PublisherManager
        from app.services.new_book.translation_pipeline import TranslationPipeline

        manager = PublisherManager()
        pipeline = TranslationPipeline(None, BookLanguagePack(None))
        engine = SyncEngine(manager, pipeline)

        static_file = tmp_path / 'google_books_books.json'
        static_file.write_text(
            json.dumps(
                [
                    {
                        'title': 'Static Test Book',
                        'author': 'Static Author',
                        'isbn13': '9780000000999',
                        'isbn10': '0000000999',
                        'description': 'Static description',
                        'cover_url': 'https://example.com/static.jpg',
                        'category': 'Fiction',
                        'publication_date': '2026-05-01',
                        'page_count': 240,
                        'language': 'en',
                        'buy_links': [{'name': 'Google Books', 'url': 'https://example.com/book'}],
                        'source_url': 'https://example.com/book',
                    }
                ]
            ),
            encoding='utf-8',
        )

        result = engine.seed_from_static_data(tmp_path)

        assert result['added'] == 1
        assert NewBook.query.count() == 1
        book = NewBook.query.first()
        assert book.title == 'Static Test Book'
        assert book.publisher.name_en == 'Google Books'
        assert book.publication_date.isoformat() == '2026-05-01'
        assert book.get_buy_links()[0]['name'] == 'Google Books'

        assert engine.ensure_static_data_seeded() is None


class TestSyncWritesLanguagePack:
    """同步时把翻译写入语言包（由门面测试迁移而来）"""

    def test_sync_publisher_books_writes_language_pack(self, db, tmp_path):
        """同步新书时会把翻译写入语言包文件"""
        import json
        from datetime import UTC, datetime
        from unittest.mock import Mock, patch

        from app.services.book_language_pack import BookLanguagePack
        from app.services.new_book.publisher_manager import PublisherManager
        from app.services.new_book.translation_pipeline import TranslationPipeline

        pack_path = tmp_path / 'book_language_pack.zh.json'
        mock_translator = Mock()

        def translate(text, source_lang='en', target_lang='zh', field_type='text'):
            return {'title': '测试新书名', 'description': '测试新书简介'}[field_type]

        mock_translator.translate.side_effect = translate
        manager = PublisherManager()
        pipeline = TranslationPipeline(mock_translator, BookLanguagePack(pack_path))
        engine = SyncEngine(manager, pipeline)
        manager.init_publishers()

        # 用启用中的出版社：Google Books/Open Library 默认停用，
        # 用它们会在同步前就因"出版社已禁用"短路返回；
        # 排除 PrhApiCrawler——它要求环境中有 PRH_API_KEY（CI 无 key 时
        # get_crawler 快速失败返回 None，本测试只关心语言包写入）
        publisher = Publisher.query.filter_by(is_active=True).filter(Publisher.crawler_class != 'PrhApiCrawler').first()
        assert publisher is not None

        mock_crawler = Mock()
        mock_crawler.__enter__ = Mock(return_value=mock_crawler)
        mock_crawler.__exit__ = Mock(return_value=None)

        mock_book_info = Mock()
        mock_book_info.title = 'New Test Book'
        mock_book_info.author = 'Test Author'
        mock_book_info.isbn13 = '9780000000002'
        mock_book_info.isbn10 = '0000000002'
        mock_book_info.description = 'New test description'
        mock_book_info.cover_url = 'https://example.com/cover.jpg'
        mock_book_info.category = 'Fiction'
        mock_book_info.publication_date = datetime.now(UTC)
        mock_book_info.price = '29.99'
        mock_book_info.page_count = 300
        mock_book_info.language = 'en'
        mock_book_info.source_url = 'https://example.com/book'
        mock_book_info.buy_links = []

        mock_crawler.get_new_books.return_value = CrawlOutcome(books=[mock_book_info], date_filter_stats=None)
        mock_crawler_cls = Mock(return_value=mock_crawler)
        mock_crawler_cls.API_KEY_CONFIG = None
        mock_crawler_cls.api_key_required = False
        mock_crawler_cls.REQUEST_DELAY = None

        with patch('app.services.new_book.sync_engine.get_crawler_class', side_effect=lambda name: mock_crawler_cls):
            result = engine.sync_publisher_books(publisher.id, max_books=1)

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert result['success'] is True
        assert result['language_pack']['pack_writes'] == 1
        assert saved['books']['9780000000002']['title_zh'] == '测试新书名'
        assert saved['books']['9780000000002']['description_zh'] == '测试新书简介'

    def test_worker_exception_returns_request_failed(self, engine, sample_publisher, db):
        with patch.object(engine, 'sync_publisher_books', side_effect=RuntimeError('boom')):
            result = engine._sync_publisher_with_timeout(sample_publisher, None, 50, False)
        assert result['success'] is False
        assert result['status'] == 'request_failed'
        assert 'boom' in result['error']
