"""
数据模型测试

测试所有数据模型的创建、查询、关系和数据转换功能
"""
import pytest
from datetime import datetime, timezone

from app.models.database import db
from app.models.schemas import (
    UserPreference,
    UserCategory,
    UserViewedBook,
    BookMetadata,
    SearchHistory,
    Award,
    AwardBook,
    SystemConfig,
    Book
)


# ==================== UserPreference 模型测试 ====================

@pytest.mark.models
class TestUserPreference:
    """测试用户偏好设置模型"""

    def test_create_user_preference(self, db):
        """测试创建用户偏好"""
        preference = UserPreference(
            session_id='test_session_123',
            view_mode='grid'
        )
        db.session.add(preference)
        db.session.commit()

        # 验证创建成功
        result = UserPreference.query.get('test_session_123')
        assert result is not None
        assert result.session_id == 'test_session_123'
        assert result.view_mode == 'grid'

    def test_user_preference_default_values(self, db):
        """测试默认字段值"""
        preference = UserPreference(session_id='test_session_456')
        db.session.add(preference)
        db.session.commit()

        result = UserPreference.query.get('test_session_456')
        assert result.view_mode == 'grid'  # 默认值
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_user_preference_to_dict(self, db):
        """测试转换为字典"""
        preference = UserPreference(
            session_id='test_session_789',
            view_mode='list'
        )
        db.session.add(preference)
        db.session.commit()

        result = UserPreference.query.get('test_session_789')
        data = result.to_dict()

        assert data['session_id'] == 'test_session_789'
        assert data['view_mode'] == 'list'
        assert 'created_at' in data
        assert 'updated_at' in data


# ==================== UserCategory 模型测试 ====================

@pytest.mark.models
class TestUserCategory:
    """测试用户关注分类模型"""

    def test_create_user_category(self, db):
        """测试创建用户分类"""
        # 先创建用户偏好
        preference = UserPreference(session_id='test_session_cat')
        db.session.add(preference)

        category = UserCategory(
            session_id='test_session_cat',
            category_id='hardcover-fiction'
        )
        db.session.add(category)
        db.session.commit()

        result = UserCategory.query.filter_by(
            session_id='test_session_cat',
            category_id='hardcover-fiction'
        ).first()

        assert result is not None
        assert result.category_id == 'hardcover-fiction'

    def test_user_category_relationship(self, db):
        """测试与用户偏好的关系"""
        preference = UserPreference(session_id='test_session_rel')
        db.session.add(preference)
        db.session.commit()

        categories = [
            UserCategory(session_id='test_session_rel', category_id='hardcover-fiction'),
            UserCategory(session_id='test_session_rel', category_id='hardcover-nonfiction'),
        ]
        for cat in categories:
            db.session.add(cat)
        db.session.commit()

        result = UserPreference.query.get('test_session_rel')
        assert result.categories.count() == 2


# ==================== UserViewedBook 模型测试 ====================

@pytest.mark.models
class TestUserViewedBook:
    """测试用户浏览记录模型"""

    def test_create_viewed_book(self, db):
        """测试创建浏览记录"""
        preference = UserPreference(session_id='test_session_view')
        db.session.add(preference)

        viewed = UserViewedBook(
            session_id='test_session_view',
            isbn='9780143127550'
        )
        db.session.add(viewed)
        db.session.commit()

        result = UserViewedBook.query.filter_by(
            session_id='test_session_view',
            isbn='9780143127550'
        ).first()

        assert result is not None
        assert result.viewed_at is not None


# ==================== BookMetadata 模型测试 ====================

@pytest.mark.models
class TestBookMetadata:
    """测试书籍元数据模型"""

    def test_create_book_metadata(self, db):
        """测试创建书籍元数据"""
        metadata = BookMetadata(
            isbn='9780143127550',
            title='Test Book Title',
            author='Test Author',
            details='Book details',
            page_count=320,
            language='en',
            publication_date='2023-10-01'
        )
        db.session.add(metadata)
        db.session.commit()

        result = BookMetadata.query.get('9780143127550')
        assert result is not None
        assert result.title == 'Test Book Title'
        assert result.author == 'Test Author'
        assert result.page_count == 320

    def test_book_metadata_to_dict(self, db):
        """测试转换为字典"""
        metadata = BookMetadata(
            isbn='9780143127551',
            title='Another Book',
            author='Another Author'
        )
        db.session.add(metadata)
        db.session.commit()

        result = BookMetadata.query.get('9780143127551')
        data = result.to_dict()

        assert data['isbn'] == '9780143127551'
        assert data['title'] == 'Another Book'
        assert 'updated_at' in data


