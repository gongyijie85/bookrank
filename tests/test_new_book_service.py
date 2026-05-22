"""
新书服务测试

测试 NewBookService 的核心功能，包括出版社管理、爬虫管理、书籍管理等
"""

import json
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.new_book_service import NewBookService


class TestNewBookService:
    """新书服务测试类"""

    @pytest.fixture(autouse=True)
    def reset_service_singleton(self):
        NewBookService.reset_instance()
        yield
        NewBookService.reset_instance()

    @pytest.fixture
    def new_book_service(self):
        """创建新书服务实例"""
        # 模拟翻译服务
        mock_translator = Mock()
        mock_translator.translate.return_value = '测试翻译结果'

        # 创建新书服务实例
        service = NewBookService(translation_service=mock_translator)
        return service

    def test_init_publishers(self, new_book_service, db):
        """测试初始化默认出版社"""
        # 执行测试
        count = new_book_service.init_publishers()

        # 验证结果
        assert count > 0
        assert Publisher.query.count() >= count

    def test_seed_from_static_data(self, new_book_service, db, tmp_path):
        """测试从静态新书 JSON 兜底导入"""
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

        result = new_book_service.seed_from_static_data(tmp_path)

        assert result['added'] == 1
        assert NewBook.query.count() == 1
        book = NewBook.query.first()
        assert book.title == 'Static Test Book'
        assert book.publisher.name_en == 'Google Books'
        assert book.publication_date.isoformat() == '2026-05-01'
        assert book.get_buy_links()[0]['name'] == 'Google Books'

        assert new_book_service.ensure_static_data_seeded() is None

    def test_get_publishers(self, new_book_service, db):
        """测试获取出版社列表"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 执行测试
        publishers = new_book_service.get_publishers(active_only=True)

        # 验证结果
        assert len(publishers) > 0
        for publisher in publishers:
            assert publisher.is_active is True

    def test_get_publisher(self, new_book_service, db):
        """测试获取单个出版社"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 获取第一个出版社
        publisher = Publisher.query.first()
        assert publisher is not None

        # 执行测试
        result = new_book_service.get_publisher(publisher.id)

        # 验证结果
        assert result is not None
        assert result.id == publisher.id

    def test_update_publisher_status(self, new_book_service, db):
        """测试更新出版社状态"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 获取第一个出版社
        publisher = Publisher.query.first()
        assert publisher is not None

        # 执行测试 - 禁用出版社
        result = new_book_service.update_publisher_status(publisher.id, False)

        # 验证结果
        assert result is True
        assert Publisher.query.get(publisher.id).is_active is False

        # 执行测试 - 启用出版社
        result = new_book_service.update_publisher_status(publisher.id, True)

        # 验证结果
        assert result is True
        assert Publisher.query.get(publisher.id).is_active is True

    def test_get_crawler(self, new_book_service):
        """测试获取爬虫实例"""
        # 执行测试 - 测试不存在的爬虫类
        crawler = new_book_service.get_crawler('NonExistentCrawler')
        assert crawler is None

    def test_get_new_books(self, new_book_service, db):
        """测试获取新书列表"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 创建测试数据
        publisher = Publisher.query.first()
        if publisher:
            # 创建测试书籍
            test_book = NewBook(
                publisher_id=publisher.id,
                title='Test Book',
                author='Test Author',
                isbn13='9780000000001',
                isbn10='0000000001',
                description='Test description',
                cover_url='https://example.com/cover.jpg',
                category='Fiction',
                publication_date=datetime.now(UTC),
                is_displayable=True,
            )
            db.session.add(test_book)
            db.session.commit()

            # 执行测试
            books, total = new_book_service.get_new_books(days=30)

            # 验证结果
            assert total >= 1
            assert len(books) >= 1

    def test_get_book(self, new_book_service, db):
        """测试获取单本书籍详情"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 创建测试数据
        publisher = Publisher.query.first()
        if publisher:
            # 创建测试书籍
            test_book = NewBook(
                publisher_id=publisher.id,
                title='Test Book',
                author='Test Author',
                isbn13='9780000000001',
                isbn10='0000000001',
                description='Test description',
                cover_url='https://example.com/cover.jpg',
                category='Fiction',
                publication_date=datetime.now(UTC),
                is_displayable=True,
            )
            db.session.add(test_book)
            db.session.commit()

            # 执行测试
            result = new_book_service.get_book(test_book.id)

            # 验证结果
            assert result is not None
            assert result.id == test_book.id
            assert result.title == 'Test Book'

    def test_search_books(self, new_book_service, db):
        """测试搜索书籍"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 创建测试数据
        publisher = Publisher.query.first()
        if publisher:
            # 创建测试书籍
            test_book = NewBook(
                publisher_id=publisher.id,
                title='Test Book',
                author='Test Author',
                isbn13='9780000000001',
                isbn10='0000000001',
                description='Test description',
                cover_url='https://example.com/cover.jpg',
                category='Fiction',
                publication_date=datetime.now(UTC),
                is_displayable=True,
            )
            db.session.add(test_book)
            db.session.commit()

            # 执行测试
            books, total = new_book_service.search_books('Test')

            # 验证结果
            assert total >= 1
            assert len(books) >= 1

    def test_get_categories(self, new_book_service, db):
        """测试获取所有分类"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 创建测试数据
        publisher = Publisher.query.first()
        if publisher:
            # 创建测试书籍
            test_book = NewBook(
                publisher_id=publisher.id,
                title='Test Book',
                author='Test Author',
                isbn13='9780000000001',
                isbn10='0000000001',
                description='Test description',
                cover_url='https://example.com/cover.jpg',
                category='Fiction',
                publication_date=datetime.now(UTC),
                is_displayable=True,
            )
            db.session.add(test_book)
            db.session.commit()

            # 执行测试
            categories = new_book_service.get_categories()

            # 验证结果
            assert len(categories) >= 1
            assert any(cat['name'] == 'Fiction' for cat in categories)

    def test_get_statistics(self, new_book_service, db):
        """测试获取统计数据"""
        # 先初始化出版社
        new_book_service.init_publishers()

        # 执行测试
        stats = new_book_service.get_statistics()

        # 验证结果
        assert isinstance(stats, dict)
        assert 'total_books' in stats
        assert 'total_publishers' in stats
        assert 'active_publishers' in stats
        assert 'recent_books_7d' in stats
        assert 'top_categories' in stats

    def test_sync_publisher_books_invalid_publisher(self, new_book_service, db):
        """测试同步无效出版社的书籍"""
        result = new_book_service.sync_publisher_books(999999)

        assert result['success'] is False
        assert 'error' in result

    def test_sync_all_publishers(self, new_book_service, db):
        """测试同步所有出版社的书籍"""
        new_book_service.init_publishers()

        mock_crawler = Mock()
        mock_crawler.__enter__ = Mock(return_value=mock_crawler)
        mock_crawler.__exit__ = Mock(return_value=None)

        mock_book_info = Mock()
        mock_book_info.title = 'Test Book'
        mock_book_info.author = 'Test Author'
        mock_book_info.isbn13 = '9780000000001'
        mock_book_info.isbn10 = '0000000001'
        mock_book_info.description = 'Test description'
        mock_book_info.cover_url = 'https://example.com/cover.jpg'
        mock_book_info.category = 'Fiction'
        mock_book_info.publication_date = datetime.now(UTC)
        mock_book_info.price = '29.99'
        mock_book_info.page_count = 300
        mock_book_info.language = 'en'
        mock_book_info.source_url = 'https://example.com/book'
        mock_book_info.buy_links = []

        mock_crawler.get_new_books.return_value = [mock_book_info]

        mock_crawler_cls = Mock()
        mock_crawler_cls.return_value = mock_crawler

        with patch('app.services.publisher_crawler.get_crawler_class', side_effect=lambda name: mock_crawler_cls):
            results = new_book_service.sync_all_publishers(max_books_per_publisher=1)

            assert isinstance(results, list)
            assert len(results) > 0

    def test_sync_publisher_books_writes_language_pack(self, db, tmp_path):
        """测试同步新书时会把翻译写入语言包"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        mock_translator = Mock()

        def translate(text, source_lang='en', target_lang='zh', field_type='text'):
            return {'title': '测试新书名', 'description': '测试新书简介'}[field_type]

        mock_translator.translate.side_effect = translate
        service = NewBookService(translation_service=mock_translator, language_pack_path=pack_path)
        service.init_publishers()

        publisher = Publisher.query.first()
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

        mock_crawler.get_new_books.return_value = [mock_book_info]
        mock_crawler_cls = Mock(return_value=mock_crawler)

        with patch('app.services.publisher_crawler.get_crawler_class', side_effect=lambda name: mock_crawler_cls):
            result = service.sync_publisher_books(publisher.id, max_books=1)

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert result['success'] is True
        assert result['language_pack']['pack_writes'] == 1
        assert saved['books']['9780000000002']['title_zh'] == '测试新书名'
        assert saved['books']['9780000000002']['description_zh'] == '测试新书简介'
