"""
图书服务测试

测试 BookService 的核心功能，包括获取图书列表、搜索图书、保存翻译等
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.book_service import BookService
from app.models.schemas import Book, BookMetadata


class TestBookService:
    """图书服务测试类"""
    
    @pytest.fixture
    def book_service(self):
        """创建图书服务实例"""
        # 模拟依赖服务
        nyt_client = Mock()
        google_client = Mock()
        cache_service = Mock()
        image_cache = Mock()
        
        # 配置模拟对象
        nyt_client.fetch_books.return_value = {
            'results': {
                'list_name': 'Hardcover Fiction',
                'published_date': '2024-01-14',
                'books': [
                    {
                        'primary_isbn13': '9780143127550',
                        'primary_isbn10': '014312755X',
                        'rank': 1,
                        'title': 'Test Book Title',
                        'author': 'Test Author',
                        'description': 'A compelling story.',
                        'book_image': 'https://example.com/image.jpg',
                        'publisher': 'Test Publisher',
                        'weeks_on_list': 10,
                        'rank_last_week': '2',
                        'price': '28.00',
                        'buy_links': [
                            {
                                'name': 'Amazon',
                                'url': 'https://amazon.com'
                            }
                        ]
                    }
                ]
            }
        }
        
        google_client.fetch_book_details.return_value = {
            'isbn_13': '9780143127550',
            'isbn_10': '014312755X',
            'title': 'Test Book Title',
            'author': 'Test Author',
            'publisher': 'Test Publisher',
            'publication_dt': '2023-10-01',
            'page_count': 320,
            'language': 'eng',
            'details': 'Detailed book description from Google Books.',
            'cover_url': 'https://example.com/cover.jpg'
        }
        
        cache_service.get.return_value = None
        cache_service.set.return_value = True
        cache_service.get_cache_time.return_value = '2024-01-14 12:00:00'
        
        image_cache.get_cached_image_url.return_value = 'https://example.com/cached_image.jpg'
        
        # 创建图书服务实例
        return BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            categories={'hardcover-fiction': '精装小说'}
        )
    
    def test_get_books_by_category(self, book_service, db):
        """测试获取指定分类的图书列表"""
        # 执行测试
        books = book_service.get_books_by_category('hardcover-fiction')
        
        # 验证结果
        assert len(books) == 1
        assert isinstance(books[0], Book)
        assert books[0].title == 'Test Book Title'
        assert books[0].author == 'Test Author'
        assert books[0].isbn13 == '9780143127550'
        assert books[0].category_id == 'hardcover-fiction'
    
    def test_get_books_by_category_with_cache(self, book_service):
        """测试从缓存获取图书列表"""
        # 模拟缓存数据
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99'
            }
        ]
        book_service._cache.get.return_value = cached_books
        
        # 执行测试
        books = book_service.get_books_by_category('hardcover-fiction')
        
        # 验证结果
        assert len(books) == 1
        assert books[0].title == 'Cached Book'
        assert books[0].author == 'Cached Author'
    
    def test_save_book_translation(self, book_service, db):
        """测试保存图书翻译"""
        # 执行测试
        result = book_service.save_book_translation(
            isbn='9780143127550',
            title_zh='测试书名',
            description_zh='测试描述',
            details_zh='测试详情'
        )
        
        # 验证结果
        assert result is True
        
        # 验证数据库中是否保存了翻译
        metadata = BookMetadata.query.get('9780143127550')
        assert metadata is not None
        assert metadata.title_zh == '测试书名'
        assert metadata.description_zh == '测试描述'
        assert metadata.details_zh == '测试详情'
    
    def test_save_book_translation_invalid_isbn(self, book_service):
        """测试保存图书翻译时ISBN无效的情况"""
        # 执行测试
        result = book_service.save_book_translation(
            isbn='',
            title_zh='测试书名'
        )
        
        # 验证结果
        assert result is False
    
    def test_search_books(self, book_service):
        """测试搜索图书"""
        # 执行测试
        with patch.object(book_service, 'get_books_by_category') as mock_get_books:
            # 模拟返回的图书数据
            mock_book = Mock()
            mock_book.title = 'Test Book Title'
            mock_book.author = 'Test Author'
            mock_get_books.return_value = [mock_book]
            
            # 执行搜索
            results = book_service.search_books('Test')
            
            # 验证结果
            assert len(results) == 1
    
    def test_search_books_no_results(self, book_service):
        """测试搜索图书无结果的情况"""
        # 执行测试
        with patch.object(book_service, 'get_books_by_category') as mock_get_books:
            # 模拟返回的图书数据
            mock_book = Mock()
            mock_book.title = 'Other Book Title'
            mock_book.author = 'Other Author'
            mock_get_books.return_value = [mock_book]
            
            # 执行搜索
            results = book_service.search_books('Test')
            
            # 验证结果
            assert len(results) == 0
    
    def test_get_latest_cache_time(self, book_service):
        """测试获取最新缓存时间"""
        # 执行测试
        cache_time = book_service.get_latest_cache_time()
        
        # 验证结果
        assert cache_time == '2024-01-14 12:00:00'
    
    def test_get_latest_cache_time_no_data(self, book_service):
        """测试获取最新缓存时间时无数据的情况"""
        # 模拟缓存时间为None
        book_service._cache.get_cache_time.return_value = None
        
        # 执行测试
        cache_time = book_service.get_latest_cache_time()
        
        # 验证结果
        assert cache_time == '暂无数据'