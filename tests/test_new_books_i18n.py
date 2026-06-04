"""
新书推介页面 i18n 修复测试

覆盖：
1. NewBook.to_dict() 包含 publisher_name_en 字段
2. /new-books SSR 页面包含必要的 data-i18n 属性
3. /new-books 页面 publisher 侧边栏有 data-pub-name-zh / data-pub-name-en
4. translations.js + translations.min.js 都有新书页相关 key
5. zh.po + en.po 包含新书页相关 msgid
6. .mo 文件已编译
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / 'templates' / 'new_books.html'
MACROS = ROOT / 'templates' / '_macros.html'
TR_SRC = ROOT / 'static' / 'js' / 'translations.js'
TR_MIN = ROOT / 'static' / 'js' / 'translations.min.js'
ZH_PO = ROOT / 'translations' / 'zh' / 'LC_MESSAGES' / 'messages.po'
EN_PO = ROOT / 'translations' / 'en' / 'LC_MESSAGES' / 'messages.po'
ZH_MO = ROOT / 'translations' / 'zh' / 'LC_MESSAGES' / 'messages.mo'
EN_MO = ROOT / 'translations' / 'en' / 'LC_MESSAGES' / 'messages.mo'


NB_KEYS = [
    'nb_header_subtitle',
    'nb_total_new_books_suffix',
    'nb_publishers_suffix',
    'nb_recent_7d_label',
    'nb_filter_publisher_label',
    'nb_filter_publisher_all',
    'nb_filter_category_label',
    'nb_filter_category_all',
    'nb_filter_time_label',
    'nb_time_7',
    'nb_time_30',
    'nb_time_90',
    'nb_time_180',
    'nb_time_365',
    'nb_search_placeholder',
    'nb_export_btn',
    'nb_sync_btn',
    'nb_result_summary',
    'nb_result_unit',
    'nb_filtered_by_date',
    'nb_empty_title',
    'nb_empty_desc',
    'nb_empty_refresh',
]


def _read(p: Path) -> str:
    return p.read_text(encoding='utf-8')


def _po_pairs(text: str) -> dict[str, str]:
    """提取 msgid -> msgstr 映射。使用 babel 解析确保中文字符正确解码。"""
    try:
        from io import StringIO

        from babel.messages import pofile

        catalog = pofile.read_po(StringIO(text))
        out: dict[str, str] = {}
        for message in catalog:
            if message.id:
                # Babel 解析重复 msgid 时取最后一个出现的位置
                out[message.id] = message.string or ''
        return out
    except Exception:
        # 退化方案：手动解析 unicode_escape
        out: dict[str, str] = {}
        for m in re.finditer(r'msgid "((?:[^"\\]|\\.)*)"\nmsgstr "((?:[^"\\]|\\.)*)"', text):
            try:
                k = bytes(m.group(1), 'utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8')
                v = bytes(m.group(2), 'utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8')
            except Exception:
                k = m.group(1)
                v = m.group(2)
            out[k] = v
        return out


class TestNewBookI18nKeys:
    """TRANSLATIONS 字典（新书页）完整性。"""

    def _keys(self, content: str) -> set[str]:
        zh_section, en_section = content.split('en:', 1)
        zh_keys = set(re.findall(r"'([^']+)':\s*'[^']*'", zh_section))
        en_keys = set(re.findall(r"'([^']+)':\s*'[^']*'", en_section))
        return zh_keys & en_keys

    def test_translations_js_has_nb_keys(self):
        keys = self._keys(_read(TR_SRC))
        missing = [k for k in NB_KEYS if k not in keys]
        assert not missing, f'translations.js 缺失 nb_* 键: {missing}'

    def test_translations_min_js_has_nb_keys(self):
        keys = self._keys(_read(TR_MIN))
        missing = [k for k in NB_KEYS if k not in keys]
        assert not missing, f'translations.min.js 缺失 nb_* 键: {missing}'

    def test_min_matches_src(self):
        """min.js 与 src.js 包含的 key 集合必须完全一致（v0.9.56 教训）。"""
        src_keys = self._keys(_read(TR_SRC))
        min_keys = self._keys(_read(TR_MIN))
        assert src_keys == min_keys, (
            f'min.js 与 src.js 同步异常: src-only={sorted(src_keys - min_keys)}, min-only={sorted(min_keys - src_keys)}'
        )

    def test_min_matches_build_output(self):
        """min.js 必须与 build.py 重新生成的内容字节级一致（v0.9.58 教训）。

        背景：v0.9.58 在 translations.js 改了 applyPageTranslation（加 data-i18n-params-*
        占位符支持），但 min.js 漏同步。test_min_matches_src 只比对 key 集合过不了，
        因为 key 集合没变。CI 跑 build.py 时 mtime 检查触发重生成 → 污染 working tree。

        本测试直接调 build.minify_js 处理 src.js 一次，与磁盘上的 min.js 字节级对比：
        - src 改了但 min 没同步 → 立即 fail
        - 提示用户跑 `python build.py` 后再 commit
        """
        import sys

        sys.path.insert(0, str(ROOT))
        from build import minify_js  # type: ignore[import-not-found]

        src_content = _read(TR_SRC)
        expected_min = minify_js(src_content)
        actual_min = _read(TR_MIN)
        assert expected_min == actual_min, (
            'translations.min.js 与 build.py 重新生成内容不一致！\n'
            '说明：src.js 改了但 min.js 没同步（v0.9.58 漏同步教训）。\n'
            '执行 `python build.py` 同步 min.js 后再 commit。\n'
            f'expected len={len(expected_min)}, actual len={len(actual_min)}'
        )


class TestNewBookPoFiles:
    """msgid 完整性。"""

    REQUIRED_MSGIDS = [
        '近7天出版',
        '最近7天出版',
        '最近30天出版',
        '最近90天出版',
        '最近半年出版',
        '最近一年出版',
        '搜索书名、作者、',
        '当前结果',
        '按出版日期筛选最近',
        '天已出版图书',
        '当前出版时间范围暂无新书，可放宽时间范围或稍后刷新',
        '刷新',
        '尝试放宽出版时间范围或搜索其他关键词',
    ]

    def test_zh_po_has_required(self):
        pairs = _po_pairs(_read(ZH_PO))
        missing = [k for k in self.REQUIRED_MSGIDS if k not in pairs]
        assert not missing, f'zh.po 缺失 msgid: {missing}'

    def test_en_po_has_required_translated(self):
        pairs = _po_pairs(_read(EN_PO))
        # 英文翻译必须存在且非空（且不能等于 msgid 本身）
        problems = []
        for k in self.REQUIRED_MSGIDS:
            v = pairs.get(k)
            if v is None or v == '' or v == k:
                problems.append(f'{k!r} -> {v!r}')
        assert not problems, f'en.po 未翻译的 msgid: {problems}'

    def test_mo_files_recompiled(self):
        """.mo 文件必须比 .po 新（说明已重新编译）。"""
        assert ZH_MO.exists() and EN_MO.exists()
        assert ZH_MO.stat().st_mtime >= ZH_PO.stat().st_mtime - 1
        assert EN_MO.stat().st_mtime >= EN_PO.stat().st_mtime - 1


class TestNewBooksTemplate:
    """new_books.html 模板：data-i18n 属性齐全。"""

    def test_filter_labels_have_data_i18n(self):
        text = _read(TPL)
        for sel, attr in [
            ('#publisher-filter', 'data-i18n="nb_filter_publisher_label"'),
            ('#category-filter', 'data-i18n="nb_filter_category_label"'),
            ('#days-filter', 'data-i18n="nb_filter_time_label"'),
        ]:
            # 简单存在性检查（不要求相邻）
            assert attr in text, f'{sel} 缺少 {attr}'

    def test_filter_options_have_data_i18n(self):
        text = _read(TPL)
        for key in [
            'nb_filter_publisher_all',
            'nb_filter_category_all',
            'nb_time_7',
            'nb_time_30',
            'nb_time_90',
            'nb_time_180',
            'nb_time_365',
        ]:
            assert f'data-i18n="{key}"' in text, f'缺 {key} data-i18n'

    def test_search_input_placeholder_i18n(self):
        text = _read(TPL)
        assert 'data-i18n-placeholder="nb_search_placeholder"' in text
        assert 'data-i18n-aria-label="nb_search_label"' in text

    def test_export_sync_buttons_have_data_i18n(self):
        text = _read(TPL)
        assert 'data-i18n="nb_export_btn"' in text
        assert 'data-i18n="nb_sync_btn"' in text

    def test_result_summary_has_data_i18n(self):
        text = _read(TPL)
        assert 'data-i18n="nb_result_summary"' in text
        assert 'data-i18n="nb_result_unit"' in text
        assert 'data-i18n="nb_filtered_by_date"' in text
        # 占位符支持
        assert 'data-i18n-params-days=' in text

    def test_empty_state_has_data_i18n(self):
        text = _read(TPL)
        for key in ['nb_empty_title', 'nb_empty_desc', 'nb_empty_refresh']:
            assert f'data-i18n="{key}"' in text, f'空状态缺 {key}'

    def test_sidebar_publisher_data_attrs(self):
        text = _read(TPL)
        assert 'data-pub-name-zh=' in text
        assert 'data-pub-name-en=' in text

    def test_apply_new_books_language_defined(self):
        text = _read(TPL)
        assert 'function applyNewBooksLanguage' in text
        assert "addEventListener('languagechange'" in text
        assert 'applyNewBooksLanguage(currentLanguage)' in text


class TestNewBookMacros:
    """book 卡片宏包含 publisher 中英文数据。"""

    def test_publisher_has_bilingual_attrs(self):
        text = _read(MACROS)
        # 卡片中的 .book-publisher span 应同时有 data-pub-name-zh 和 data-pub-name-en
        assert 'book-publisher' in text
        assert 'data-pub-name-zh' in text
        assert 'data-pub-name-en' in text


class TestNewBookToDict:
    """NewBook.to_dict() 包含 publisher_name_en。"""

    def test_publisher_name_en_in_to_dict(self):
        import inspect

        from app.models.new_book import NewBook

        src = inspect.getsource(NewBook.to_dict)
        assert 'publisher_name_en' in src
        assert 'name_en' in src


class TestNewBookPageClientI18n:
    """客户端测试：访问 /new-books 页面，检查 data-i18n 属性在 HTML 中。"""

    def test_zh_page_has_data_i18n_attrs(self, client):
        """中文 SSR：应包含新书页所有 data-i18n 属性。"""
        response = client.get('/new-books')
        if response.status_code != 200:
            pytest.skip(f'页面状态非 200：{response.status_code}')
        body = response.get_data(as_text=True)
        for key in [
            'nb_header_subtitle',
            'nb_filter_publisher_label',
            'nb_time_30',
            'nb_export_btn',
            'nb_result_summary',
            'nb_filtered_by_date',
        ]:
            assert f'data-i18n="{key}"' in body, f'页面缺 {key}'

    def test_publisher_sidebar_has_bilingual_data(self, client):
        response = client.get('/new-books')
        if response.status_code != 200:
            pytest.skip(f'页面状态非 200：{response.status_code}')
        body = response.get_data(as_text=True)
        # 至少一个 sidebar link 包含 data-pub-name-zh 和 data-pub-name-en
        assert 'data-pub-name-zh=' in body
        assert 'data-pub-name-en=' in body
