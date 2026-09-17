"""
智谱AI翻译服务单元测试

覆盖范围：
- _parse_json_from_text 静态方法
- ZhipuTranslationService 初始化、可用性、缓存统计、翻译校验
- HybridTranslationService 可用性、主备切换
- 模块级便捷函数 get_translation_service / translate_text / translate_book_info
- 模块级 _translate_book_info 辅助函数
"""

from unittest.mock import MagicMock, Mock, patch

from app.services.zhipu_translation_service import (
    HybridTranslationService,
    ZhipuTranslationService,
    _cached_translate_author_name,
    _translate_book_info,
    get_translation_service,
    translate_book_info,
    translate_text,
)


def _make_api_response(content: str) -> Mock:
    """构造模拟的智谱AI API响应对象"""
    response = Mock()
    choice = Mock()
    message = Mock()
    message.content = content
    choice.message = message
    response.choices = [choice]
    return response


def _make_zhipu_service(api_key: str = 'test-key', app=None) -> ZhipuTranslationService:
    """创建已注入mock客户端的ZhipuTranslationService实例"""
    service = ZhipuTranslationService(api_key=api_key, app=app)
    mock_client = MagicMock()
    service._client = mock_client
    return service, mock_client


class TestParseJsonFromText:
    """_parse_json_from_text 静态方法测试"""

    def test_clean_json(self):
        text = '{"title_zh": "测试书名", "description_zh": "测试简介"}'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result == {'title_zh': '测试书名', 'description_zh': '测试简介'}

    def test_json_with_markdown_wrapper(self):
        text = '```json\n{"title_zh": "书名"}\n```'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result == {'title_zh': '书名'}

    def test_json_with_surrounding_text(self):
        text = '以下是翻译结果：\n{"title_zh": "翻译书名", "details_zh": "翻译详情"}\n请查收。'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result is not None
        assert result['title_zh'] == '翻译书名'
        assert result['details_zh'] == '翻译详情'

    def test_no_json_returns_none(self):
        text = '这是一段没有JSON的纯文本'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result is None

    def test_nested_json(self):
        text = '{"meta": {"version": 1}, "title_zh": "嵌套测试"}'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result is not None
        assert result['meta'] == {'version': 1}
        assert result['title_zh'] == '嵌套测试'

    def test_empty_string(self):
        result = ZhipuTranslationService._parse_json_from_text('')
        assert result is None

    def test_malformed_json_after_braces(self):
        text = '{not valid json}'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result is None

    def test_json_surrounded_by_non_json_text(self):
        text = '翻译结果如下：\n{"title_zh": "书名", "description_zh": "简介"}\n以上。'
        result = ZhipuTranslationService._parse_json_from_text(text)
        assert result is not None
        assert result['title_zh'] == '书名'
        assert result['description_zh'] == '简介'


class TestZhipuTranslationServiceInit:
    """ZhipuTranslationService 初始化测试"""

    def test_api_key_from_param(self):
        service = ZhipuTranslationService(api_key='my-secret-key')
        assert service.api_key == 'my-secret-key'
        assert service.model == 'glm-4.7-flash'

    def test_api_key_from_env(self):
        with patch.dict('os.environ', {'ZHIPU_API_KEY': 'env-key-123'}):
            service = ZhipuTranslationService(api_key=None)
            assert service.api_key == 'env-key-123'

    def test_missing_key_results_in_none(self):
        with patch.dict('os.environ', {}, clear=True):
            service = ZhipuTranslationService(api_key=None)
            assert service.api_key is None

    def test_model_from_param(self):
        service = ZhipuTranslationService(api_key='k', model='custom-model')
        assert service.model == 'custom-model'

    def test_model_from_app_config(self, app):
        app.config['ZHIPU_TRANSLATION_MODEL'] = 'config-model'
        service = ZhipuTranslationService(api_key='k', app=app)
        assert service.model == 'config-model'

    def test_zhipu_rollback_ignores_siliconflow_model(self, app):
        app.config.update(
            TRANSLATION_PROVIDER='zhipu',
            TRANSLATION_MODEL='tencent/Hunyuan-MT-7B',
            ZHIPU_TRANSLATION_MODEL='glm-4.7-flash',
            TRANSLATION_USE_MERGED_JSON=None,
        )

        service = ZhipuTranslationService(api_key='k', app=app)

        assert service.provider == 'zhipu'
        assert service.model == 'glm-4.7-flash'
        assert service.use_merged_json is True

    def test_siliconflow_uses_configured_model_and_field_mode(self, app):
        app.config.update(
            TRANSLATION_PROVIDER='siliconflow',
            TRANSLATION_MODEL='tencent/Hunyuan-MT-7B',
            TRANSLATION_USE_MERGED_JSON=None,
        )

        service = ZhipuTranslationService(api_key='k', app=app)

        assert service.provider == 'siliconflow'
        assert service.model == 'tencent/Hunyuan-MT-7B'
        assert service.use_merged_json is False

    def test_merged_json_config_overrides_provider_default(self, app):
        app.config.update(
            TRANSLATION_PROVIDER='siliconflow',
            TRANSLATION_USE_MERGED_JSON=True,
        )

        service = ZhipuTranslationService(api_key='k', app=app)

        assert service.use_merged_json is True

    def test_model_default_fallback(self):
        service = ZhipuTranslationService(api_key='k')
        assert service.model == 'glm-4.7-flash'

    def test_initial_state(self):
        service = ZhipuTranslationService(api_key='k')
        assert service._client is None
        assert service._cache_service is None
        assert service._last_request_time == 0


