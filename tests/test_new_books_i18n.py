"""
新书推介页面 i18n 修复测试

覆盖：
1. NewBook.to_dict() 包含 publisher_name_en 字段
2. /new-books SSR 页面包含必要的 data-i18n 属性
3. /new-books 页面 publisher 侧边栏有 data-pub-name-zh / data-pub-name-en
4. translations.js 包含新书页相关 key（min.js 已删除）
5. zh.po + en.po 包含新书页相关 msgid
6. .mo 文件已编译
7. v0.9.62 详情页 i18n 修复 + 切语言实时刷新修复
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / 'templates' / 'new_books.html'
DETAIL_TPL = ROOT / 'templates' / 'new_book_detail.html'
MACROS = ROOT / 'templates' / '_macros.html'
TR_SRC = ROOT / 'static' / 'js' / 'translations.js'
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


# ============================================================
# v0.9.62 修复回归测试
# ============================================================

NB_DETAIL_KEYS = [
    'nb_detail_label_isbn',
    'nb_detail_description_title',
    'nb_detail_no_description',
]


class TestNewBookDetailI18n:
    """v0.9.62 修复：新书详情页 i18n 补全（v0.9.58 漏修的盲点）。"""

    def test_translations_has_detail_keys(self):
        """translations.js 包含详情页 3 个 i18n 键（min.js 已随 P0-4 删除）。"""
        src = _read(TR_SRC)
        for k in NB_DETAIL_KEYS:
            assert f"'{k}'" in src, f'translations.js 缺 {k}'

    def test_detail_template_has_i18n_attrs(self):
        """详情页模板包含所有 i18n 数据属性。"""
        text = _read(DETAIL_TPL)
        # 标题/作者 data-en / data-zh
        assert 'class="detail-title" data-en=' in text, '标题缺 data-en'
        assert 'data-zh=' in text, '标题缺 data-zh'
        assert 'class="detail-author" data-en=' in text, '作者缺 data-en'
        # ISBN 标签 data-i18n
        assert 'data-i18n="nb_detail_label_isbn"' in text, 'ISBN 标签缺 data-i18n'
        # 出版社 data-pub-name
        assert 'data-pub-name-zh=' in text, '出版社缺 data-pub-name-zh'
        assert 'data-pub-name-en=' in text, '出版社缺 data-pub-name-en'
        # 简介 data-en / data-zh + no-desc 占位
        assert 'id="detail-description"' in text, '简介容器 id 缺失'
        assert 'data-no-desc-zh=' in text, '简介缺 data-no-desc-zh'
        assert 'data-no-desc-en=' in text, '简介缺 data-no-desc-en'
        # 简介标题 data-i18n
        assert 'data-i18n="nb_detail_description_title"' in text, '简介标题缺 data-i18n'

    def test_detail_template_has_apply_function(self):
        """详情页有 applyNewBookDetailLanguage 函数和 languagechange 监听。"""
        text = _read(DETAIL_TPL)
        assert 'function applyNewBookDetailLanguage' in text
        assert "addEventListener('languagechange'" in text
        assert 'applyNewBookDetailLanguage(e.detail.language)' in text

    def test_detail_template_uses_translated_fallback(self):
        """'暂无简介' 占位用 {{ _() }} 翻译（SSR 走 Flask-Babel）。"""
        text = _read(DETAIL_TPL)
        # 硬编码的"暂无简介"应该被 _() 包裹
        assert "or _('暂无简介')" in text or "or {{ _('暂无简介') }}" in text, (
            "详情页 '暂无简介' 占位未走 Flask-Babel，英文 SSR 模式会显示中文"
        )

    def test_en_po_has_isbn_translated(self):
        """v0.9.62 修复：en.po 中 ISBN 翻译不能为空。"""
        pairs = _po_pairs(_read(EN_PO))
        v = pairs.get('ISBN', '')
        assert v and v.strip() == 'ISBN', f'ISBN 在 en.po 翻译为空（实际: {v!r}），会导致英文模式 ISBN 标签空白'


class TestApplyNewBooksLanguageNoMoreNoop:
    """v0.9.62 修复：applyNewBooksLanguage 末尾的 noop 死代码，必须触发实际重渲染。"""

    def test_no_comment_only_ending(self):
        """applyNewBooksLanguage 末尾不能只有注释（v0.9.58 的 noop 死代码）。"""
        text = _read(TPL)
        # 找到 applyNewBooksLanguage 函数体
        m = re.search(
            r'function\s+applyNewBooksLanguage\s*\([^)]*\)\s*\{(.+?)\n\}',
            text,
            re.DOTALL,
        )
        assert m, 'applyNewBooksLanguage 函数未找到'
        body = m.group(1)
        # 末尾 200 字符内必须有 BookI18n.applyLanguage 或 registerAll 的真实调用
        tail = body[-300:]
        assert 'BookI18n.applyLanguage' in tail, (
            'applyNewBooksLanguage 末尾仍是 noop 死代码（C2 未修）。'
            '需要调用 BookI18n.applyLanguage(lang) 让已加载的卡片标题/作者/简介实时切换。'
        )

    def test_languagechange_handler_has_card_guard(self):
        """languagechange 监听器应有"已加载卡片"守卫（L4 修复：避免空列表时多余 API 请求）。"""
        text = _read(TPL)
        # 找到 languagechange 监听器，允许多层嵌套花括号
        m = re.search(
            r"addEventListener\('languagechange',\s*function[\s\S]+?\n\}\);",
            text,
        )
        assert m, 'languagechange 监听器未找到'
        handler = m.group(0)
        # 必须有 booksContainer 检查
        assert 'booksContainer' in handler, (
            'languagechange 监听器未加 booksContainer 守卫（L4 未修），空列表时仍会触发多余 loadBooks() 请求'
        )

    def test_render_books_always_apply_language(self):
        """renderBooks 末尾的 BookI18n.applyLanguage 不应有 'zh' 守卫（L6 修复）。"""
        text = _read(TPL)
        # 找 renderBooks 函数最外层花括号配对
        start = text.find('function renderBooks')
        assert start != -1, 'renderBooks 函数未找到'
        depth = 0
        i = start
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[start : i + 1]
        # 不应再有 if (currentLanguage === 'zh') 这种条件
        assert "if (currentLanguage === 'zh')" not in body, (
            "renderBooks 末尾仍是 'zh only' 守卫（L6 未修），"
            '英文模式下不会应用 BookI18n.applyLanguage，导致英文首屏 SSR 后切语言失效'
        )


class TestPublisherFilterFirstOption:
    """v0.9.62 修复：publisher-filter 第一个 option（'全部出版社'）也必须有 data-pub-name-*。"""

    def test_first_option_has_bilingual_attrs(self):
        """C4 修复：第一个 option 必须有 data-pub-name-zh / data-pub-name-en。"""
        text = _read(TPL)
        # 第一个 option 块（value=""）
        m = re.search(
            r'<select\s+id="publisher-filter"[^>]*>.*?<option\s+value=""\s*([^>]*)>(.*?)</option>',
            text,
            re.DOTALL,
        )
        assert m, 'publisher-filter 第一个 option 未找到'
        attrs = m.group(1)
        assert 'data-pub-name-zh=' in attrs, (
            "C4 未修：'全部出版社' 第一个 option 缺 data-pub-name-zh，"
            '切换语言后该 option 文本不会刷新（依赖 SSR 翻译，'
            '但 SSR 是请求时决定的，用户切语言后该值不会变）'
        )
        assert 'data-pub-name-en=' in attrs, '第一个 option 缺 data-pub-name-en'

    def test_apply_new_books_language_handles_all_options(self):
        """v0.9.63: applyNewBooksLanguage 委托给通用化 BookI18n.applyPublisherLanguage。"""
        text = _read(TPL)
        start = text.find('function applyNewBooksLanguage')
        assert start != -1, 'applyNewBooksLanguage 函数未找到'
        depth = 0
        i = start
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[start : i + 1]
        # v0.9.63: 委托给通用化 BookI18n.applyPublisherLanguage，不再硬编码 publisher-filter
        assert 'BookI18n.applyPublisherLanguage' in body, (
            'v0.9.63: applyNewBooksLanguage 没有委托给通用化的 BookI18n.applyPublisherLanguage'
        )
        # 兜底：退化实现仍要处理 data-pub-name-zh 元素
        assert 'data-pub-name-zh' in body, 'applyNewBooksLanguage 没有读取 data-pub-name-zh'
