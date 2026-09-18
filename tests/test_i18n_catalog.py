"""English catalogue completeness — the guard against Chinese leaking into the English UI.

Chinese reaches the English UI through two mechanisms, both silent:

1. **Empty msgstr** — gettext falls back to the Chinese msgid.
2. **Fuzzy entry** — `pybabel compile` *skips* fuzzy entries, so a translation that exists in
   the .po never reaches the .mo. The entry looks translated in the .po and still renders
   Chinese at runtime. 38 entries were in exactly this state.

A third mechanism is client-side: `translations.js` writes `aria-label` / `placeholder` /
`title` from `t(key)` unconditionally, so a key the dictionary does not define lands in the
attribute verbatim (a screen reader reads "footer_sitemap").

This file asserts the invariants, not the current contents, so it keeps holding as strings
are added.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EN_PO = ROOT / 'translations' / 'en' / 'LC_MESSAGES' / 'messages.po'
JS = ROOT / 'static' / 'js' / 'translations.js'
TEMPLATES = ROOT / 'templates'

# CJK ideographs, CJK punctuation, fullwidth forms
CJK = re.compile(r'[\u3000-\u303f\u4e00-\u9fff\uff01-\uff60]')

# Shown untranslated in a language picker on purpose (the English UI lists the Chinese
# option in Chinese, as the Chinese UI lists "English" in English).
ENDONYM_ALLOWLIST = {'简体中文'}


# PO string escapes -> the character they stand for. Without this, `msgstr "\" cover"` parses
# as the two characters `\"` and can never equal what gettext returns from the .mo.
_PO_ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}


def _unescape(value: str) -> str:
    return re.sub(r'\\(.)', lambda m: _PO_ESCAPES.get(m.group(1), m.group(1)), value)


def parse_po(path: Path) -> list[dict]:
    """Return live (non-obsolete) entries: {msgid, msgstr, flags}."""
    lines = path.read_text(encoding='utf-8').split('\n')
    out: list[dict] = []
    flags: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#~'):
            i += 1
            continue
        if line.startswith('#,'):
            flags = [f.strip() for f in line[2:].split(',')]
            i += 1
            continue
        if line.startswith('msgid '):

            def join(k: int) -> tuple[str, int]:
                parts = re.findall(r'"((?:[^"\\]|\\.)*)"', lines[k].split(' ', 1)[1])
                j = k + 1
                while j < len(lines) and lines[j].startswith('"'):
                    parts += re.findall(r'"((?:[^"\\]|\\.)*)"', lines[j])
                    j += 1
                return _unescape(''.join(parts)), j

            mid, j = join(i)
            mstr = ''
            if j < len(lines) and lines[j].startswith('msgstr'):
                mstr, j = join(j)
            out.append({'msgid': mid, 'msgstr': mstr, 'flags': flags})
            flags = []
            i = j
            continue
        i += 1
    return out


@pytest.fixture(scope='module')
def en_entries() -> list[dict]:
    return parse_po(EN_PO)


class TestEnglishCatalogue:
    def test_catalogue_is_not_empty(self, en_entries: list[dict]) -> None:
        assert len(en_entries) > 300, 'catalogue looks unreadable — did the parse break?'

    def test_no_live_entry_falls_back_to_chinese(self, en_entries: list[dict]) -> None:
        """An empty msgstr makes gettext return the Chinese msgid."""
        offenders = [e['msgid'] for e in en_entries if CJK.search(e['msgid']) and e['msgstr'] == '']
        assert not offenders, (
            f'{len(offenders)} English entries have an empty msgstr, so they render Chinese: {offenders[:10]}'
        )

    def test_no_live_entry_renders_chinese(self, en_entries: list[dict]) -> None:
        offenders = [
            (e['msgid'], e['msgstr'])
            for e in en_entries
            if CJK.search(e['msgid']) and CJK.search(e['msgstr']) and e['msgid'] not in ENDONYM_ALLOWLIST
        ]
        assert not offenders, f'English entries rendering Chinese: {offenders[:10]}'

    def test_no_translated_entry_is_fuzzy(self, en_entries: list[dict]) -> None:
        """A fuzzy entry is skipped by `pybabel compile`, so its translation is dead.

        Such an entry looks translated in the .po and still shows Chinese in the browser.
        """
        dead = [
            e['msgid'] for e in en_entries if 'fuzzy' in e['flags'] and CJK.search(e['msgid']) and e['msgstr'].strip()
        ]
        assert not dead, (
            f'{len(dead)} fuzzy English entries have a translation that compile() discards, '
            f'so they render Chinese: {dead[:10]}'
        )

    def test_compiled_catalogue_matches_the_po(self, app, en_entries: list[dict]) -> None:
        """`.mo` must carry every translation the `.po` declares.

        Catches a forgotten `pybabel compile` as well as compile-time skipping.
        """
        import gettext

        with (ROOT / 'translations' / 'en' / 'LC_MESSAGES' / 'messages.mo').open('rb') as f:
            mo = gettext.GNUTranslations(f)

        # A handful of samples is enough: a stale .mo fails on the first translated string.
        samples = [e for e in en_entries if CJK.search(e['msgid']) and e['msgstr'].strip() and len(e['msgid']) > 3][:80]
        stale = [e['msgid'] for e in samples if mo.gettext(e['msgid']) != e['msgstr']]
        assert not stale, (
            f'{len(stale)} translations are in the .po but missing from the compiled .mo '
            f'(run `make translations`): {stale[:5]}'
        )


class TestSuffixFragments:
    """`年` and `名` are Chinese suffixes with no English equivalent.

    gettext cannot express "delete this", and an empty msgstr would fall back to the Chinese
    msgid, so a single space is used. Asserted explicitly so the value is not "corrected" to
    empty (which would reintroduce the leak) — see the translator comments in the .po.
    """

    @pytest.mark.parametrize('msgid', ['年', '名'])
    def test_suffix_renders_as_whitespace_not_chinese(self, en_entries: list[dict], msgid: str) -> None:
        entry = next((e for e in en_entries if e['msgid'] == msgid), None)
        assert entry is not None, f'{msgid!r} missing from the English catalogue'
        assert entry['msgstr'].strip() == '', f'{msgid!r} should render as nothing in English, got {entry["msgstr"]!r}'
        assert entry['msgstr'] != '', f'{msgid!r} must not be an empty msgstr — that falls back to the Chinese msgid'


class TestClientDictionary:
    def test_every_template_i18n_key_is_defined(self) -> None:
        """`t(key)` returns the key itself when undefined, and the attribute paths write it
        straight into `aria-label` / `placeholder` / `title`."""
        js = JS.read_text(encoding='utf-8')
        defined = set(re.findall(r"^\s*'([a-zA-Z0-9_]+)':", js, re.M))

        referenced: set[str] = set()
        for path in TEMPLATES.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            referenced |= set(re.findall(r'data-i18n(?:-placeholder|-title|-aria-label)?="([a-zA-Z0-9_]+)"', text))

        missing = sorted(referenced - defined)
        assert not missing, (
            f'{len(missing)} data-i18n keys are referenced by templates but undefined in '
            f'translations.js, so the raw key lands in the attribute: {missing}'
        )

    def test_both_locales_define_the_same_keys(self) -> None:
        """中英两侧键集必须一致：只补一侧时，另一侧的 `t(key)` 会静默回退到中文。"""
        js = JS.read_text(encoding='utf-8')
        zh_block = js.split('zh: {', 1)[1].split('en: {', 1)[0]
        en_block = js.split('en: {', 1)[1].split('\n};', 1)[0]
        zh_keys = set(re.findall(r"^\s*'([a-zA-Z0-9_]+)':", zh_block, re.M))
        en_keys = set(re.findall(r"^\s*'([a-zA-Z0-9_]+)':", en_block, re.M))

        assert zh_keys, '解析不出 zh 键集，本用例已失效'
        assert zh_keys - en_keys == set(), f'缺少英文条目的键: {sorted(zh_keys - en_keys)}'
        assert en_keys - zh_keys == set(), f'缺少中文条目的键: {sorted(en_keys - zh_keys)}'


class TestChromeI18nHooks:
    """chrome 里可见的文案都必须带**可被 applyPageTranslation 消费**的钩子。

    语言偏好存在 localStorage：浏览器内切换语言时由 `applyPageTranslation()` **就地改写**
    带钩子的元素（不重新请求）。所以没有钩子的可见文案会**冻结在 SSR 语言** ——
    用户报的"切换语言后有一部分导航没有翻译"正是这个：面包屑三项 + 侧边栏「导航」整段
    共 48 处（真实浏览器实测，见 .debug/probe_lang_residue.mjs）。

    两类钩子：
    - `data-i18n`：静态 chrome 文案（有字典键）；
    - `data-zh` + `data-en`：数据型文案（分类名 / 书名 / 奖项名 / 周报标题），没有字典键。
    """

    HOOK = re.compile(r'data-i18n(?:-placeholder|-title|-aria-label)?=|data-zh=')

    # 只挑**不依赖 DB 内容**的页面：/reports/weekly 需要周报数据 + 服务打桩，在全量运行时
    # 会被上游用例的状态影响（实测单跑正常、全量下渲染成错误页 → 没有面包屑）。
    # 数据型条目的覆盖交给下面的源码级不变量与宏渲染用例，两者都不依赖 fixture。
    @pytest.mark.parametrize('path', ['/about', '/new-books'])
    def test_breadcrumb_items_carry_a_translation_hook(self, client, path: str) -> None:
        response = client.get(path)
        assert response.status_code == 200, f'{path} -> {response.status_code}'
        html = response.get_data(as_text=True)
        items = re.findall(r'<li class="breadcrumb-item">(.*?)</li>', html, re.S)
        assert items, f'{path} 渲染不出面包屑条目，本用例会退化成空转'
        bare = [i.strip()[:140] for i in items if not self.HOOK.search(i)]
        assert not bare, f'{path} 的面包屑条目缺翻译钩子，切语言后会冻结在 SSR 语言: {bare}'

    def test_every_breadcrumb_item_declares_a_hook(self) -> None:
        """所有调用点都必须给条目带钩子 —— 覆盖需要 fixture 的页面（周报详情、图书详情等）。

        条目在本仓库里一律写成单行 dict，所以按行判定即可；新增跨行写法会在这里被拦下，
        提示保持单行（或同步放宽本用例），不会静默漏检。
        """
        offenders: list[str] = []
        for path in sorted(TEMPLATES.rglob('*.html')):
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if "'label':" not in line:
                    continue
                if "'key':" in line:
                    continue
                if "'zh':" in line and "'en':" in line:
                    continue
                offenders.append(f'{path.name}:{lineno}: {line.strip()[:100]}')
        assert not offenders, (
            f'以下面包屑条目既没有 key（静态文案）也没有 zh/en（数据型文案），切换语言时会冻结在 SSR 语言：{offenders}'
        )

    def test_report_title_filter_localizes_the_standard_title(self, app) -> None:
        """周报面包屑靠 `report_title` 过滤器产出两侧文案（标准标题才会被改写）。"""
        localize = app.jinja_env.filters['report_title']
        standard = '2026年09月14日-2026年09月20日 畅销书周报'
        assert localize(standard, 'zh') == standard
        english = localize(standard, 'en')
        assert english != standard and '周报' not in english, f'en 侧未被本地化: {english!r}'
        # 人工撰写的任意标题必须原样透传，不许猜
        assert localize('自定义标题', 'en') == '自定义标题'

    def test_breadcrumb_macro_emits_both_locale_variants(self, app) -> None:
        """数据型条目必须同时产出 data-zh / data-en，客户端才能择一。"""
        macro = app.jinja_env.get_template('_breadcrumbs.html').module
        # nonce 必须显式传入：宏内 JSON-LD 用的 csp_nonce() 是 context processor，
        # 直接调用宏时不在作用域内（与 _weekly_lang_sync.html 的同一约定）。
        html = macro.breadcrumbs(
            [
                {'label': '首页', 'key': 'nav_home', 'url': '/'},
                {'label': '精装小说', 'zh': '精装小说', 'en': 'Hardcover Fiction', 'url': '/?category=f'},
                {'label': '永恒之火的燃烧', 'zh': '永恒之火的燃烧', 'en': 'BURN OF THE EVERFLAME', 'url': '/b'},
            ],
            'TESTNONCE',
        )
        assert 'data-i18n="nav_home"' in html
        assert 'data-zh="精装小说"' in html and 'data-en="Hardcover Fiction"' in html
        assert 'data-en="BURN OF THE EVERFLAME"' in html

    def test_sidebar_default_block_labels_carry_a_hook(self) -> None:
        """base.html 默认侧边栏里任何裸文案都会在切语言后冻结（「导航」整段曾如此）。"""
        html = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
        assert '{% block sidebar %}' in html, '侧边栏 block 被改名，本用例需同步'
        block = html.split('{% block sidebar %}', 1)[1].split('{% endblock %}', 1)[0]
        bare = [
            m.group(0)[:120]
            for m in re.finditer(r'<(span|h3)\b([^>]*)>\s*\{\{[^}]+\}\}\s*</\1>', block)
            if 'data-' not in m.group(2)
        ]
        assert not bare, f'侧边栏存在没有翻译钩子的可见文案: {bare}'


class TestEnglishPageRendering:
    """Server-side check: these exact strings used to render (in Chinese) on English pages."""

    LEAKED_STRINGS = [
        '数据仅供学习交流',
        '数据来源：NYT Books API',
        '站点地图',
        '诺贝尔文学奖、布克奖、普利策奖等',
        '正在翻译',
        '获奖图书',
    ]

    @pytest.mark.parametrize('path', ['/?lang=en', '/about?lang=en', '/awards?lang=en'])
    def test_english_pages_do_not_render_the_known_leaks(self, client, path: str) -> None:
        response = client.get(path)
        assert response.status_code == 200, f'{path} -> {response.status_code}'
        html = response.get_data(as_text=True)
        # strip scripts/styles: inline comments are localised too and legitimately Chinese-free,
        # but they are not user-visible and should not affect this assertion
        body = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)
        found = [s for s in self.LEAKED_STRINGS if s in body]
        assert not found, f'{path} still renders Chinese: {found}'