class TestZhipuTranslationServiceAvailability:
    """ZhipuTranslationService.is_available 测试"""

    def test_available_with_client(self):
        service, _ = _make_zhipu_service()
        assert service.is_available() is True

    def test_not_available_without_key(self):
        with patch.dict('os.environ', {}, clear=True):
            service = ZhipuTranslationService(api_key=None)
            assert service.is_available() is False

    def test_not_available_when_client_creation_fails(self):
        service = ZhipuTranslationService(api_key='test-key')
        with patch(
            'app.services.zhipu_translation_service.ZhipuTranslationService._get_client',
            return_value=None,
        ):
            assert service.is_available() is False


class TestZhipuTranslationServiceGetCacheStats:
    """ZhipuTranslationService.get_cache_stats 测试"""

    def test_returns_dict_when_cache_unavailable(self):
        service, _ = _make_zhipu_service()
        service._cache_service = None
        with patch.object(service, '_get_cache_service', return_value=None):
            stats = service.get_cache_stats()
            assert isinstance(stats, dict)
            assert stats['total_count'] == 0
            assert '缓存服务不可用' in stats['message']

    def test_returns_stats_from_cache_service(self):
        service, _ = _make_zhipu_service()
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {'total_count': 42, 'hit_rate': 0.85}
        with patch.object(service, '_get_cache_service', return_value=mock_cache):
            stats = service.get_cache_stats()
            assert stats['total_count'] == 42
            assert stats['hit_rate'] == 0.85


class TestValidateTranslation:
    """_validate_translation 静态方法测试"""

    def test_valid_translation(self):
        result = ZhipuTranslationService._validate_translation('了不起的盖茨比', 'The Great Gatsby')
        assert result is True

    def test_same_as_original_rejected(self):
        result = ZhipuTranslationService._validate_translation('The Great Gatsby', 'The Great Gatsby')
        assert result is False

    def test_empty_translated_text_accepted(self):
        result = ZhipuTranslationService._validate_translation('', 'Hello')
        assert result is True

    def test_none_translated_text_accepted(self):
        result = ZhipuTranslationService._validate_translation(None, 'Hello')
        assert result is True

    def test_pollution_marker_book_title(self):
        result = ZhipuTranslationService._validate_translation('书名：了不起的盖茨比', 'The Great Gatsby')
        assert result is False

    def test_pollution_marker_author(self):
        result = ZhipuTranslationService._validate_translation('作者：张三', 'John Smith')
        assert result is False

    def test_pollution_marker_description(self):
        result = ZhipuTranslationService._validate_translation('简介：这是一本书', 'A book')
        assert result is False

    def test_pollution_marker_bold_markdown(self):
        result = ZhipuTranslationService._validate_translation('**测试**', 'Test')
        assert result is False

    def test_pollution_marker_english_title_prefix(self):
        result = ZhipuTranslationService._validate_translation('Title: 书名', 'Book')
        assert result is False

    def test_pollution_marker_translation_prefix(self):
        result = ZhipuTranslationService._validate_translation('翻译：你好', 'Hello')
        assert result is False

    def test_pollution_marker_backtick(self):
        result = ZhipuTranslationService._validate_translation('`代码`', 'Code')
        assert result is False

    def test_whitespace_only_differs_from_source(self):
        result = ZhipuTranslationService._validate_translation('  新文本  ', 'Original')
        assert result is True


