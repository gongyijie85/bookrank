"""新书查询模块测试

由 tests/test_new_book_service.py 拆分而来（门面坍塌重构）：
针对 NewBookQueryService 的列表、搜索、详情、分类与统计查询。
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.new_book.query_service import NewBookQueryService


@pytest.fixture
def query_service():
    """创建查询模块实例：翻译管道用 mock 隔离（查询路径只做语言包补齐）"""
    return NewBookQueryService(MagicMock())


def _seed_publisher(db) -> Publisher:
    pm = __import__('app.services.new_book.publisher_manager', fromlist=['PublisherManager'])
    pm.PublisherManager().init_publishers()
    publisher = Publisher.query.first()
    assert publisher is not None
    return publisher


class TestNewBookQueryService:
    def test_get_new_books(self, query_service, db):
        """测试获取新书列表"""
        publisher = _seed_publisher(db)
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

        books, total = query_service.get_new_books(days=30)

        assert total >= 1
        assert len(books) >= 1

    def test_get_new_books_filters_by_publication_date(self, query_service, db):
        """新书时间范围应按出版日期过滤，而不是按同步入库时间过滤"""
        publisher = _seed_publisher(db)

        today = datetime.now(UTC).date()
        now = datetime.now(UTC)
        rows = [
            NewBook(
                publisher_id=publisher.id,
                title='Recent Publication',
                author='Author',
                isbn13='9780000000101',
                category='Fiction',
                publication_date=today - timedelta(days=5),
                created_at=now - timedelta(days=120),
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='Old Publication Synced Today',
                author='Author',
                isbn13='9780000000102',
                category='Fiction',
                publication_date=today - timedelta(days=120),
                created_at=now,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='Future Publication',
                author='Author',
                isbn13='9780000000103',
                category='Fiction',
                publication_date=today + timedelta(days=30),
                created_at=now,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='No Date Recent Sync',
                author='Author',
                isbn13='9780000000104',
                category='Fiction',
                publication_date=None,
                created_at=now,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='No Date Recently Discovered',
                author='Author',
                isbn13='9780000000105',
                category='Fiction',
                publication_date=None,
                created_at=now - timedelta(days=5),
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='No Date Outside Window',
                author='Author',
                isbn13='9780000000106',
                category='Fiction',
                publication_date=None,
                created_at=now - timedelta(days=31),
                is_displayable=True,
            ),
        ]
        db.session.add_all(rows)
        db.session.commit()

        books, total = query_service.get_new_books(days=30)

        titles = {book.title for book in books}
        assert total == 3
        assert titles == {'Recent Publication', 'No Date Recent Sync', 'No Date Recently Discovered'}

        no_date_book = next(book for book in books if book.title == 'No Date Recently Discovered')
        assert no_date_book.publication_date is None
        assert no_date_book.created_at.date() == (today - timedelta(days=5))

    def test_search_books_honors_publication_window(self, query_service, db):
        """搜索也应遵守当前新书出版时间范围"""
        publisher = _seed_publisher(db)

        today = datetime.now(UTC).date()
        db.session.add_all(
            [
                NewBook(
                    publisher_id=publisher.id,
                    title='Window Match',
                    author='Author',
                    isbn13='9780000000111',
                    publication_date=today - timedelta(days=3),
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Window Match Old',
                    author='Author',
                    isbn13='9780000000112',
                    publication_date=today - timedelta(days=80),
                    is_displayable=True,
                ),
            ]
        )
        db.session.commit()

        books, total = query_service.search_books('Window Match', days=30)

        assert total == 1
        assert books[0].title == 'Window Match'

    def test_get_book(self, query_service, db):
        """测试获取单本书籍详情"""
        publisher = _seed_publisher(db)
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

        result = query_service.get_book(test_book.id)

        assert result is not None
        assert result.id == test_book.id
        assert result.title == 'Test Book'

    def test_search_books(self, query_service, db):
        """测试搜索书籍"""
        publisher = _seed_publisher(db)
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

        books, total = query_service.search_books('Test')

        assert total >= 1
        assert len(books) >= 1

    def test_get_categories(self, query_service, db):
        """测试获取所有分类"""
        publisher = _seed_publisher(db)
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

        categories = query_service.get_categories()

        assert len(categories) >= 1
        assert any(cat['name'] == 'Fiction' for cat in categories)

    def test_get_statistics(self, query_service, db):
        """测试获取统计数据"""
        _seed_publisher(db)

        stats = query_service.get_statistics()

        assert isinstance(stats, dict)
        assert 'total_books' in stats
        assert 'total_publishers' in stats
        assert 'active_publishers' in stats
        assert 'recent_books_7d' in stats
        assert 'top_categories' in stats
