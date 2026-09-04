"""Free translation service tests (was 0% coverage)."""

from unittest.mock import patch

from app.services.free_translation_service import FreeTranslationService, GoogleTranslationService


class TestGoogleTranslationService:
    def test_empty_text_passthrough(self):
        svc = GoogleTranslationService()
        assert svc.translate('') == ''
        assert svc.translate('   ') == '   '

    def test_missing_client_returns_none(self):
        svc = GoogleTranslationService()
        with patch('deep_translator.GoogleTranslator', side_effect=ImportError('missing')):
            # 直接触发 _get_client 的 ImportError 分支
            svc._client = None
            result = svc.translate('hello')
            assert result is None

    @patch('deep_translator.GoogleTranslator')
    def test_translate_success(self, mock_gt):
        # from deep_translator import GoogleTranslator -> mock_gt (the class)
        # client_class(source=.., target=..) -> mock_gt.return_value
        # .translate(text) -> mock_gt.return_value.translate
        mock_gt.return_value.translate.return_value = '你好'

        svc = GoogleTranslationService(delay=0)
        result = svc.translate('hello', 'en', 'zh')
        assert result == '你好'
        mock_gt.assert_called_once_with(source='en', target='zh-CN')

    @patch('deep_translator.GoogleTranslator')
    def test_translate_exhausts_retries(self, mock_gt):
        mock_gt.return_value.translate.side_effect = Exception('boom')

        svc = GoogleTranslationService(delay=0)
        result = svc.translate('hello')
        assert result is None


class TestFreeTranslationService:
    def test_empty_text(self):
        svc = FreeTranslationService()
        assert svc.translate('') == ''

    @patch.object(GoogleTranslationService, 'translate', return_value=None)
    def test_fallback_none(self, mock_google):
        svc = FreeTranslationService()
        assert svc.translate('hello') is None

    @patch.object(GoogleTranslationService, 'translate', return_value='你好')
    def test_google_result(self, mock_google):
        svc = FreeTranslationService()
        assert svc.translate('hello') == '你好'

    @patch.object(GoogleTranslationService, 'translate', side_effect=lambda t, s='en', z='zh': None)
    def test_batch_fallback_to_original(self, mock_google):
        svc = FreeTranslationService()
        results = svc.translate_batch(['a', 'b'], max_workers=2)
        assert results == ['a', 'b']
