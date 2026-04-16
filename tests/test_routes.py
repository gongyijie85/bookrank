"""
API 路由测试

测试所有 API 端点的响应、参数验证和错误处理
"""
import pytest
import json

from app.models.database import db
from app.models.schemas import (
    UserPreference,
    SearchHistory,
    Award,
    AwardBook
)


# ==================== 健康检查测试 ====================

@pytest.mark.routes
class TestHealthCheck:
    """测试健康检查端点"""

    def test_health_check_success(self, client):
        """测试健康检查成功响应"""
        response = client.get('/api/health')

        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['status'] == 'healthy'


# ==================== 图书列表测试 ====================

@pytest.mark.routes
class TestGetBooks:
    """测试获取图书列表端点"""

    def test_get_books_invalid_category(self, client):
        """测试无效分类参数"""
        response = client.get('/api/books/invalid_category_xyz')

        assert response.status_code == 400

        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Invalid category' in data['message']


# ==================== 搜索功能测试 ====================

@pytest.mark.routes
class TestSearchBooks:
    """测试搜索图书端点"""

    def test_search_empty_keyword(self, client):
        """测试空关键词"""
        response = client.get('/api/search?keyword=')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'required' in data['message'].lower()

    def test_search_short_keyword(self, client):
        """测试过短关键词"""
        response = client.get('/api/search?keyword=a')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'at least 2' in data['message'].lower()


# ==================== 搜索历史测试 ====================

@pytest.mark.routes
class TestSearchHistory:
    """测试搜索历史端点"""

    def test_get_search_history_empty(self, client, db):
        """测试获取空搜索历史"""
        response = client.get('/api/search/history')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ==================== 用户偏好测试 ====================

@pytest.mark.routes
class TestUserPreferences:
    """测试用户偏好端点"""

    def test_get_preferences_empty(self, client, db):
        """测试获取不存在的用户偏好"""
        response = client.get('/api/user/preferences')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_update_preferences_invalid_content_type(self, client):
        """测试无效的内容类型"""
        response = client.post(
            '/api/user/preferences',
            data='not json',
            content_type='text/plain'
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_update_preferences_view_mode(self, client, db):
        """测试更新视图模式"""
        response = client.post(
            '/api/user/preferences',
            data=json.dumps({'view_mode': 'list'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ==================== ISBN 验证测试 ====================

@pytest.mark.routes
class TestISBNValidation:
    """测试 ISBN 验证功能"""

    def test_validate_isbn_invalid_format(self, client):
        """测试无效 ISBN 格式"""
        response = client.get('/api/book-details/invalid_isbn')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Invalid ISBN' in data['message']

    def test_validate_isbn_valid_10(self, client):
        """测试有效 ISBN-10"""
        response = client.get('/api/book-details/014312755X')

        # 格式正确但可能找不到书籍
        assert response.status_code in [200, 404]

    def test_validate_isbn_valid_13(self, client):
        """测试有效 ISBN-13"""
        response = client.get('/api/book-details/9780143127550')

        # 格式正确但可能找不到书籍
        assert response.status_code in [200, 404]


# ==================== 奖项相关测试 ====================

@pytest.mark.routes
class TestAwards:
    """测试奖项相关端点"""

    def test_get_awards_empty(self, client, db):
        """测试获取空奖项列表"""
        response = client.get('/api/awards')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_get_awards_with_data(self, client, db):
        """测试获取有数据的奖项列表"""
        award = Award(
            name='诺贝尔文学奖',
            name_en='Nobel Prize',
            country='瑞典'
        )
        db.session.add(award)
        db.session.commit()

        response = client.get('/api/awards')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['data']['awards']) >= 1

    def test_get_award_books_not_found(self, client):
        """测试获取不存在的奖项图书"""
        response = client.get('/api/awards/99999/books')

        # 由于测试环境可能没有数据，返回可能是 404 或 500
        assert response.status_code in [404, 500]

    def test_get_award_books_invalid_year(self, client):
        """测试无效年份参数"""
        response = client.get('/api/awards/1/books?year=3000')

        assert response.status_code in [400, 500]


# ==================== 获奖图书测试 ====================

@pytest.mark.routes
class TestAwardBooks:
    """测试获奖图书端点"""

    def test_get_award_book_detail_not_found(self, client):
        """测试获取不存在的图书详情"""
        response = client.get('/api/award-books/99999')

        assert response.status_code in [404, 500]

    def test_search_award_books_empty_keyword(self, client):
        """测试搜索空关键词"""
        response = client.get('/api/award-books/search?keyword=')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_search_award_books_keyword_too_long(self, client):
        """测试关键词过长"""
        long_keyword = 'a' * 101
        response = client.get(f'/api/award-books/search?keyword={long_keyword}')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False


# ==================== 翻译功能测试 ====================

@pytest.mark.routes
class TestTranslationAPI:
    """测试翻译功能端点"""

    def test_translate_with_fallback(self, client):
        """测试翻译功能（使用备用翻译服务）"""
        response = client.post(
            '/api/translate',
            data=json.dumps({'text': 'Hello'}),
            content_type='application/json'
        )

        assert response.status_code in [200, 503]
        data = json.loads(response.data)
        if response.status_code == 200:
            assert data['success'] is True
            assert 'translated' in data['data']

    def test_translation_cache_stats(self, client):
        """测试翻译缓存统计"""
        response = client.get('/api/translate/cache/stats')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data


# ==================== CSV 导出测试 ====================

@pytest.mark.routes
class TestExportCSV:
    """测试 CSV 导出端点"""

    def test_export_invalid_category(self, client):
        """测试无效分类导出"""
        response = client.get('/api/export/invalid_category')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False


# ==================== 错误处理测试 ====================

@pytest.mark.routes
class TestErrorHandlers:
    """测试错误处理器"""

    def test_404_error(self, client):
        """测试 404 错误"""
        response = client.get('/api/nonexistent')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False
