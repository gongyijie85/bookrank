"""
翻译服务测试

测试翻译服务的核心功能，包括智谱AI翻译、混合翻译服务等
"""
import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from app.services.zhipu_translation_service import (
    HybridTranslationService, ZhipuTranslationService,
    get_translation_service, translate_text, translate_book_info
)


class TestTranslationService:
    """翻译服务测试类"""

    @pytest.fixture
    def hybrid_service(self):
        """创建混合翻译服务实例"""
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = '测试翻译结果'
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response

        service = HybridTranslationService(zhipu_api_key='test_api_key')
        service.zhipu._client = mock_client
        service._cache_service = Mock()
        service._cache_service.get.return_value = None
        service._cache_service.get_stats.return_value = {'total_count': 0}
        return service
    
    def test_translate_text(self, hybrid_service):
        """测试翻译文本"""
        # 执行测试
        result = hybrid_service.translate('Hello world')
        
        # 验证结果
        assert result == '测试翻译结果'
    
    def test_translate_empty_text(self, hybrid_service):
        """测试翻译空文本"""
        # 执行测试
        result = hybrid_service.translate('')
        
        # 验证结果
        assert result == ''
    
    def test_translate_none_text(self, hybrid_service):
        """测试翻译None文本"""
        # 执行测试
        result = hybrid_service.translate(None)
        
        # 验证结果
        assert result is None
    
    def test_translate_batch(self, hybrid_service):
        """测试批量翻译"""
        # 执行测试
        texts = ['Hello', 'World']
        results = hybrid_service.translate_batch(texts)
        
        # 验证结果
        assert len(results) == 2
        assert results[0] == '测试翻译结果'
        assert results[1] == '测试翻译结果'
    
    def test_translate_book_info(self, hybrid_service):
        """测试翻译图书信息"""
        # 执行测试
        book_data = {
            'title': 'Test Book',
            'description': 'This is a test book',
            'details': 'Detailed description'
        }
        result = hybrid_service.translate_book_info(book_data)

        # 验证结果
        assert result['title'] == 'Test Book'
        assert result['title_zh'] == '《测试翻译结果》'
        assert result['description_zh'] == '测试翻译结果'
        assert result['details_zh'] == '测试翻译结果'
    
    def test_translate_book_info_with_existing_translation(self, hybrid_service):
        """测试翻译已有翻译的图书信息"""
        # 执行测试
        book_data = {
            'title': 'Test Book',
            'title_zh': '已翻译的书名',
            'description': 'This is a test book'
        }
        result = hybrid_service.translate_book_info(book_data)
        
        # 验证结果
        assert result['title_zh'] == '已翻译的书名'  # 应该保持原有翻译
        assert result['description_zh'] == '测试翻译结果'  # 应该翻译新内容
    
    def test_get_cache_stats(self, hybrid_service):
        """测试获取缓存统计信息"""
        # 执行测试
        stats = hybrid_service.get_cache_stats()
        
        # 验证结果
        assert isinstance(stats, dict)
    
    def test_get_translation_service_singleton(self):
        """测试获取翻译服务的单例模式"""
        # 执行测试
        service1 = get_translation_service()
        service2 = get_translation_service()
        
        # 验证结果
        assert service1 is service2
    
    def test_translate_text_convenience_function(self):
        """测试翻译文本的便捷函数"""
        # 模拟翻译服务
        with patch('app.services.zhipu_translation_service.get_translation_service') as mock_get_service:
            mock_service = Mock()
            mock_service.translate.return_value = '测试翻译结果'
            mock_get_service.return_value = mock_service
            
            # 执行测试
            result = translate_text('Hello world')
            
            # 验证结果
            assert result == '测试翻译结果'
    
    def test_translate_book_info_convenience_function(self):
        """测试翻译图书信息的便捷函数"""
        # 模拟翻译服务
        with patch('app.services.zhipu_translation_service.get_translation_service') as mock_get_service:
            mock_service = Mock()
            mock_service.translate_book_info.return_value = {'title': 'Test Book', 'title_zh': '测试书名'}
            mock_get_service.return_value = mock_service
            
            # 执行测试
            book_data = {'title': 'Test Book'}
            result = translate_book_info(book_data)
            
            # 验证结果
            assert result['title'] == 'Test Book'
            assert result['title_zh'] == '测试书名'
    
    def test_zhipu_translation_service_init(self):
        """测试智谱翻译服务初始化"""
        # 执行测试
        service = ZhipuTranslationService(api_key='test_api_key')
        
        # 验证结果
        assert service.api_key == 'test_api_key'
        assert service.model == 'glm-4.7-flash'
    
    def test_zhipu_translation_service_unavailable(self):
        """测试智谱翻译服务不可用的情况"""
        with patch.dict(os.environ, {}, clear=False):
            env_key = os.environ.pop('ZHIPU_API_KEY', None)
            try:
                service = ZhipuTranslationService(api_key=None)
                assert not service.is_available()
                assert service.translate('Hello world') is None
            finally:
                if env_key is not None:
                    os.environ['ZHIPU_API_KEY'] = env_key


