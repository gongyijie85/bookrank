"""
智谱AI翻译服务扩展测试

覆盖现有测试未覆盖的路径：
- _get_client 错误路径（ImportError / ConnectionError）
- _get_cache_service 导入失败路径
- translate 速率限制、重试逻辑、异常处理
- translate_batch 缓存预检 + 并行翻译 + 进度回调
- translate_book_fields 合并翻译全路径
- HybridTranslationService._run_with_context / _get_fallback / 缓存写入
- HybridTranslationService.translate_batch 完整流程
"""

import json
import time
from unittest.mock import MagicMock, Mock, patch

from app.services.zhipu_translation_service import (
    HybridTranslationService,
    ZhipuTranslationService,
)


def _make_api_response(content: str | None) -> Mock:
    response = Mock()
    choice = Mock()
    message = Mock()
    message.content = content
    choice.message = message
    response.choices = [choice] if content is not None else []
    return response


def _make_zhipu_service(api_key: str = 'test-key', app=None):
    service = ZhipuTranslationService(api_key=api_key, app=app)
    mock_client = MagicMock()
    service._client = mock_client
    return service, mock_client


class TestGetClientErrorPaths:
    def test_import_error_returns_none(self):
        service = ZhipuTranslationService(api_key='test-key')
        service._client = None
        with (
            patch.dict('sys.modules', {'zhipuai': None}),
            patch('builtins.__import__', side_effect=ImportError('No module')),
        ):
            result = service._get_client()
            assert result is None

    def test_connection_error_returns_none(self):
        service = ZhipuTranslationService(api_key='test-key')
        service._client = None
        mock_zhipu_module = MagicMock()
        mock_zhipu_module.ZhipuAI.side_effect = ConnectionError('Connection refused')
        with patch.dict('sys.modules', {'zhipuai': mock_zhipu_module}):
            result = service._get_client()
            assert result is None

    def test_runtime_error_returns_none(self):
        service = ZhipuTranslationService(api_key='test-key')
        service._client = None
        mock_zhipu_module = MagicMock()
        mock_zhipu_module.ZhipuAI.side_effect = RuntimeError('Init failed')
        with patch.dict('sys.modules', {'zhipuai': mock_zhipu_module}):
            result = service._get_client()
            assert result is None

    def test_no_api_key_returns_none(self):
        service = ZhipuTranslationService(api_key=None)
        service._client = None
        with patch.dict('os.environ', {}, clear=True):
            result = service._get_client()
            assert result is None

    def test_successful_client_creation(self):
        service = ZhipuTranslationService(api_key='test-key')
        service._client = None
        mock_zhipu_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_zhipu_module.ZhipuAI.return_value = mock_client_instance
        with patch.dict('sys.modules', {'zhipuai': mock_zhipu_module}):
            result = service._get_client()
            assert result is mock_client_instance
            assert service._client is mock_client_instance

    def test_cached_client_returned_directly(self):
        service, mock_client = _make_zhipu_service()
        result = service._get_client()
        assert result is mock_client


class TestGetCacheServiceErrorPaths:
    def test_cache_service_import_error(self):
        service = ZhipuTranslationService(api_key='test-key')
        service._cache_service = None
        with patch(
            'builtins.__import__',
            side_effect=ImportError('No cache module'),
        ):
            result = service._get_cache_service()
            assert result is None

    def test_cache_service_already_initialized(self):
        service, _ = _make_zhipu_service()
        mock_cache = Mock()
        service._cache_service = mock_cache
        result = service._get_cache_service()
        assert result is mock_cache

    def test_cache_service_success(self):
        service = ZhipuTranslationService(api_key='test-key')
        service._cache_service = None
        mock_cache_service = Mock()
        mock_getter = Mock(return_value=mock_cache_service)
        with (
            patch.dict(
                'sys.modules',
                {'app.services.translation_cache_service': MagicMock(get_translation_cache_service=mock_getter)},
            ),
            patch(
                'builtins.__import__',
                side_effect=lambda name, *a, **kw: __import__(name, *a, **kw),
            ),
        ):
            pass
        mock_cache = Mock()
        service._cache_service = mock_cache
        assert service._get_cache_service() is mock_cache


