"""
奖项API集成测试

测试奖项相关API端点的核心功能，包括获取奖项列表、获奖图书、搜索、分页等
"""

import pytest

from app import create_app
from app.models.database import db as _db
from app.models.schemas import Award, AwardBook


@pytest.fixture(scope='module')
def app():
    """创建测试应用实例并初始化数据库"""
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        _seed_test_data()
        yield app
        _db.session.remove()
        _db.drop_all()


def _seed_test_data():
    """插入测试数据：一个奖项和两本获奖图书"""
    award = Award(name='Test Award', description='A test award', country='US')
    _db.session.add(award)
    _db.session.commit()

    book1 = AwardBook(
        award_id=award.id,
        title='Test Book 1',
        author='Author One',
        year=2024,
        rank=1,
        category='Fiction',
        isbn13='9780143127550',
    )
    book2 = AwardBook(
        award_id=award.id,
        title='Test Book 2',
        author='Author Two',
        year=2023,
        rank=2,
        category='Fiction',
        isbn13='9780062796200',
    )
    _db.session.add_all([book1, book2])
    _db.session.commit()


@pytest.fixture(scope='module')
def client(app):
    """创建测试客户端"""
    return app.test_client()


class TestAwardsAPI:
    """奖项API测试类"""

    def test_get_awards(self, client):
        """测试获取所有奖项列表"""
        response = client.get('/api/awards')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert len(data['data']['awards']) >= 1

    def test_get_award_books(self, client, app):
        """测试获取指定奖项的图书列表"""
        with app.app_context():
            award = Award.query.first()
            response = client.get(f'/api/awards/{award.id}/books')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'books' in data['data']

    def test_get_award_books_not_found(self, client):
        """测试获取不存在奖项的图书列表"""
        response = client.get('/api/awards/99999/books')
        assert response.status_code == 404

    def test_get_all_award_books(self, client):
        """测试获取所有获奖图书"""
        response = client.get('/api/award-books')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'books' in data['data']

    def test_get_all_award_books_with_year_filter(self, client):
        """测试按年份筛选获奖图书"""
        response = client.get('/api/award-books?year=2024')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_get_all_award_books_invalid_year(self, client):
        """测试使用无效年份筛选获奖图书"""
        response = client.get('/api/award-books?year=1800')
        assert response.status_code == 400

    def test_get_award_book_detail(self, client, app):
        """测试获取获奖图书详情"""
        with app.app_context():
            book = AwardBook.query.first()
            response = client.get(f'/api/award-books/{book.id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'book' in data['data']

    def test_get_award_book_detail_not_found(self, client):
        """测试获取不存在图书的详情"""
        response = client.get('/api/award-books/99999')
        assert response.status_code == 404

    def test_search_award_books(self, client):
        """测试搜索获奖图书"""
        response = client.get('/api/award-books/search?keyword=Test')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'books' in data['data']

    def test_search_award_books_empty_keyword(self, client):
        """测试搜索获奖图书时空关键词"""
        response = client.get('/api/award-books/search?keyword=')
        assert response.status_code == 400

    def test_search_award_books_keyword_too_long(self, client):
        """测试搜索获奖图书时关键词过长"""
        response = client.get(f'/api/award-books/search?keyword={"x" * 101}')
        assert response.status_code == 400


class TestAwardsPagination:
    """奖项分页测试类"""

    def test_pagination_params(self, client):
        """测试自定义分页参数"""
        response = client.get('/api/award-books?page=1&limit=1')
        assert response.status_code == 200
        data = response.get_json()
        assert 'pagination' in data['data']
        assert data['data']['pagination']['limit'] == 1

    def test_pagination_default(self, client):
        """测试默认分页参数"""
        response = client.get('/api/award-books')
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['pagination']['page'] == 1
        assert data['data']['pagination']['limit'] == 20