class TestTranslationPostprocess:
    """翻译后处理统一函数测试"""

    def test_clean_removes_markdown_bold(self):
        from app.utils.api_helpers import clean_translation_text
        assert clean_translation_text('**了不起的盖茨比**') == '了不起的盖茨比'

    def test_clean_removes_field_prefix(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('书名：了不起的盖茨比')
        assert '书名：' not in result

    def test_clean_removes_translation_prefix(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('翻译：这是测试内容')
        assert result == '这是测试内容'

    def test_clean_title_truncates_at_next_field(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('书名：了不起的盖茨比作者：菲茨杰拉德', field_type='title')
        assert '菲茨杰拉德' not in result
        assert '盖茨比' in result

    def test_clean_preserves_clean_text(self):
        from app.utils.api_helpers import clean_translation_text
        assert clean_translation_text('这是一段干净的中文') == '这是一段干净的中文'

    def test_clean_empty_and_none(self):
        from app.utils.api_helpers import clean_translation_text
        assert clean_translation_text('') == ''
        assert clean_translation_text(None) is None

    def test_quick_clean_skips_clean_text(self):
        from app.utils.api_helpers import quick_clean_translation
        result = quick_clean_translation('干净的中文文本')
        assert result == '干净的中文文本'

    def test_quick_clean_processes_dirty_text(self):
        from app.utils.api_helpers import quick_clean_translation
        result = quick_clean_translation('**书名**测试内容')
        assert '**' not in result

    def test_add_book_title_marks_for_title(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('了不起的盖茨比', field_type='title')
        assert result == '《了不起的盖茨比》'

    def test_no_marks_for_mixed_lang_title(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('Clean Code', field_type='title')
        assert '《' not in result


class TestFieldAwarePrompts:
    """字段感知提示词测试"""

    def test_title_prompt_prohibits_book_marks(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('title')
        assert '书名号' in prompt or '《》' in prompt

    def test_description_prompt_requests_fluent(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('description')
        assert '流畅' in prompt or '自然' in prompt

    def test_text_prompt_is_default(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('text')
        assert prompt is not None
        assert len(prompt) > 0

    def test_author_prompt_format(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('author')
        assert '译名' in prompt or '音译' in prompt

    def test_unknown_field_returns_text_prompt(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('unknown_field')
        text_prompt = service._get_prompt_for_field('text')
        assert prompt == text_prompt


class TestTranslationQualityCheck:
    """翻译质量校验测试"""

    def test_reject_dirty_translation_with_labels(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('书名：了不起的盖茨比', 'The Great Gatsby')
        assert result is False

    def test_reject_dirty_translation_with_markdown(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('**了不起的盖茨比**', 'The Great Gatsby')
        assert result is False

    def test_accept_clean_translation(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('了不起的盖茨比', 'The Great Gatsby')
        assert result is True

    def test_reject_too_similar_to_source(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('The Great Gatsby', 'The Great Gatsby')
        assert result is False

    def test_accept_empty_result_passthrough(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('', 'Hello')
        assert result is True


class TestTranslationCacheVersion:
    """翻译缓存版本控制测试"""

    def test_cache_version_exists(self):
        from app.services.translation_cache_service import TranslationCacheService
        assert hasattr(TranslationCacheService, 'CACHE_VERSION')
        assert isinstance(TranslationCacheService.CACHE_VERSION, int)
        assert TranslationCacheService.CACHE_VERSION >= 2


class TestFreeTranslationService:
    """免费翻译服务测试"""

    def test_google_translate_empty_input(self):
        from app.services.free_translation_service import GoogleTranslationService
        service = GoogleTranslationService()
        assert service.translate('') == ''
        assert service.translate(None) is None

    def test_free_service_empty_input(self):
        from app.services.free_translation_service import FreeTranslationService
        service = FreeTranslationService()
        assert service.translate('') == ''
        assert service.translate(None) is None