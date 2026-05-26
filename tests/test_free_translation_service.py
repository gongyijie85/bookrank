"""免费翻译服务测试"""

from unittest.mock import MagicMock, patch

from app.services.free_translation_service import FreeTranslationService, GoogleTranslationService


class TestGoogleTranslationService:
    def test_empty_text(self):
        svc = GoogleTranslationService()
        assert svc.translate('') == ''
        assert svc.translate('   ') == '   '

    @patch.object(GoogleTranslationService, '_get_client', return_value=None)
    def test_no_client(self, mock_client):
        svc = GoogleTranslationService()
        assert svc.translate('hello') is None

    @patch.object(GoogleTranslationService, '_get_client')
    def test_translate_success(self, mock_get_client):
        mock_translator_class = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate.return_value = '你好'
        mock_translator_class.return_value = mock_translator
        mock_get_client.return_value = mock_translator_class

        svc = GoogleTranslationService(delay=0)
        result = svc.translate('hello')
        assert result == '你好'

    @patch.object(GoogleTranslationService, '_get_client')
    def test_translate_exception_then_success(self, mock_get_client):
        mock_translator_class = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate.side_effect = [Exception('fail'), '你好']
        mock_translator_class.return_value = mock_translator
        mock_get_client.return_value = mock_translator_class

        svc = GoogleTranslationService(delay=0)
        with patch('app.services.free_translation_service.time.sleep'):
            result = svc.translate('hello')
        assert result == '你好'

    @patch.object(GoogleTranslationService, '_get_client')
    def test_translate_all_retries_fail(self, mock_get_client):
        mock_translator_class = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate.side_effect = Exception('always fail')
        mock_translator_class.return_value = mock_translator
        mock_get_client.return_value = mock_translator_class

        svc = GoogleTranslationService(delay=0)
        with patch('app.services.free_translation_service.time.sleep'):
            result = svc.translate('hello')
        assert result is None

    @patch.object(GoogleTranslationService, '_get_client')
    def test_translate_returns_empty(self, mock_get_client):
        mock_translator_class = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate.return_value = ''
        mock_translator_class.return_value = mock_translator
        mock_get_client.return_value = mock_translator_class

        svc = GoogleTranslationService(delay=0)
        result = svc.translate('hello')
        assert result is None

    def test_get_client_import_error(self):
        svc = GoogleTranslationService()
        with (
            patch.dict('sys.modules', {'deep_translator': None}),
            patch('builtins.__import__', side_effect=ImportError('no module')),
        ):
            result = svc._get_client()
            assert result is None

    @patch.object(GoogleTranslationService, '_get_client')
    def test_lang_mapping(self, mock_get_client):
        mock_translator_class = MagicMock()
        mock_translator = MagicMock()
        mock_translator.translate.return_value = '结果'
        mock_translator_class.return_value = mock_translator
        mock_get_client.return_value = mock_translator_class

        svc = GoogleTranslationService(delay=0)
        svc.translate('hello', source_lang='zh', target_lang='en')
        mock_translator_class.assert_called_with(source='zh-CN', target='en')


class TestFreeTranslationService:
    @patch.object(GoogleTranslationService, 'translate', return_value='你好')
    def test_translate_success(self, mock_translate):
        svc = FreeTranslationService()
        result = svc.translate('hello')
        assert result == '你好'

    def test_translate_empty(self):
        svc = FreeTranslationService()
        assert svc.translate('') == ''

    @patch.object(GoogleTranslationService, 'translate', return_value=None)
    def test_translate_failure(self, mock_translate):
        svc = FreeTranslationService()
        result = svc.translate('hello')
        assert result is None

    @patch.object(FreeTranslationService, 'translate')
    def test_translate_batch(self, mock_translate):
        mock_translate.side_effect = lambda t, *a, **kw: f'翻译:{t}'

        svc = FreeTranslationService()
        results = svc.translate_batch(['hello', 'world'])
        assert len(results) == 2
