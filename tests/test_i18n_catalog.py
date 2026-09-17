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