# ==================== SearchHistory 模型测试 ====================

@pytest.mark.models
class TestSearchHistory:
    """测试搜索历史模型"""

    def test_create_search_history(self, db):
        """测试创建搜索历史"""
        history = SearchHistory(
            session_id='test_session_search',
            keyword='Python',
            result_count=10
        )
        db.session.add(history)
        db.session.commit()

        result = SearchHistory.query.first()
        assert result is not None
        assert result.keyword == 'Python'
        assert result.result_count == 10


# ==================== Award 模型测试 ====================

@pytest.mark.models
class TestAward:
    """测试奖项模型"""

    def test_create_award(self, db):
        """测试创建奖项"""
        award = Award(
            name='诺贝尔文学奖',
            name_en='Nobel Prize in Literature',
            country='瑞典',
            description='世界著名文学奖项',
            category_count=1,
            established_year=1901,
            award_month=10
        )
        db.session.add(award)
        db.session.commit()

        result = Award.query.filter_by(name='诺贝尔文学奖').first()
        assert result is not None
        assert result.name_en == 'Nobel Prize in Literature'
        assert result.country == '瑞典'

    def test_award_to_dict(self, db):
        """测试转换为字典"""
        award = Award(
            name='测试奖项',
            name_en='Test Award',
            country='中国'
        )
        db.session.add(award)
        db.session.commit()

        result = Award.query.filter_by(name='测试奖项').first()
        data = result.to_dict()

        assert data['name'] == '测试奖项'
        assert data['name_en'] == 'Test Award'


# ==================== AwardBook 模型测试 ====================

@pytest.mark.models
class TestAwardBook:
    """测试获奖图书模型"""

    def test_create_award_book(self, db):
        """测试创建获奖图书"""
        # 先创建奖项
        award = Award(
            name='测试奖',
            name_en='Test Award',
            country='US'
        )
        db.session.add(award)
        db.session.commit()

        book = AwardBook(
            award_id=award.id,
            year=2024,
            category='小说',
            rank=1,
            title='获奖图书',
            author='作者A',
            isbn13='9780143127550',
            verification_status='pending'
        )
        db.session.add(book)
        db.session.commit()

        result = AwardBook.query.filter_by(title='获奖图书').first()
        assert result is not None
        assert result.year == 2024


# ==================== SystemConfig 模型测试 ====================

@pytest.mark.models
class TestSystemConfig:
    """测试系统配置模型"""

    def test_create_system_config(self, db):
        """测试创建系统配置"""
        config = SystemConfig(
            key='site_name',
            value='BookRank',
            description='网站名称'
        )
        db.session.add(config)
        db.session.commit()

        result = SystemConfig.query.get('site_name')
        assert result is not None
        assert result.value == 'BookRank'

    def test_get_value(self, db):
        """测试获取配置值"""
        config = SystemConfig(
            key='max_results',
            value='50'
        )
        db.session.add(config)
        db.session.commit()

        # 测试获取存在的配置
        value = SystemConfig.get_value('max_results')
        assert value == '50'

        # 测试获取不存在的配置，使用默认值
        value = SystemConfig.get_value('nonexistent', 'default')
        assert value == 'default'


# ==================== Book 数据类测试 ====================

@pytest.mark.models
class TestBook:
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
            price='28.00',
            description_zh='中文描述'
        )

        data = book.to_dict()

        assert data['title'] == 'Test Book'
        assert data['description_zh'] == '中文描述'

    def test_book_from_api_response(self):
        """测试从 API 响应创建 Book"""
        book_data = {
            'primary_isbn13': '9780143127550',
            'primary_isbn10': '014312755X',
            'title': 'API Test Book',
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
        assert book.title == 'API Test Book'
        assert book.rank == 5
        assert book.page_count == '300'

    def test_book_price_handling_zero(self):
        """测试价格处理 - 零价格"""
        book_data = {
            'primary_isbn13': '9780143127550',
            'title': 'Book',
            'author': 'Author',
            'publisher': 'Publisher',
            'rank': 1,
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
