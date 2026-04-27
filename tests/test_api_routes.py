"""
API路由测试

测试API路由的核心功能，包括健康检查、获取图书列表、搜索图书、翻译功能等
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app import create_app


class TestApiRoutes:
    """API路由测试类"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用实例"""
        app = create_app('testing')
        app.config['CATEGORIES'] = {
            'hardcover-fiction': '精装小说',
            'hardcover-nonfiction': '精装非虚构'
        }
        return app
    
    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        return app.test_client()
    
    def test_health_check(self, client):
        """测试健康检查端点"""
        # 执行测试
        response = client.get('/api/health')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'healthy'
        assert data['data']['service'] == 'book-rank-api'
    
    def test_get_csrf_token(self, client):
        """测试获取CSRF令牌端点"""
        # 执行测试
        response = client.get('/api/csrf-token')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'csrf_token' in data['data']
    
    def test_get_books_invalid_category(self, client):
        """测试获取无效分类的图书"""
        # 执行测试
        response = client.get('/api/books/invalid-category')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Invalid category' in data['message']
    
    def test_search_books_missing_keyword(self, client):
        """测试搜索图书时缺少关键词"""
        # 执行测试
        response = client.get('/api/search')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Search keyword is required' in data['message']
    
    def test_search_books_short_keyword(self, client):
        """测试搜索图书时关键词过短"""
        # 执行测试
        response = client.get('/api/search?keyword=a')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Keyword must be at least 2 characters' in data['message']
    
    def test_search_books_long_keyword(self, client):
        """测试搜索图书时关键词过长"""
        # 执行测试
        long_keyword = 'a' * 101
        response = client.get(f'/api/search?keyword={long_keyword}')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Keyword must be at most 100 characters' in data['message']
    
    def test_get_search_history(self, client):
        """测试获取搜索历史"""
        # 执行测试
        response = client.get('/api/search/history')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'history' in data['data']
    
    def test_user_preferences_get(self, client):
        """测试获取用户偏好"""
        # 执行测试
        response = client.get('/api/user/preferences')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'preferences' in data['data']
    
    def test_user_preferences_post(self, client):
        """测试更新用户偏好"""
        # 执行测试
        response = client.post('/api/user/preferences', json={
            'view_mode': 'grid',
            'preferred_categories': ['hardcover-fiction']
        })
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['message'] == 'Preferences saved'
    
    def test_export_csv_invalid_category(self, client):
        """测试导出CSV时无效分类"""
        # 执行测试
        response = client.get('/api/export/invalid-category')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Invalid category' in data['message']
    
    def test_get_book_details_invalid_isbn(self, client):
        """测试获取图书详情时无效ISBN"""
        # 执行测试
        response = client.get('/api/book-details/invalid-isbn')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Invalid ISBN format' in data['message']
    
    def test_translate_text_missing_text(self, client):
        """测试翻译文本时缺少文本"""
        # 执行测试
        response = client.post('/api/translate', json={})
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert '缺少要翻译的文本' in data['message']
    
    def test_translate_text_long_text(self, client):
        """测试翻译文本时文本过长"""
        # 执行测试
        long_text = 'a' * 10001
        response = client.post('/api/translate', json={
            'text': long_text
        })
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert '文本长度超过限制' in data['message']
    
    def test_translate_book_invalid_isbn(self, client):
        """测试翻译图书时无效ISBN"""
        # 执行测试
        response = client.post('/api/translate/book/invalid-isbn')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert '无效的ISBN格式' in data['message']
    
    def test_get_translation_cache_stats(self, client):
        """测试获取翻译缓存统计信息"""
        # 执行测试
        response = client.get('/api/translate/cache/stats')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'service' in data['data']
    
    def test_get_translation_cache_recent(self, client):
        """测试获取最近的翻译缓存记录"""
        # 执行测试
        response = client.get('/api/translate/cache/recent')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'records' in data['data']
    
    def test_get_api_cache_stats(self, client):
        """测试获取API缓存统计信息"""
        # 执行测试
        response = client.get('/api/cache/stats')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_get_api_cache_recent(self, client):
        """测试获取最近的API缓存记录"""
        # 执行测试
        response = client.get('/api/cache/recent')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'records' in data['data']
    
    def test_get_awards(self, client):
        """测试获取所有奖项列表"""
        # 执行测试
        response = client.get('/api/awards')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'awards' in data['data']
    
    def test_get_award_books_invalid_award(self, client):
        """测试获取无效奖项的图书列表"""
        # 执行测试
        response = client.get('/api/awards/999999/books')
        
        # 验证结果
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
        assert '奖项不存在' in data['message']
    
    def test_get_all_award_books(self, client):
        """测试获取所有获奖图书"""
        # 执行测试
        response = client.get('/api/award-books')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'books' in data['data']
        assert 'pagination' in data['data']
    
    def test_get_award_book_detail_invalid(self, client):
        """测试获取无效图书详情"""
        # 执行测试
        response = client.get('/api/award-books/999999')
        
        # 验证结果
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
        assert '图书不存在' in data['message']
    
    def test_search_award_books_missing_keyword(self, client):
        """测试搜索获奖图书时缺少关键词"""
        # 执行测试
        response = client.get('/api/award-books/search')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert '搜索关键词不能为空' in data['message']
    
    def test_get_recommendations(self, client):
        """测试获取个性化推荐"""
        # 执行测试
        response = client.get('/api/recommendations')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_get_similarity_recommendations_missing_params(self, client):
        """测试获取相似图书推荐时缺少参数"""
        # 执行测试
        response = client.get('/api/recommendations/similarity')
        
        # 验证结果
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert '请提供' in data['message']
    
    def test_get_search_suggestions(self, client):
        """测试获取搜索建议"""
        # 执行测试
        response = client.get('/api/search/suggestions?prefix=test')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'suggestions' in data['data']
    
    def test_smart_search(self, client):
        """测试智能搜索"""
        # 执行测试
        response = client.get('/api/search/smart?keyword=test')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_get_popular_searches(self, client):
        """测试获取热门搜索词"""
        # 执行测试
        response = client.get('/api/search/popular')
        
        # 验证结果
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True