"""The configured provider follows the owner's selected no-cost translation channel."""

import runpy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def test_default_provider_is_zhipu_but_can_be_explicitly_overridden(monkeypatch):
    with patch('dotenv.load_dotenv'):
        monkeypatch.delenv('TRANSLATION_PROVIDER', raising=False)
        assert runpy.run_path(str(ROOT / 'app/config.py'))['Config'].TRANSLATION_PROVIDER == 'zhipu'
        monkeypatch.setenv('TRANSLATION_PROVIDER', 'siliconflow')
        assert runpy.run_path(str(ROOT / 'app/config.py'))['Config'].TRANSLATION_PROVIDER == 'siliconflow'


def test_render_blueprint_keeps_the_selected_provider():
    text = (ROOT / 'render.yaml').read_text(encoding='utf-8')
    assert '- key: TRANSLATION_PROVIDER\n        value: zhipu' in text
    assert '- key: ZHIPU_API_KEY\n        sync: false' in text