class TestHybridTranslationServiceAvailability:
    """HybridTranslationService.is_available 测试"""

    def test_available_when_zhipu_available(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = True
        service.zhipu = mock_zhipu
        assert service.is_available() is True

    def test_available_when_fallback_available(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = False
        service.zhipu = mock_zhipu
        mock_fallback = Mock()
        with patch.object(service, '_get_fallback', return_value=mock_fallback):
            assert service.is_available() is True

    def test_not_available_when_neither_available(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = False
        service.zhipu = mock_zhipu
        with patch.object(service, '_get_fallback', return_value=None):
            assert service.is_available() is False


class TestHybridTranslationServiceTranslate:
    """HybridTranslationService.translate 测试"""

    def test_empty_text_returns_input(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        assert service.translate('') == ''
        assert service.translate(None) is None
        assert service.translate('   ') == '   '

    def test_cache_hit_returns_translated(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cached_result = Mock()
        mock_cached_result.translated_text = '缓存翻译结果'
        mock_cache.get.return_value = mock_cached_result
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', return_value='缓存翻译结果'),
        ):
            result = service.translate('Hello')
            assert result == '缓存翻译结果'

    def test_primary_zhipu_used_when_available(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cache.get.return_value = None
        with patch.object(service, '_get_cache_service', return_value=mock_cache):
            mock_zhipu = Mock()
            mock_zhipu.is_available.return_value = True
            mock_zhipu.translate.return_value = '智谱翻译结果'
            service.zhipu = mock_zhipu
            result = service.translate('Hello')
            assert result == '智谱翻译结果'
            mock_zhipu.translate.assert_called_once()

    def test_fallback_used_when_zhipu_fails(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_cache = Mock()
        mock_cache.get.return_value = None
        with patch.object(service, '_get_cache_service', return_value=mock_cache):
            mock_zhipu = Mock()
            mock_zhipu.is_available.return_value = False
            service.zhipu = mock_zhipu
            mock_fallback = Mock()
            mock_fallback.translate.return_value = '备用翻译结果'
            with patch.object(service, '_get_fallback', return_value=mock_fallback):
                result = service.translate('Hello')
                assert result == '备用翻译结果'

    def test_returns_none_when_all_services_fail(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_cache = Mock()
        mock_cache.get.return_value = None
        with patch.object(service, '_get_cache_service', return_value=mock_cache):
            mock_zhipu = Mock()
            mock_zhipu.is_available.return_value = False
            service.zhipu = mock_zhipu
            with patch.object(service, '_get_fallback', return_value=None):
                result = service.translate('Hello')
                assert result is None


class TestGetTranslationServiceSingleton:
    """get_translation_service 单例模式测试"""

    def test_returns_same_instance(self):
        with patch('app.services.zhipu_translation_service._hybrid_translation_service', None):
            service1 = get_translation_service()
            service2 = get_translation_service()
            assert service1 is service2

    def test_singleton_is_hybrid_service(self):
        with patch('app.services.zhipu_translation_service._hybrid_translation_service', None):
            service = get_translation_service()
            assert isinstance(service, HybridTranslationService)


class TestTranslateTextConvenienceFunction:
    """translate_text 便捷函数测试"""

    def test_delegates_to_singleton(self):
        mock_service = MagicMock()
        mock_service.translate.return_value = '便捷函数翻译结果'
        with patch('app.services.zhipu_translation_service.get_translation_service', return_value=mock_service):
            result = translate_text('Hello world')
            assert result == '便捷函数翻译结果'
            mock_service.translate.assert_called_once_with('Hello world', 'en', 'zh')

    def test_passes_custom_languages(self):
        mock_service = MagicMock()
        mock_service.translate.return_value = '结果'
        with patch('app.services.zhipu_translation_service.get_translation_service', return_value=mock_service):
            translate_text('Text', 'en', 'ja')
            mock_service.translate.assert_called_once_with('Text', 'en', 'ja')


class TestTranslateBookInfoConvenienceFunction:
    """translate_book_info 便捷函数测试"""

    def test_delegates_to_singleton(self):
        mock_service = MagicMock()
        expected = {'title': 'Book', 'title_zh': '书名'}
        mock_service.translate_book_info.return_value = expected
        with patch('app.services.zhipu_translation_service.get_translation_service', return_value=mock_service):
            book_data = {'title': 'Book'}
            result = translate_book_info(book_data)
            assert result == expected
            mock_service.translate_book_info.assert_called_once_with(book_data, 'zh')

    def test_passes_custom_target_lang(self):
        mock_service = MagicMock()
        mock_service.translate_book_info.return_value = {}
        with patch('app.services.zhipu_translation_service.get_translation_service', return_value=mock_service):
            translate_book_info({'title': 'X'}, target_lang='ja')
            mock_service.translate_book_info.assert_called_once_with({'title': 'X'}, 'ja')


class TestTranslateBookInfoHelper:
    """_translate_book_info 模块级辅助函数测试"""

    def test_translates_missing_fields(self):
        mock_translator = Mock()
        mock_translator.translate.return_value = '翻译内容'
        book_data = {'title': 'English Title', 'description': 'English Desc', 'details': 'English Details'}
        result = _translate_book_info(mock_translator, book_data)
        assert result['title_zh'] == '翻译内容'
        assert result['description_zh'] == '翻译内容'
        assert result['details_zh'] == '翻译内容'
        assert mock_translator.translate.call_count == 3

    def test_skips_already_translated_fields(self):
        mock_translator = Mock()
        mock_translator.translate.return_value = '新翻译'
        book_data = {
            'title': 'English Title',
            'title_zh': '已翻译标题',
            'description': 'English Desc',
        }
        result = _translate_book_info(mock_translator, book_data)
        assert result['title_zh'] == '已翻译标题'
        assert mock_translator.translate.call_count == 1
        mock_translator.translate.assert_called_with(
            'English Desc', target_lang='zh', field_type='description', context=book_data
        )

    def test_skips_empty_source_fields(self):
        mock_translator = Mock()
        mock_translator.translate.return_value = '翻译'
        book_data = {'title': '', 'description': None}
        result = _translate_book_info(mock_translator, book_data)
        assert mock_translator.translate.call_count == 0
        assert 'title_zh' not in result
        assert 'description_zh' not in result

    def test_does_not_modify_original_dict(self):
        mock_translator = Mock()
        mock_translator.translate.return_value = '翻译'
        original = {'title': 'Book'}
        _translate_book_info(mock_translator, original)
        assert 'title_zh' not in original

    def test_passes_custom_target_lang(self):
        mock_translator = Mock()
        mock_translator.translate.return_value = '翻訳'
        book_data = {'title': 'Book'}
        _translate_book_info(mock_translator, book_data, target_lang='ja')
        mock_translator.translate.assert_called_once_with(
            'Book', target_lang='ja', field_type='title', context=book_data
        )


class TestZhipuTranslationServiceTranslate:
    """ZhipuTranslationService.translate 测试"""

    def test_empty_text_returns_input(self):
        service, _ = _make_zhipu_service()
        assert service.translate('') == ''
        assert service.translate('   ') == '   '
        assert service.translate(None) is None

    def test_no_client_returns_none(self):
        service = ZhipuTranslationService(api_key=None)
        with patch.dict('os.environ', {}, clear=True):
            result = service.translate('Hello')
            assert result is None

    def test_successful_translation(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response('翻译结果')
        with (
            patch('app.services.zhipu_translation_service.clean_translation_text', return_value='翻译结果'),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate('Hello', field_type='text')
            assert result == '翻译结果'

    def test_empty_response_returns_none(self):
        service, mock_client = _make_zhipu_service()
        mock_resp = Mock()
        mock_resp.choices = []
        mock_client.chat.completions.create.return_value = mock_resp
        with patch('app.services.zhipu_translation_service.time') as mock_time:
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate('Hello')
            assert result is None

    def test_validation_failure_still_postprocesses(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response('书名：测试')
        with (
            patch.object(service, '_validate_translation', return_value=False),
            patch('app.services.zhipu_translation_service.clean_translation_text', return_value='测试'),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate('Test', field_type='title')
            assert result == '测试'


class TestZhipuTranslationServiceTranslateAuthorName:
    """ZhipuTranslationService.translate_author_name 测试"""

    def test_empty_author_returns_none(self):
        service, _ = _make_zhipu_service()
        assert service.translate_author_name('') is None
        assert service.translate_author_name('   ') is None
        assert service.translate_author_name(None) is None

    def test_cached_author_returns_from_cache(self):
        service, _ = _make_zhipu_service()
        with patch.object(service, 'translate', return_value='约翰·史密斯') as mock_translate:
            assert service.translate_author_name('John Smith') == '约翰·史密斯'
            assert service.translate_author_name('John Smith') == '约翰·史密斯'
            mock_translate.assert_called_once_with('John Smith', field_type='author')

    def test_lru_cache_bounds_size(self):
        service, _ = _make_zhipu_service()
        with patch.object(service, 'translate', return_value='作者'):
            for i in range(1001):
                service.translate_author_name(f'Author {i}')
        info = _cached_translate_author_name.cache_info()
        assert info.currsize <= 1000

    def test_lru_cache_hits_on_repeat(self):
        service, _ = _make_zhipu_service()
        with patch.object(service, 'translate', return_value='甲') as mock_translate:
            service.translate_author_name('A')
            service.translate_author_name('B')
            service.translate_author_name('C')
            service.translate_author_name('A')
        info = _cached_translate_author_name.cache_info()
        assert info.hits >= 1
        assert mock_translate.call_count == 3


class TestHybridTranslationServiceGetCacheStats:
    """HybridTranslationService.get_cache_stats 测试"""

    def test_returns_dict_when_no_cache(self):
        service = HybridTranslationService(zhipu_api_key='k')
        with patch.object(service, '_get_cache_service', return_value=None):
            stats = service.get_cache_stats()
            assert isinstance(stats, dict)
            assert stats['total_count'] == 0

    def test_returns_cache_stats(self):
        service = HybridTranslationService(zhipu_api_key='k')
        mock_cache = Mock()
        mock_cache.get_stats.return_value = {'total_count': 100}
        with patch.object(service, '_get_cache_service', return_value=mock_cache):
            stats = service.get_cache_stats()
            assert stats['total_count'] == 100


class TestFieldPrompts:
    """字段提示词配置测试"""

    def test_all_expected_field_types_present(self):
        service = ZhipuTranslationService(api_key='k')
        expected_types = ['title', 'description', 'details', 'author', 'text']
        for ft in expected_types:
            prompt = service._get_prompt_for_field(ft)
            assert prompt is not None
            assert len(prompt) > 0

    def test_unknown_field_falls_back_to_text(self):
        service = ZhipuTranslationService(api_key='k')
        text_prompt = service._get_prompt_for_field('text')
        unknown_prompt = service._get_prompt_for_field('nonexistent')
        assert unknown_prompt == text_prompt


class TestHunyuanPublishingPrompts:
    def test_title_prompt_generalizes_semantic_adaptation_with_context(self):
        prompt = ZhipuTranslationService._build_hunyuan_prompt(
            'VERITY',
            'zh',
            'title',
            {
                'author': 'Colleen Hoover',
                'category': 'Psychological thriller',
                'description': 'A manuscript exposes a horrifying truth.',
            },
        )

        assert '意译' in prompt
        assert '有限创译' in prompt
        assert '人名标题不必机械音译' in prompt
        assert '避免生硬逐字翻译' in prompt
        assert 'Colleen Hoover' in prompt
        assert 'Psychological thriller' in prompt
        assert prompt.endswith('VERITY')

    def test_description_prompt_uses_confirmed_title_and_glossary(self):
        prompt = ZhipuTranslationService._build_hunyuan_prompt(
            'Lowen discovers a manuscript.',
            'zh',
            'description',
            {
                'title': 'Verity',
                'title_zh': '真相',
                'glossary': {'Lowen Ashleigh': '洛温·阿什利'},
            },
        )

        assert '已确定中文书名：真相' in prompt
        assert 'Lowen Ashleigh' in prompt
        assert '洛温·阿什利' in prompt
        assert '不改变人物关系和情节' in prompt

    def test_hunyuan_request_uses_single_user_message_and_recommended_parameters(self, app):
        app.config.update(
            TRANSLATION_PROVIDER='siliconflow',
            TRANSLATION_MODEL='tencent/Hunyuan-MT-7B',
            TRANSLATION_USE_MERGED_JSON=None,
        )
        service, mock_client = _make_zhipu_service(app=app)
        mock_client.chat.completions.create.return_value = _make_api_response('真相')

        result = service.translate(
            'VERITY',
            field_type='title',
            context={'author': 'Colleen Hoover', 'description': 'A horrifying truth is uncovered.'},
        )

        assert result == '真相'
        request = mock_client.chat.completions.create.call_args.kwargs
        assert [message['role'] for message in request['messages']] == ['user']
        assert 'Colleen Hoover' in request['messages'][0]['content']
        assert request['temperature'] == 0.7
        assert request['top_p'] == 0.6
        assert request['frequency_penalty'] == 0
        assert request['extra_body'] == {'top_k': 20, 'repetition_penalty': 1.05}

    def test_cache_context_changes_by_field_and_book_context(self):
        title_context = ZhipuTranslationService.build_cache_context('title', {'author': 'Author A'})
        other_book = ZhipuTranslationService.build_cache_context('title', {'author': 'Author B'})
        description_context = ZhipuTranslationService.build_cache_context('description', {'author': 'Author A'})

        assert title_context != other_book
        assert title_context != description_context
        assert ZhipuTranslationService.PROMPT_VERSION in title_context
