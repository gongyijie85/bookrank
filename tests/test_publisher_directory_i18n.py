"""Publisher directory + category dropdown must not fall back to Chinese in the English UI.

Both are the same class of bug, and neither is reachable by fixing the gettext catalogue:

- `app/data/publishers.py` is hand-written content. `category` and `description` existed only in
  Chinese, so `?lang=en` rendered 939 visible Chinese characters. The template also had no locale
  branch at all (`_locale` appeared zero times), even though `name_en` already existed per entry.
- `templates/index.html` rendered `{{ categories[key] }}` for the `<option>` list. The English
  names were already in `config.CATEGORY_NAMES_EN` and already passed to the template as
  `category_names_en` — the template simply never consulted it, so the first paint was Chinese and
  the client-side `categories.js` labels only applied when the user toggled the language.

These tests pin the invariants (data completeness + locale-correct rendering), so adding a
publisher without English content fails here rather than shipping a leak.
"""

from __future__ import annotations

import html as html_module
import re

import pytest

from app.data.publishers import PUBLISHERS_DATA

CJK = re.compile(r'[\u3000-\u303f\u4e00-\u9fff\uff01-\uff60]')

# Chinese strings that must not survive on the English pages
ZH_CATEGORY_SAMPLES = ['综合大型出版集团', '童书出版', '学术与教育出版']
ZH_DESCRIPTION_SAMPLES = [
    '全球最大大众出版集团，全品类新书首发',
    '英国独立童书社，互动绘本、儿童文学新书',
    '日本连锁书店在线平台，日文外文新书资讯',
]
ZH_PUBLISHER_NAME = '企鹅兰登书屋（全球站）'

# The language switcher renders the Chinese option's own glyphs (中/简) on purpose, so speakers
# can find their language — exactly like the Chinese UI showing "English". Not a leak.
_LANG_SWITCHER_LEAVES = re.compile(
    r'<span class="lang-current"[^>]*>.*?</span>'
    r'|<span class="lang-flag"[^>]*>.*?</span>'
    r'|<span class="lang-name"[^>]*>.*?</span>',
    re.S,
)


def _content(html: str) -> str:
    """Text of the page with scripts/styles/comments/entities resolved and the switcher removed.

    Two things that are NOT user-visible leaks and must be stripped first:

    - **HTML comments.** Templates carry Chinese developer comments (e.g. the "Early lang sync"
      note in `base.html`). They never render. They also break naive tag stripping, because the
      comment body contains `<html lang>` — a nested `<` — so `<[^>]+>` stops at the wrong `>`.
    - **The language switcher glyphs** (中/简), which are shown deliberately.

    Entities matter too: `Children's publishing` is served as `Children&#39;s` and
    `Simon & Schuster` as `Simon &amp; Schuster`, so raw substring checks against the source
    string fail.
    """
    body = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', body, flags=re.S)
    body = _LANG_SWITCHER_LEAVES.sub('', body)
    return html_module.unescape(re.sub(r'<[^>]+>', ' ', body))


class TestDataCompleteness:
    def test_every_category_has_english(self) -> None:
        missing = [c['category'] for c in PUBLISHERS_DATA if not c.get('category_en')]
        assert not missing, f'categories without English: {missing}'

    def test_every_publisher_has_name_and_description_in_english(self) -> None:
        missing_name = [p['name'] for c in PUBLISHERS_DATA for p in c['publishers'] if not p.get('name_en')]
        missing_desc = [p['name'] for c in PUBLISHERS_DATA for p in c['publishers'] if not p.get('description_en')]
        assert not missing_name, f'publishers without name_en: {missing_name}'
        assert not missing_desc, f'publishers without description_en: {missing_desc}'

    def test_english_values_contain_no_chinese(self) -> None:
        offenders = []
        for c in PUBLISHERS_DATA:
            if CJK.search(c['category_en']):
                offenders.append(c['category_en'])
            for p in c['publishers']:
                for field in ('name_en', 'description_en'):
                    if CJK.search(p[field]):
                        offenders.append(p[field])
        assert not offenders, f'English fields containing Chinese: {offenders[:5]}'


