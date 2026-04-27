"""
服务层测试

测试业务逻辑服务的功能
"""
import pytest
from unittest.mock import patch, MagicMock

from app.models.schemas import Book
from app.utils.exceptions import APIRateLimitException, APIException, ValidationException


# ==================== Book 数据类测试 ====================

@pytest.mark.services
class TestBookDataClass:
    """测试 Book 数据类"""

    def test_create_book(self):
        """测试创建 Book 对象"""
        book = Book(
            id='9780143127550',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            cover='https://example.com/cover.jpg',
            list_name='Hardcover Fiction',
            category_id='hardcover-fiction',
            category_name='精装小说',
            rank=1,
            weeks_on_list=10,
            rank_last_week='2',
            published_date='2024-01-14',
            description='Description',
            details='Details',
            publication_dt='2023-10-01',
            page_count='320',
            language='en',
            buy_links=[],
            isbn13='9780143127550',
            isbn10='014312755X',
            price='28.00'
        )

        assert book.id == '9780143127550'
        assert book.title == 'Test Book'
        assert book.rank == 1

    def test_book_to_dict(self):
        """测试 Book 转换为字典"""
        book = Book(
            id='9780143127550',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            cover='',
            list_name='Hardcover Fiction',
            category_id='hardcover-fiction',
            category_name='精装小说',
            rank=1,
            weeks_on_list=10,
            rank_last_week='2',
            published_date='2024-01-14',
            description='Description',
            details='Details',
            publication_dt='2023-10-01',
            page_count='320',
            language='en',
            buy_links=[],
            isbn13='9780143127550',
            isbn10='014312755X',
            price='28.00',
            description_zh='中文描述'
        )

        data = book.to_dict()

        assert data['title'] == 'Test Book'
        assert data['description_zh'] == '中文描述'
        assert data['isbn13'] == '9780143127550'

    def test_book_from_api_response(self):
        """测试从 API 响应创建 Book"""
        book_data = {
            'primary_isbn13': '9780143127550',
            'primary_isbn10': '014312755X',
            'title': 'API Book',
            'author': 'API Author',
            'publisher': 'API Publisher',
            'rank': 5,
            'weeks_on_list': 3,
            'rank_last_week': '8',
            'description': 'Book description',
            'price': '25.99',
            'buy_links': [
                {'name': 'Amazon', 'url': 'https://amazon.com'}
            ]
        }

        supplement = {
            'details': 'Detailed description',
            'publication_dt': '2023-10-01',
            'page_count': 300,
            'language': 'eng'
        }

        book = Book.from_api_response(
            book_data=book_data,
            category_id='hardcover-fiction',
            category_name='精装小说',
            list_name='Hardcover Fiction',
            published_date='2024-01-14',
            supplement=supplement
        )

        assert book.id == '9780143127550'
        assert book.title == 'API Book'
        assert book.author == 'API Author'
        assert book.rank == 5
        assert book.page_count == '300'
        assert book.language == 'eng'
        assert len(book.buy_links) == 1

    def test_book_price_handling_valid(self):
        """测试价格处理 - 有效价格"""
        book_data = {
            'primary_isbn13': '9780143127550',
            'title': 'Book 1',
            'author': 'Author',
            'publisher': 'Publisher',
            'rank': 1,
            'weeks_on_list': 1,
            'rank_last_week': '',
            'description': '',
            'price': '25.99',
            'buy_links': []
        }

        book = Book.from_api_response(
            book_data, 'fiction', '小说', 'List', '2024-01-01', {}
        )

        assert book.price == '25.99'

    def test_book_price_handling_zero(self):
        """测试价格处理 - 零价格"""
        book_data = {
            'primary_isbn13': '9780143127550',
            'title': 'Book 2',
            'author': 'Author',
            'publisher': 'Publisher',
            'rank': 2,
            'weeks_on_list': 1,
            'rank_last_week': '',
            'description': '',
            'price': '0',
            'buy_links': []
        }

        book = Book.from_api_response(
            book_data, 'fiction', '小说', 'List', '2024-01-01', {}
        )

        assert book.price == '未知'

    def test_book_price_handling_none(self):
        """测试价格处理 - 空价格"""
        book_data = {
            'primary_isbn13': '9780143127550',
            'title': 'Book 3',
            'author': 'Author',
            'publisher': 'Publisher',
            'rank': 3,
            'weeks_on_list': 1,
            'rank_last_week': '',
            'description': '',
            'price': None,
            'buy_links': []
        }

        book = Book.from_api_response(
            book_data, 'fiction', '小说', 'List', '2024-01-01', {}
        )

        assert book.price == '未知'


# ==================== 异常类测试 ====================

@pytest.mark.services
class TestExceptions:
    """测试异常类"""

    def test_api_exception(self):
        """测试 API 异常"""
        exc = APIException('Test error', status_code=500)

        assert str(exc) == 'Test error'
        assert exc.status_code == 500

    def test_api_rate_limit_exception(self):
        """测试限流异常"""
        exc = APIRateLimitException('Rate limited', retry_after=60)

        assert str(exc) == 'Rate limited'
        assert exc.retry_after == 60

    def test_validation_exception(self):
        """测试验证异常"""
        exc = ValidationException('Invalid input')

        assert str(exc) == 'Invalid input'


# ==================== 工具函数测试 ====================

@pytest.mark.services
class TestUtilities:
    """测试工具函数"""

    def test_rate_limiter(self):
        """测试限流器"""
        from app.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(max_calls=5, window_seconds=60)

        # 允许的请求
        for i in range(5):
            assert limiter.is_allowed() is True

        # 超出限制
        assert limiter.is_allowed() is False

    def test_secure_filename(self):
        """测试安全文件名"""
        from app.utils.security import sanitize_filename

        # 测试正常文件名
        assert sanitize_filename('normal_file.txt') == 'normal_file.txt'

        # 测试危险文件名 - 应该被清理
        result = sanitize_filename('../../etc/passwd')
        assert '..' not in result or result == 'etc_passwd'
