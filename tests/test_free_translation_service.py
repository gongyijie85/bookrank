"""Free translation service tests (was 0% coverage, fixed for removed dep).

deep-translator was intentionally removed (PYSEC-2022-252 supply-chain
poisoning, see SECURITY.md). Tests inject a fake module via sys.modules to
simulate "installed" for the translation paths, and test the real degraded
path (module missing -> None) directly.
"""

import builtins
import sys
import types
from unittest.mock import patch

from app.services.free_translation_service import FreeTranslationService, GoogleTranslationService


class TestGoogleTranslationService:
    def test_empty_text_passthrough(self):
        svc = GoogleTranslationService()
        assert svc.translate('') == ''
        assert svc.translate('   ') == '   '

    def test_missing_client_returns_none(self):
        # 模拟 deep-translator 未安装（供应链投毒后刻意移除：生产/CI 环境即如此）
        sys.modules.pop('deep_translator', None)
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name.startswith('deep_translator'):
                raise ImportError('模拟 deep-translator 缺失')
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=_fake_import):
            svc = GoogleTranslationService()
            assert svc._get_client() is None
            assert svc.translate('hello') is None

    def test_translate_success_with_fake_module(self):
        # 模拟 deep-translator 已安装（sys.modules 注入）
        fake_mod = types.ModuleType('deep_translator')

        class _FakeTranslator:
            def __init__(self, source='', target=''):
                self._source = source
                self._target = target

            def translate(self, text):
                return '你好'

        fake_mod.GoogleTranslator = _FakeTranslator
        sys.modules['deep_translator'] = fake_mod
        try:
            svc = GoogleTranslationService(delay=0)
            result = svc.translate('hello', 'en', 'zh')
            assert result == '你好'
        finally:
            sys.modules.pop('deep_translator', None)

    def test_translate_exhausts_retries_with_fake_module(self):
        fake_mod = types.ModuleType('deep_translator')

        class _BoomTranslator:
            def __init__(self, source='', target=''):
                pass

            def translate(self, text):
                raise Exception('boom')

        fake_mod.GoogleTranslator = _BoomTranslator
        sys.modules['deep_translator'] = fake_mod
        try:
            svc = GoogleTranslationService(delay=0)
            result = svc.translate('hello')
            assert result is None
        finally:
            sys.modules.pop('deep_translator', None)


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
