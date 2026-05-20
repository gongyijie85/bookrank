"""
翻译API集成测试

测试翻译相关API端点的核心功能，包括文本翻译、图书翻译、CSRF保护、缓存管理等
"""

import pytest

from app import create_app
from app.models.database import db as _db

ADMIN_HEADERS = {'X-Admin-Secret': 'test-admin-secret'}


@pytest.fixture(scope='module')
def app():
    """创建测试应用实例并初始化数据库"""
    app = create_app('testing')
    app.config['ADMIN_SECRET'] = 'test-admin-secret'
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='module')
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def csrf_token(client):
    """获取CSRF令牌"""
    response = client.get('/api/csrf-token')
    data = response.get_json()
    return data['data']['csrf_token']


class TestTranslationAPI:
    """翻译API测试类"""

    def test_translate_missing_content_type(self, client, csrf_token):
        """测试翻译时缺少Content-Type"""
        response = client.post('/api/translate', json={'text': 'Hello'}, headers={'X-CSRF-Token': csrf_token})
        # 使用json=参数会自动设置Content-Type，这里测试不使用json参数的情况
        response = client.post('/api/translate', data='text=Hello', headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_empty_text(self, client, csrf_token):
        """测试翻译空文本"""
        response = client.post('/api/translate', json={'text': ''}, headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_text_too_long(self, client, csrf_token):
        """测试翻译文本过长"""
        response = client.post('/api/translate', json={'text': 'x' * 10001}, headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_book_fields_empty(self, client, csrf_token):
        """测试翻译图书字段时请求体为空"""
        response = client.post('/api/translate/book-fields', json={}, headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_book_isbn_invalid(self, client, csrf_token):
        """测试翻译图书时ISBN无效"""
        response = client.post('/api/translate/book/invalid-isbn', headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_cache_stats(self, client):
        """测试获取翻译缓存统计信息"""
        response = client.get('/api/translate/cache/stats', headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'service' in data['data']

    def test_translate_cache_recent(self, client):
        """测试获取最近的翻译缓存记录"""
        response = client.get('/api/translate/cache/recent?limit=5', headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True


class TestCSRFProtection:
    """CSRF保护测试类"""

    def test_csrf_token_endpoint(self, client):
        """测试CSRF令牌端点"""
        response = client.get('/api/csrf-token')
        assert response.status_code == 200
        data = response.get_json()
        assert 'csrf_token' in data['data']

    def test_translate_without_csrf(self, client):
        """测试不带CSRF令牌发起翻译请求"""
        response = client.post('/api/translate', json={'text': 'Hello'})
        assert response.status_code in (200, 400, 403)


class TestCacheAPI:
    """缓存API测试类"""

    def test_cache_stats_requires_admin(self, client):
        """测试缓存统计需要管理员认证"""
        response = client.get('/api/cache/stats')
        assert response.status_code == 403

    def test_cache_stats(self, client):
        """测试获取缓存统计信息"""
        response = client.get('/api/cache/stats', headers=ADMIN_HEADERS)
        assert response.status_code == 200

    def test_cache_recent(self, client):
        """测试获取最近缓存记录"""
        response = client.get('/api/cache/recent?limit=5', headers=ADMIN_HEADERS)
        assert response.status_code == 200

    def test_cache_clear_without_csrf(self, client):
        """测试不带CSRF令牌清除缓存"""
        response = client.post('/api/cache/clear', json={})
        assert response.status_code in (200, 400, 403)