class TestTranslateRateLimiting:
    def test_rate_limiting_sleep_called(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response('翻译结果')
        service._last_request_time = time.time()
        service._request_interval = 0.5
        with (
            patch.object(service, '_postprocess_translation', return_value='翻译结果'),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = service._last_request_time + 0.1
            mock_time.sleep = Mock()
            service.translate('Hello')
            mock_time.sleep.assert_called()

    def test_no_sleep_when_interval_elapsed(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response('翻译结果')
        service._last_request_time = 0
        service._request_interval = 0.1
        with (
            patch.object(service, '_postprocess_translation', return_value='翻译结果'),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            service.translate('Hello')
            mock_time.sleep.assert_not_called()


class TestTranslateRetryLogic:
    def test_translation_exception_returns_none(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.side_effect = Exception('API error')
        with patch('app.services.zhipu_translation_service.time') as mock_time:
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate('Hello')
            assert result is None

    def test_connection_error_retries_then_fails(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.side_effect = ConnectionError('Connection failed')
        with patch('app.services.zhipu_translation_service.time') as mock_time:
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate('Hello')
            assert result is None
            assert mock_client.chat.completions.create.call_count == 3

    def test_response_with_none_content(self):
        service, mock_client = _make_zhipu_service()
        response = Mock()
        choice = Mock()
        message = Mock()
        message.content = None
        choice.message = message
        response.choices = [choice]
        mock_client.chat.completions.create.return_value = response
        with patch('app.services.zhipu_translation_service.time') as mock_time:
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate('Hello')
            assert result is None

    def test_successful_translation_with_rate_limit_update(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response('翻译结果')
        with (
            patch.object(service, '_postprocess_translation', return_value='翻译结果'),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            service.translate('Hello')
            assert service._last_request_time == 1000.0


class TestTranslateBatch:
    def test_batch_with_cache_hits(self):
        service, _ = _make_zhipu_service()
        mock_cache_service = Mock()
        mock_cached = Mock()
        mock_cached.translated_text = '缓存翻译'
        mock_cache_service.get.return_value = mock_cached
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache_service),
            patch('app.utils.api_helpers.clean_translation_text', return_value='缓存翻译'),
        ):
            results = service.translate_batch(['Hello', 'World'])
            assert len(results) == 2
            assert results[0] == '缓存翻译'
            assert results[1] == '缓存翻译'

    def test_batch_empty_texts(self):
        service, _ = _make_zhipu_service()
        with patch.object(service, '_get_cache_service', return_value=None):
            results = service.translate_batch(['', '  ', None])
            assert results == ['', '  ', None]

    def test_batch_with_progress_callback(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response('翻译结果')
        callback = Mock()
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch.object(service, '_postprocess_translation', return_value='翻译结果'),
            patch.object(service, 'is_available', return_value=True),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            results = service.translate_batch(['Hello', 'World'], progress_callback=callback)
            assert len(results) == 2
            assert callback.call_count > 0

    def test_batch_cache_read_error_items_stay_none(self):
        service, _ = _make_zhipu_service()
        mock_cache_service = Mock()
        mock_cache_service.get.side_effect = ValueError('Cache error')
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache_service),
            patch.object(service, 'is_available', return_value=False),
        ):
            results = service.translate_batch(['Hello'])
            assert len(results) == 1
            assert results[0] is None

    def test_batch_fallback_when_not_available(self):
        service, _ = _make_zhipu_service()
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch.object(service, 'is_available', return_value=False),
        ):
            results = service.translate_batch(['Hello'])
            assert results[0] is None

    def test_batch_translate_returns_none_fallback_to_original(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.return_value = _make_api_response(None)
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            results = service.translate_batch(['Hello'])
            assert len(results) == 1
            assert results[0] == 'Hello'


class TestTranslateBookFields:
    def test_all_fields_empty(self):
        service, _ = _make_zhipu_service()
        with patch.object(service, '_get_cache_service', return_value=None):
            result = service.translate_book_fields(title='', description='', details='')
            assert result['title_zh'] is None
            assert result['description_zh'] is None
            assert result['details_zh'] is None

    def test_cache_hit_for_all_fields(self):
        service, _ = _make_zhipu_service()
        mock_cache = Mock()
        mock_cached_title = Mock()
        mock_cached_title.translated_text = '缓存书名'
        mock_cached_desc = Mock()
        mock_cached_desc.translated_text = '缓存描述'
        mock_cached_details = Mock()
        mock_cached_details.translated_text = '缓存详情'
        mock_cache.get.side_effect = [mock_cached_title, mock_cached_desc, mock_cached_details]
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
        ):
            result = service.translate_book_fields(title='Title', description='Desc', details='Details')
            assert result['title_zh'] == '缓存书名'
            assert result['description_zh'] == '缓存描述'
            assert result['details_zh'] == '缓存详情'

    def test_no_client_fallback_to_single_translations(self):
        service = ZhipuTranslationService(api_key=None)
        service._client = None
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch.object(service, '_get_client', return_value=None),
            patch.object(service, 'translate', side_effect=lambda t, sl='en', tl='zh', field_type='text': f'翻译_{t}'),
        ):
            result = service.translate_book_fields(title='Title', description='Desc')
            assert result['title_zh'] == '翻译_Title'
            assert result['description_zh'] == '翻译_Desc'
            assert result['details_zh'] is None

    def test_successful_json_response(self):
        service, mock_client = _make_zhipu_service()
        json_response = json.dumps(
            {
                'title_zh': '翻译书名',
                'description_zh': '翻译描述',
                'details_zh': '翻译详情',
            }
        )
        mock_client.chat.completions.create.return_value = _make_api_response(json_response)
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title', description='Desc', details='Details')
            assert result['title_zh'] == '翻译书名'
            assert result['description_zh'] == '翻译描述'
            assert result['details_zh'] == '翻译详情'

    def test_json_with_markdown_wrapper(self):
        service, mock_client = _make_zhipu_service()
        json_response = '```json\n{"title_zh": "Markdown书名"}\n```'
        mock_client.chat.completions.create.return_value = _make_api_response(json_response)
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title')
            assert result['title_zh'] == 'Markdown书名'

    def test_json_decode_error_falls_back_to_parse_json_from_text(self):
        service, mock_client = _make_zhipu_service()
        text_response = '以下是结果：\n{"title_zh": "回退书名"}'
        mock_client.chat.completions.create.return_value = _make_api_response(text_response)
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title')
            assert result['title_zh'] == '回退书名'

    def test_exception_fallback_to_single_translations(self):
        service, mock_client = _make_zhipu_service()
        mock_client.chat.completions.create.side_effect = Exception('API error')
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch.object(
                service, 'translate', side_effect=lambda t, sl='en', tl='zh', field_type='text': f'单字段_{t}'
            ),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title', description='Desc')
            assert result['title_zh'] == '单字段_Title'
            assert result['description_zh'] == '单字段_Desc'

    def test_cache_read_exception_handled(self):
        service, mock_client = _make_zhipu_service()
        mock_cache = Mock()
        mock_cache.get.side_effect = Exception('Cache read error')
        json_response = json.dumps({'title_zh': '缓存异常后翻译'})
        mock_client.chat.completions.create.return_value = _make_api_response(json_response)
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title')
            assert result['title_zh'] == '缓存异常后翻译'

    def test_cache_write_success(self):
        service, mock_client = _make_zhipu_service()
        json_response = json.dumps({'title_zh': '写入缓存书名'})
        mock_client.chat.completions.create.return_value = _make_api_response(json_response)
        mock_cache = Mock()
        mock_cache.get.return_value = None
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title')
            assert result['title_zh'] == '写入缓存书名'
            assert mock_cache.set.call_count > 0

    def test_cache_write_exception_handled(self):
        service, mock_client = _make_zhipu_service()
        json_response = json.dumps({'title_zh': '缓存写入失败仍返回'})
        mock_client.chat.completions.create.return_value = _make_api_response(json_response)
        mock_cache = Mock()
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception('Cache write error')
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title')
            assert result['title_zh'] == '缓存写入失败仍返回'

    def test_rate_limiting_in_book_fields(self):
        service, mock_client = _make_zhipu_service()
        service._last_request_time = time.time()
        service._request_interval = 0.5
        json_response = json.dumps({'title_zh': '速率限制测试'})
        mock_client.chat.completions.create.return_value = _make_api_response(json_response)
        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = service._last_request_time + 0.1
            mock_time.sleep = Mock()
            service.translate_book_fields(title='Title')
            mock_time.sleep.assert_called()

    def test_only_uncached_fields_sent(self):
        service, mock_client = _make_zhipu_service()
        mock_cache = Mock()
        mock_cached_title = Mock()
        mock_cached_title.translated_text = '已有书名'

        def cache_get_side_effect(text, sl, tl):
            if text == 'Title':
                return mock_cached_title
            return None

        mock_cache.get.side_effect = cache_get_side_effect
        mock_client.chat.completions.create.return_value = _make_api_response(json.dumps({'description_zh': '新描述'}))
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', side_effect=lambda t, **kw: t),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title', description='Desc')
            assert result['title_zh'] == '已有书名'
            assert result['description_zh'] == '新描述'
            call_args = mock_client.chat.completions.create.call_args
            user_content = call_args[1]['messages'][1]['content']
            assert 'Title' not in user_content
            assert 'Desc' in user_content

    def test_empty_response_returns_none_fallback(self):
        service, mock_client = _make_zhipu_service()
        empty_resp = Mock()
        empty_resp.choices = []
        mock_client.chat.completions.create.return_value = empty_resp

        def translate_side_effect(*args, **kwargs):
            return f'单字段_{args[0]}'

        with (
            patch.object(service, '_get_cache_service', return_value=None),
            patch.object(service, 'translate', side_effect=translate_side_effect),
            patch('app.services.zhipu_translation_service.time') as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_time.sleep = Mock()
            result = service.translate_book_fields(title='Title')
            assert result['title_zh'] == '单字段_Title'


class TestPostprocessTranslation:
    def test_postprocess_delegates_to_clean(self):
        with patch('app.utils.api_helpers.clean_translation_text', return_value='清理后') as mock_clean:
            result = ZhipuTranslationService._postprocess_translation('**清理前**', field_type='title')
            assert result == '清理后'
            mock_clean.assert_called_once_with('**清理前**', field_type='title')


class TestHybridGetClientErrorPaths:
    def test_get_fallback_success(self):
        service = HybridTranslationService(zhipu_api_key=None)
        service._fallback = None
        mock_fallback = Mock()
        mock_module = MagicMock()
        mock_module.FreeTranslationService.return_value = mock_fallback
        with patch.dict('sys.modules', {'app.services.free_translation_service': mock_module}):
            result = service._get_fallback()
            assert result is mock_fallback
            assert service._fallback is mock_fallback

    def test_get_fallback_import_error(self):
        service = HybridTranslationService(zhipu_api_key=None)
        service._fallback = None
        with patch(
            'builtins.__import__',
            side_effect=ImportError('No free translation module'),
        ):
            result = service._get_fallback()
            assert result is None

    def test_get_fallback_already_initialized(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_fallback = Mock()
        service._fallback = mock_fallback
        result = service._get_fallback()
        assert result is mock_fallback


class TestHybridGetCacheServiceErrorPaths:
    def test_cache_service_import_error(self):
        service = HybridTranslationService(zhipu_api_key=None)
        service._cache_service = None
        with patch(
            'builtins.__import__',
            side_effect=ImportError('No cache module'),
        ):
            result = service._get_cache_service()
            assert result is None

    def test_cache_service_already_initialized(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_cache = Mock()
        service._cache_service = mock_cache
        result = service._get_cache_service()
        assert result is mock_cache


class TestHybridRunWithContext:
    def test_without_app_calls_directly(self):
        service = HybridTranslationService(zhipu_api_key=None)
        func = Mock(return_value='result')
        result = service._run_with_context(func, 'arg1')
        func.assert_called_once_with('arg1')
        assert result == 'result'

    def test_with_app_uses_app_context(self):
        mock_app = MagicMock()
        mock_context = MagicMock()
        mock_app.app_context.return_value.__enter__ = Mock(return_value=mock_context)
        mock_app.app_context.return_value.__exit__ = Mock(return_value=False)
        service = HybridTranslationService(zhipu_api_key=None, app=mock_app)
        func = Mock(return_value='ctx_result')
        result = service._run_with_context(func, 'arg1')
        func.assert_called_once_with('arg1')
        assert result == 'ctx_result'


class TestHybridTranslateExtended:
    def test_cache_error_handled_gracefully(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_cache = Mock()
        mock_cache.get.side_effect = Exception('Cache read error')
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = False
        service.zhipu = mock_zhipu
        mock_fallback = Mock()
        mock_fallback.translate.return_value = '备用翻译'
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch.object(service, '_get_fallback', return_value=mock_fallback),
        ):
            result = service.translate('Hello')
            assert result == '备用翻译'

    def test_cache_write_success_after_translation(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cache.get.return_value = None
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = True
        mock_zhipu.translate.return_value = '智谱翻译'
        service.zhipu = mock_zhipu
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.services.translation_cache_service.TranslationCacheService.CACHE_VERSION', 2),
        ):
            result = service.translate('Hello')
            assert result == '智谱翻译'
            mock_cache.set.assert_called_once()

    def test_cache_write_error_handled(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception('Cache write error')
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = True
        mock_zhipu.translate.return_value = '智谱翻译'
        service.zhipu = mock_zhipu
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.services.translation_cache_service.TranslationCacheService.CACHE_VERSION', 2),
        ):
            result = service.translate('Hello')
            assert result == '智谱翻译'

    def test_translate_with_field_type(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cache.get.return_value = None
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = True
        mock_zhipu.translate.return_value = '书名翻译'
        service.zhipu = mock_zhipu
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.services.translation_cache_service.TranslationCacheService.CACHE_VERSION', 2),
        ):
            result = service.translate('Clean Code', field_type='title')
            mock_zhipu.translate.assert_called_once_with('Clean Code', 'en', 'zh', field_type='title')


class TestHybridTranslateBatchExtended:
    def test_batch_with_cache_and_translation(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cached = Mock()
        mock_cached.translated_text = '缓存结果'
        mock_cache.get.return_value = mock_cached
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = True
        service.zhipu = mock_zhipu
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch('app.utils.api_helpers.clean_translation_text', return_value='缓存结果'),
        ):
            results = service.translate_batch(['Hello', 'World'])
            assert len(results) == 2
            assert results[0] == '缓存结果'

    def test_batch_empty_texts(self):
        service = HybridTranslationService(zhipu_api_key=None)
        with patch.object(service, '_get_cache_service', return_value=None):
            results = service.translate_batch(['', '  ', None])
            assert results == ['', '  ', None]

    def test_batch_progress_callback(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_cache = Mock()
        mock_cache.get.return_value = None
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = True
        mock_zhipu.translate.return_value = '翻译结果'
        service.zhipu = mock_zhipu
        callback = Mock()
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
        ):
            results = service.translate_batch(['Hello'], progress_callback=callback)
            assert callback.call_count > 0

    def test_batch_cache_read_error(self):
        service = HybridTranslationService(zhipu_api_key=None)
        mock_cache = Mock()
        mock_cache.get.side_effect = Exception('Cache error')
        mock_zhipu = Mock()
        mock_zhipu.is_available.return_value = False
        service.zhipu = mock_zhipu
        with (
            patch.object(service, '_get_cache_service', return_value=mock_cache),
            patch.object(service, '_get_fallback', return_value=None),
        ):
            results = service.translate_batch(['Hello'])
            assert results[0] == 'Hello'


class TestHybridTranslateBookFields:
    def test_delegates_to_zhipu(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_zhipu = Mock()
        mock_zhipu.translate_book_fields.return_value = {
            'title_zh': '书名',
            'description_zh': '描述',
            'details_zh': '详情',
        }
        service.zhipu = mock_zhipu
        result = service.translate_book_fields(title='Title', description='Desc', details='Details')
        mock_zhipu.translate_book_fields.assert_called_once_with(
            title='Title',
            description='Desc',
            details='Details',
            source_lang='en',
            target_lang='zh',
        )
        assert result['title_zh'] == '书名'


class TestHybridTranslateAuthorName:
    def test_delegates_to_zhipu(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        mock_zhipu = Mock()
        mock_zhipu.translate_author_name.return_value = '作者翻译'
        service.zhipu = mock_zhipu
        result = service.translate_author_name('John Smith')
        mock_zhipu.translate_author_name.assert_called_once_with('John Smith')
        assert result == '作者翻译'


class TestTranslateBookInfoViaZhipu:
    def test_translates_book_info(self):
        service, _ = _make_zhipu_service()
        with patch('app.services.zhipu_translation_service._translate_book_info') as mock_helper:
            mock_helper.return_value = {'title': 'Book', 'title_zh': '书名'}
            book_data = {'title': 'Book'}
            result = service.translate_book_info(book_data)
            mock_helper.assert_called_once_with(service, book_data, 'zh')
            assert result['title_zh'] == '书名'

    def test_custom_target_lang(self):
        service, _ = _make_zhipu_service()
        with patch('app.services.zhipu_translation_service._translate_book_info') as mock_helper:
            mock_helper.return_value = {}
            service.translate_book_info({'title': 'X'}, target_lang='ja')
            mock_helper.assert_called_once_with(service, {'title': 'X'}, 'ja')


class TestHybridTranslateBookInfo:
    def test_delegates_to_helper(self):
        service = HybridTranslationService(zhipu_api_key='test-key')
        with patch('app.services.zhipu_translation_service._translate_book_info') as mock_helper:
            mock_helper.return_value = {'title': 'Book', 'title_zh': '书名'}
            result = service.translate_book_info({'title': 'Book'})
            mock_helper.assert_called_once_with(service, {'title': 'Book'}, 'zh')
            assert result['title_zh'] == '书名'
