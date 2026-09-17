"""占位串清单单一真相源的回归锁。

背景
----
「没有内容」的占位串（`'No detailed description available.'` / `'暂无详细描述'` 等）
语义上等于 NULL，却是**真值**。历史上它们以**四份各自维护的清单**散落在
`api_helpers` / `book_language_pack` / 模板 / 脚本里，改一处漏一处：

- 模板把占位串归一化成空 → 详情页「详细信息」标签整块消失；
- 下游 `needs_details = details 有值 and != 占位串` 恒为假 → 补齐路径被永久封死。

现在唯一来源是 `app/utils/api_helpers.PLACEHOLDER_TEXTS`：

| 消费方 | 取得方式 |
| --- | --- |
| Python（写入边界 / 判定） | `strip_placeholder()` / `is_placeholder_text()` |
| 模板 | 注入的 Jinja 全局 `PLACEHOLDER_TEXTS`（`app/__init__.py` 注册） |
| 前端 JS | 无法 import Python → `static/mobile/js/mobile.js` 保留**镜像**，由本文件断言逐字一致 |

本文件锁住上述派生关系：任何一处回退成"自己的字面量清单"，这里就红。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.utils.api_helpers import PLACEHOLDER_TEXTS

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
SCRIPTS = ROOT / 'scripts'
TEMPLATES = ROOT / 'templates'
MOBILE_JS = ROOT / 'static' / 'mobile' / 'js' / 'mobile.js'

#: 模板里不允许再出现的「第二份清单」写法（含历史写法，防止被复制回来）
FORBIDDEN_TEMPLATE_PATTERNS = (
    '_detail_placeholders',
    "not in ('No summary available.",
    "!= 'No summary available.'",
)


def _template_files() -> list[Path]:
    return sorted(TEMPLATES.rglob('*.html'))


class TestPythonSideDerivesFromTheCanonicalSet:
    def test_book_language_pack_derives_instead_of_redeclaring(self):
        src = (APP / 'services' / 'book_language_pack.py').read_text(encoding='utf-8')
        assert '_PLACEHOLDERS = PLACEHOLDER_TEXTS' in src, '语言包应派生自单一真相源'
        assert 'PLACEHOLDER_TEXTS, ' in src or '(PLACEHOLDER_TEXTS' in src or 'PLACEHOLDER_TEXTS,' in src, (
            '语言包应显式 import PLACEHOLDER_TEXTS'
        )

    def test_language_pack_set_is_identical_to_the_canonical_set(self):
        from app.services.book_language_pack import BookLanguagePack

        assert BookLanguagePack._PLACEHOLDERS == PLACEHOLDER_TEXTS

    def test_backfill_script_derives_instead_of_redeclaring(self):
        src = (SCRIPTS / 'backfill_book_titles.py').read_text(encoding='utf-8')
        assert '_PLACEHOLDER_NOISE = PLACEHOLDER_TEXTS | _DETAIL_NOISE_EXTRA' in src, (
            '回填脚本应派生共享占位串，只额外声明详情字段特有的噪音词'
        )

    def test_batch_translate_uses_the_predicate(self):
        src = (SCRIPTS / 'batch_translate.py').read_text(encoding='utf-8')
        assert 'is_placeholder_text' in src, '批量翻译应用统一判定函数'
        assert "not in ['No summary available." not in src, '不该再有内联的字面量列表'
        assert "not in ['No detailed description available." not in src, '不该再有内联的字面量列表'

    def test_google_books_client_does_not_fabricate_a_placeholder(self):
        src = (APP / 'services' / 'google_books_client.py').read_text(encoding='utf-8')
        for literal in PLACEHOLDER_TEXTS:
            assert f"else '{literal}'" not in src, f'抓取侧不该凭空写回占位串 {literal!r}'


class TestTemplateSideUsesTheInjectedGlobal:
    def test_jinja_global_is_registered(self):
        src = (APP / '__init__.py').read_text(encoding='utf-8')
        assert "jinja_env.globals['PLACEHOLDER_TEXTS'] = PLACEHOLDER_TEXTS" in src, (
            '模板要靠注入的 Jinja 全局判定，注册这行不能被删'
        )

    def test_no_template_redeclares_its_own_list(self):
        offenders: list[str] = []
        for path in _template_files():
            text = path.read_text(encoding='utf-8')
            for pattern in FORBIDDEN_TEMPLATE_PATTERNS:
                if pattern in text:
                    offenders.append(f'{path.relative_to(ROOT)}: {pattern}')
        assert not offenders, '模板又自建了占位串清单：\n  ' + '\n  '.join(offenders)

    def test_templates_that_normalise_details_use_the_global(self):
        """做过占位串归一化的模板必须引用注入的全局，而不是空手判定。"""
        for path in _template_files():
            text = path.read_text(encoding='utf-8')
            if 'PLACEHOLDER_TEXTS' not in text:
                continue
            assert 'in PLACEHOLDER_TEXTS' in text, f'{path.relative_to(ROOT)} 引用了全局却没用于判定'


class TestFrontendMirrorStaysInSync:
    """JS 无法 import Python：`mobile.js` 保留镜像，必须逐字与 Python 集合一致。"""

    @staticmethod
    def _js_placeholders() -> set[str]:
        src = MOBILE_JS.read_text(encoding='utf-8')
        match = re.search(r'const PLACEHOLDERS\s*=\s*\[([^\]]*)\]', src)
        assert match, 'mobile.js 里的 PLACEHOLDERS 镜像不见了'
        values: set[str] = set()
        for item in re.finditer(r"""['"]([^'"]*)['"]""", match.group(1)):
            values.add(item.group(1))
        return values

    def test_mirror_is_identical_to_the_canonical_set(self):
        js = self._js_placeholders()
        assert js == set(PLACEHOLDER_TEXTS), (
            '前端镜像与 Python 单一真相源漂移：\n'
            f'  仅 JS 有: {sorted(js - set(PLACEHOLDER_TEXTS))}\n'
            f'  仅 Python 有: {sorted(set(PLACEHOLDER_TEXTS) - js)}'
        )


class TestCanonicalSetShape:
    """集合本身的最小契约：覆盖抓取侧两种语言，且判定函数行为一致。"""

    def test_contains_both_languages(self):
        assert any(re.search(r'[\u4e00-\u9fff]', t) for t in PLACEHOLDER_TEXTS), '缺中文占位串'
        assert any(t.startswith('No ') for t in PLACEHOLDER_TEXTS), '缺英文占位串'

    def test_is_json_serialisable_for_debug_dumps(self):
        assert json.loads(json.dumps(sorted(PLACEHOLDER_TEXTS))) == sorted(PLACEHOLDER_TEXTS)