class TestPublishersPageEnglish:
    def test_no_visible_chinese(self, client) -> None:
        html = client.get('/publishers?lang=en').get_data(as_text=True)
        text = _content(html)
        found = [s for s in ZH_CATEGORY_SAMPLES + ZH_DESCRIPTION_SAMPLES + [ZH_PUBLISHER_NAME] if s in text]
        assert not found, f'English /publishers still renders Chinese: {found}'
        assert not CJK.search(text), 'English /publishers still contains CJK'

    def test_renders_english_category_titles(self, client) -> None:
        text = _content(client.get('/publishers?lang=en').get_data(as_text=True))
        for c in PUBLISHERS_DATA:
            assert c['category_en'] in text, f'missing English category: {c["category_en"]}'

    def test_renders_english_descriptions_and_names(self, client) -> None:
        text = _content(client.get('/publishers?lang=en').get_data(as_text=True))
        for c in PUBLISHERS_DATA:
            for p in c['publishers']:
                assert p['description_en'] in text, f'missing English description: {p["name_en"]}'
                assert p['name_en'] in text, f'missing English name: {p["name_en"]}'

    def test_chinese_name_column_is_not_rendered(self, client) -> None:
        """The CH-name column content is Chinese, so the column is dropped in English.

        Search still works: rows keep both `data-name` and `data-name-en`.
        """
        html = client.get('/publishers?lang=en').get_data(as_text=True)
        assert '<th>Chinese Name</th>' not in html
        assert 'data-name-en=' in html and 'data-name=' in html

    def test_mobile_english_is_also_english(self, client) -> None:
        ua = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'}
        html = client.get('/publishers?lang=en', headers=ua).get_data(as_text=True)
        # mobile renders cards, not a table; check the same samples
        found = [s for s in ZH_CATEGORY_SAMPLES + ZH_DESCRIPTION_SAMPLES if s in html]
        assert not found, f'English mobile /publishers still renders Chinese: {found}'


class TestPublishersPageChinese:
    def test_chinese_unchanged(self, client) -> None:
        text = _content(client.get('/publishers?lang=zh').get_data(as_text=True))
        for c in PUBLISHERS_DATA:
            assert c['category'] in text, f'Chinese category lost: {c["category"]}'
        assert ZH_PUBLISHER_NAME in text
        assert ZH_DESCRIPTION_SAMPLES[0] in text
        # both name columns are still present in Chinese
        assert '中文名称' in text and '英文名称' in text


class TestHomeCategoryDropdown:
    """The `<option>` list must be English on first paint, not after a language toggle."""

    def test_english_options_on_first_paint(self, client) -> None:
        html = client.get('/?lang=en').get_data(as_text=True)
        options = re.findall(r'<option value="([^"]+)"[^>]*>\s*([^<]+)', html)
        labels = {v: t.strip() for v, t in options}
        assert labels, 'no category options rendered'
        # every option must be free of Chinese
        offenders = {v: t for v, t in labels.items() if CJK.search(t)}
        assert not offenders, f'English dropdown still has Chinese options: {offenders}'
        # and the NYT English names must be the ones shown
        assert any('Hardcover Fiction' in t for t in labels.values()), labels

    def test_chinese_options_unchanged(self, client) -> None:
        html = client.get('/?lang=zh').get_data(as_text=True)
        options = re.findall(r'<option value="([^"]+)"[^>]*>\s*([^<]+)', html)
        labels = {v: t.strip() for v, t in options}
        assert any('精装小说' in t for t in labels.values()), labels


class TestEnglishSourceLookup:
    def test_english_names_come_from_config_not_the_chinese_dict(self) -> None:
        """`category_names_en` was already plumbed into the template but never used.

        Guard the wiring: if it is dropped from the route context, the fallback silently returns
        the Chinese label and the dropdown regresses.
        """
        from app.config import config

        names_en = config['testing'].CATEGORY_NAMES_EN
        categories = config['testing'].CATEGORIES
        assert names_en, 'CATEGORY_NAMES_EN must not be empty'
        assert set(names_en) == set(categories), 'CATEGORY_NAMES_EN and CATEGORIES must cover the same category IDs'
        for key in categories:
            assert not CJK.search(names_en[key]), f'{key} English name contains Chinese'


@pytest.mark.parametrize('path', ['/publishers?lang=en', '/?lang=en'])
def test_english_pages_have_no_visible_chinese(client, path: str) -> None:
    """End-to-end guard mirroring the browser measurement (excludes the language switcher)."""
    html = client.get(path).get_data(as_text=True)
    assert not CJK.search(_content(html)), f'{path} still renders Chinese'
