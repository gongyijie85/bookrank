"""
奖项API集成测试

测试奖项相关API端点的核心功能，包括获取奖项列表、获奖图书、搜索、分页等
"""

import pytest

from app.models.schemas import Award, AwardBook


def _seed_test_data(db):
    """插入测试数据：一个奖项和两本获奖图书

    通过参数注入 conftest 的 function-scoped db fixture（每个测试用例独立 db）
    """
    award = Award(name='Test Award', description='A test award', country='US')
    db.session.add(award)
    db.session.commit()

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
    db.session.add_all([book1, book2])
    db.session.commit()


@pytest.fixture
def client_with_award_data(client, db):
    """提供带种子数据的测试客户端（每个用例独立 db）"""
    _seed_test_data(db)
    return client


class TestAwardsAPI:
    """奖项API测试类"""

    def test_get_awards(self, client_with_award_data, app):
        """测试获取所有奖项列表"""
        client = client_with_award_data
        response = client.get('/api/awards')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert len(data['data']['awards']) >= 1

    def test_get_award_books(self, client_with_award_data, app):
        """测试获取指定奖项的图书列表"""
        client = client_with_award_data
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

    def test_get_all_award_books(self, client_with_award_data):
        """测试获取所有获奖图书"""
        client = client_with_award_data
        response = client.get('/api/award-books')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'books' in data['data']

    def test_get_all_award_books_with_year_filter(self, client_with_award_data):
        """测试按年份筛选获奖图书"""
        client = client_with_award_data
        response = client.get('/api/award-books?year=2024')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_get_all_award_books_invalid_year(self, client):
        """测试使用无效年份筛选获奖图书"""
        response = client.get('/api/award-books?year=1800')
        assert response.status_code == 400

    def test_get_award_book_detail(self, client_with_award_data, app):
        """测试获取获奖图书详情"""
        client = client_with_award_data
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

    def test_search_award_books(self, client_with_award_data):
        """测试搜索获奖图书"""
        client = client_with_award_data
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

    def test_pagination_params(self, client_with_award_data):
        """测试自定义分页参数"""
        client = client_with_award_data
        response = client.get('/api/award-books?page=1&limit=1')
        assert response.status_code == 200
        data = response.get_json()
        assert 'pagination' in data['data']
        assert data['data']['pagination']['limit'] == 1

    def test_pagination_default(self, client_with_award_data):
        """测试默认分页参数"""
        client = client_with_award_data
        response = client.get('/api/award-books')
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['pagination']['page'] == 1
        assert data['data']['pagination']['limit'] == 20


class TestAdminAwardFixEndpoints:
    """测试 api/awards.py 中 2 个 admin 端点的鉴权行为

    端点契约：
    - POST /api/admin/fix-award-book-titles
    - POST /api/admin/fix-award-book-titles-by-ids
    鉴权：X-Admin-Secret 头匹配 ADMIN_SECRET（v0.9.61+ 统一协议）
    """

    def test_missing_header_returns_403(self, client, db):
        """不传 X-Admin-Secret 应返回 403"""
        response = client.post(
            '/api/admin/fix-award-book-titles-by-ids',
            json={'items': []},
        )
        assert response.status_code == 403

    def test_wrong_secret_returns_403(self, client, db, admin_headers):
        """错误 secret 应返回 403"""
        headers = {**admin_headers, 'X-Admin-Secret': 'wrong-secret'}
        response = client.post(
            '/api/admin/fix-award-book-titles-by-ids',
            headers=headers,
            json={'items': []},
        )
        assert response.status_code == 403

    def test_valid_secret_succeeds(self, client, db, admin_headers, _seed_award):
        """正确 secret + 合法数据应成功修复"""
        from app.models.schemas import AwardBook

        with client.application.app_context():
            book = AwardBook.query.first()
        response = client.post(
            '/api/admin/fix-award-book-titles-by-ids',
            headers=admin_headers,
            json={'items': [{'id': book.id, 'title_zh': '测试书名'}]},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['fixed_count'] >= 1

    def test_empty_items_returns_400(self, client, db, admin_headers):
        """items=[] 应返回 400"""
        response = client.post(
            '/api/admin/fix-award-book-titles-by-ids',
            headers=admin_headers,
            json={'items': []},
        )
        assert response.status_code == 400

    def test_429_after_5_failures(self, client, db, admin_headers, clear_auth_failures):
        """5 次错误 secret 后第 6 次应返回 429

        ⚠️ 重要：admin_auth.py:114-115 在达到 _AUTH_MAX_FAILURES (5) 时
        会 _auth_failures.pop(client_ip, None) 清空 state 并设置封禁。
        所以循环 5 次后第 6 次才会拿到 429。

        🔧 mock 仅为避免在测试数据库上持久化 SystemConfig（与本测试契约无关），
        不掩盖任何鉴权行为（401/403/限流阈值/封禁状态均真实执行）。
        """
        from unittest.mock import patch

        wrong_headers = {'X-Admin-Secret': 'wrong'}
        with patch('app.utils.admin_auth._persist_failures'):
            for _ in range(5):
                client.post(
                    '/api/admin/fix-award-book-titles-by-ids',
                    headers=wrong_headers,
                    json={'items': []},
                )
            response = client.post(
                '/api/admin/fix-award-book-titles-by-ids',
                headers=wrong_headers,
                json={'items': []},
            )
        assert response.status_code == 429

    def test_get_method_rejected(self, client, db, admin_headers):
        """GET 请求应返回 405（路由级拒绝，不会进 admin_required）"""
        response = client.get(
            '/api/admin/fix-award-book-titles-by-ids',
            headers=admin_headers,
        )
        assert response.status_code == 405
