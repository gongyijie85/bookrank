"""详情页布局改版 + 元数据诚实性（前端可读性专项的回归锁）。

覆盖两件事：

**A. 首屏布局**（1366×768 实测下原「简介开头」落在 852px —— 首屏看不到）
   根因是右侧栏里塞了 7 张等高元信息卡片 + 带顶部色条的 hero 标题卡，把简介挤出首屏。
   改版把元信息收敛成紧凑定义列表、简介提到元信息之前、并仅对详情端点隐藏全局侧边栏。
   本文件从**渲染结果**断言这些结构性事实（顺序、可见标签、body class 作用域），
   不锁具体 px —— px 由浏览器验收，这里锁的是"结构上做不到"的回归。

**B. 元数据诚实性**
   - `page_count` 只在正数时有意义：0 / '0' / None / 负数 / 布尔 / 小数 / 非数字串都必须
     不产生任何「页数」行（历史上渲染出「页数：0 页」，因为模板逐个列举脏值字面量）。
   - 只有元信息 / 占位串 / 语言标记（'英文'）时**不得**出现「详细信息」标签或面板。
   - 获奖图书作者：`_shape_award_book` 曾整条漏掉 `author`（DB 里存的 Penn Cole 显示不出来）。

判定逻辑本身（`positive_int_text`）的边界用参数化直接打，避免只测"某一本恰好没踩雷"。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from app.models.book import Book
from app.utils.book_labels import positive_int_text

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'

DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'
MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'

#: 「无信息量」取值的完整打击面：0 值、布尔、负数、小数、非数字串、None、空白
INVALID_PAGES = [
    0,
    '0',
    ' 0 ',
    '000',
    None,
    '',
    '   ',
    -1,
    '-12',
    True,
    False,
    '3.5',
    3.5,
    'Unknown',
    '未知',
    'N/A',
    'None',
    'abc',
    '12a',
    [],
]

VALID_PAGES = [
    (320, '320'),
    ('320', '320'),
    (' 320 ', '320'),
    ('0320', '320'),
    (1, '1'),
    ('1', '1'),
]


def _make_book(**overrides):
    defaults = {
        'id': '9780143127550',
        'title': 'Test Book',
        'title_zh': None,
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'cover': '',
        'list_name': 'Hardcover Fiction',
        'category_id': 'hardcover-fiction',
        'category_name': 'Hardcover Fiction',
        'rank': 1,
        'weeks_on_list': 3,
        'rank_last_week': '2',
        'published_date': '2024-01-14',
        'description': 'A test description',
        'description_zh': None,
        'details': 'Test details',
        'details_zh': None,
        'publication_dt': '2023-10-01',
        'page_count': '320',
        'language': 'en',
        'buy_links': [],
        'isbn13': '9780143127550',
        'isbn10': '014312755X',
        'price': '28.00',
    }
    defaults.update(overrides)
    return Book(**defaults)


def _mock_book_service(books):
    svc = MagicMock()
    svc.get_books_by_category.return_value = books
    svc.get_cache_time.return_value = '2024-01-14'
    svc.get_latest_cache_time.return_value = '2024-01-14'
    svc.search_books.return_value = []
    return svc


@pytest.fixture
def book_service(app):
    """临时注册 book_service，测完无条件还原（同 test_card_desc_and_details_render）。"""
    original = app.extensions.get('book_service')
    try:
        yield lambda books: app.extensions.__setitem__('book_service', _mock_book_service(books))
    finally:
        if original is None:
            app.extensions.pop('book_service', None)
        else:
            app.extensions['book_service'] = original


def _render_detail(client, book_service, lang: str = 'zh', ua: str | None = None, **overrides) -> str:
    """渲染桌面 / 移动版书籍详情页。

    `lang` 必须显式带上：`_get_locale()` 的优先级是 URL 参数 > Cookie > Accept-Language，
    不带上时结果取决于环境残留，空态文案的断言会随跑法不同而红绿。
    """
    book_service([_make_book(**overrides)])
    headers = {'User-Agent': ua} if ua else None
    with (
        patch('app.routes.main.enrich_book_details'),
        patch('app.routes.main.merge_or_translate_book'),
    ):
        response = client.get(f'/book/0?category=hardcover-fiction&lang={lang}', headers=headers)
    assert response.status_code == 200
    return response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# A. 判定逻辑本身
# ---------------------------------------------------------------------------


class TestPositiveIntText:
    """页数判定：只放行正数，其余一律空串（模板据此整行隐藏）。"""

    @pytest.mark.parametrize('value', INVALID_PAGES)
    def test_invalid_values_normalise_to_empty(self, value):
        assert positive_int_text(value) == '', f'{value!r} 不该被当成有效页数'

    @pytest.mark.parametrize(('value', 'expected'), VALID_PAGES)
    def test_valid_values_normalise_to_decimal(self, value, expected):
        assert positive_int_text(value) == expected


# ---------------------------------------------------------------------------
# B. 渲染结果：页数
# ---------------------------------------------------------------------------


class TestPageCountRendering:
    """无效页数不得在页面上产生任何「页数」痕迹（桌面 + 移动）。"""

    @staticmethod
    def _page_rows(soup: BeautifulSoup) -> list[str]:
        rows = []
        for row in soup.select('.detail-meta-row, .m-meta-row, .m-detail-facts span, .m-detail-facts > span'):
            text = row.get_text(' ', strip=True)
            if '页数' in text or 'Pages' in text:
                rows.append(text)
        return rows

    @pytest.mark.parametrize('value', [0, '0', None, -1, True, '3.5', 'abc', 'Unknown'])
    def test_desktop_hides_page_row_for_invalid_values(self, client, book_service, value):
        html = _render_detail(client, book_service, page_count=value)
        soup = BeautifulSoup(html, 'html.parser')
        assert self._page_rows(soup) == [], f'page_count={value!r} 不该渲染出页数行'
        assert '页数' not in soup.select_one('.detail-meta').get_text(' ', strip=True)

    @pytest.mark.parametrize('value', [0, '0', None, -1, True, '3.5', 'abc', 'Unknown'])
    def test_mobile_hides_page_row_for_invalid_values(self, client, book_service, value):
        html = _render_detail(client, book_service, ua=MOBILE_UA, page_count=value)
        soup = BeautifulSoup(html, 'html.parser')
        assert '页数' not in soup.get_text(' ', strip=True), f'page_count={value!r} 不该渲染出页数'

    @pytest.mark.parametrize('value', [320, '320', ' 320 '])
    def test_desktop_shows_page_row_for_valid_values(self, client, book_service, value):
        """反向断言：有效值必须真的渲染出来，证明上面的隐藏不是在测一个恒空的选择器。"""
        html = _render_detail(client, book_service, page_count=value)
        soup = BeautifulSoup(html, 'html.parser')
        assert self._page_rows(soup), '有效页数必须渲染出页数行'
        assert '320' in soup.select_one('.detail-meta').get_text(' ', strip=True)


# ---------------------------------------------------------------------------
# C. 渲染结果：详细信息标签页
# ---------------------------------------------------------------------------


class TestDetailsTabHonesty:
    """详情/空态/语言标记三类取值下的标签页与面板。"""

    @staticmethod
    def _has_details_tab(soup: BeautifulSoup) -> bool:
        return soup.find(id='tab-details') is not None or bool(soup.select('[data-tab="details"]'))

    @staticmethod
    def _has_details_panel(soup: BeautifulSoup) -> bool:
        return soup.find(id='panel-details') is not None or bool(soup.select('[data-panel="details"]'))

    @pytest.mark.parametrize('value', ['No detailed description available.', '暂无详细描述', '暂无简介', 'N/A'])
    def test_placeholder_details_create_no_tab_or_panel_desktop(self, client, book_service, value):
        html = _render_detail(client, book_service, details=value, details_zh=None)
        soup = BeautifulSoup(html, 'html.parser')
        assert not self._has_details_tab(soup), f'占位串 {value!r} 不该产生「详细信息」标签'
        assert not self._has_details_panel(soup), f'占位串 {value!r} 不该产生「详细信息」面板'
        assert value not in soup.get_text(' ', strip=True), '占位串本身也不该当正文渲染'

    @pytest.mark.parametrize('value', ['英文', '英语', '- 英文', '小说', '-', 'N/A'])
    def test_language_only_details_create_no_tab_or_panel_desktop(self, client, book_service, value):
        """语言标记是可渲染的真值，但没有任何信息量 —— 不能变成「详细信息: 英文」。"""
        html = _render_detail(client, book_service, details=value, details_zh=None)
        soup = BeautifulSoup(html, 'html.parser')
        assert not self._has_details_tab(soup), f'语言标记 {value!r} 不该产生「详细信息」标签'
        assert not self._has_details_panel(soup), f'语言标记 {value!r} 不该产生「详细信息」面板'

    @pytest.mark.parametrize('value', ['英文', '英语', '小说'])
    def test_language_only_details_create_no_tab_mobile(self, client, book_service, value):
        html = _render_detail(client, book_service, ua=MOBILE_UA, details=value, details_zh=None)
        soup = BeautifulSoup(html, 'html.parser')
        assert not self._has_details_tab(soup), f'移动端语言标记 {value!r} 不该产生「详细信息」标签'
        assert not self._has_details_panel(soup), f'移动端语言标记 {value!r} 不该产生「详细信息」面板'

    @pytest.mark.parametrize('value', ['英文', '小说', 'No detailed description available.'])
    def test_empty_details_create_no_tab_mobile(self, client, book_service, value):
        html = _render_detail(client, book_service, ua=MOBILE_UA, details=value, details_zh=None)
        soup = BeautifulSoup(html, 'html.parser')
        assert not self._has_details_tab(soup)

    def test_real_details_still_create_tab_and_panel_both_ends(self, client, book_service):
        """反向断言：真有详情时两端都必须渲染标签 + 面板，且正文可见。"""
        for ua in (None, MOBILE_UA):
            html = _render_detail(
                client,
                book_service,
                ua=ua,
                details='A substantial English detail paragraph.',
                details_zh='一段有实质内容的中文详细介绍。',
            )
            soup = BeautifulSoup(html, 'html.parser')
            label = 'desktop' if ua is None else 'mobile'
            assert self._has_details_tab(soup), f'{label}: 有详情时「详细信息」标签必须出现'
            assert self._has_details_panel(soup), f'{label}: 有详情时「详细信息」面板必须出现'
            assert '一段有实质内容的中文详细介绍。' in html, f'{label}: 详情正文必须渲染'


# ---------------------------------------------------------------------------
# D. 首屏布局：结构性事实
# ---------------------------------------------------------------------------


class TestFirstScreenStructure:
    """首屏布局的结构约束（px 由浏览器验收，这里锁"结构上做不到"的回归）。"""

    def test_intro_precedes_secondary_metadata(self, client, book_service):
        """简介必须排在元信息定义列表之前 —— 否则元信息又会把简介顶到首屏之下。"""
        html = _render_detail(client, book_service, description_zh='一段首屏简介。')
        soup = BeautifulSoup(html, 'html.parser')
        intro = soup.select_one('.detail-intro')
        meta = soup.select_one('.detail-meta')
        assert intro is not None, '详情页应渲染首屏简介块 .detail-intro'
        assert meta is not None, '详情页应渲染元信息定义列表 .detail-meta'
        # source position 比较：两者都在同一父节点下，直接用文档序
        order = [id(node) for node in soup.select('.detail-intro, .detail-meta')]
        assert order == [id(intro), id(meta)], '简介必须出现在元信息之前'

    def test_metadata_is_a_definition_list_not_seven_cards(self, client, book_service):
        html = _render_detail(client, book_service)
        soup = BeautifulSoup(html, 'html.parser')
        assert soup.select_one('.detail-meta') is not None
        assert soup.select('.detail-meta-row'), '元信息应为 dt/dd 行'
        # 每个 dt 都有配对的 dd（定义列表语义，读屏可读）
        for row in soup.select('.detail-meta-row'):
            assert row.find('dt') is not None and row.find('dd') is not None
        assert soup.select('.meta-card') == [], '不应再有 7 张等高卡片'
        assert soup.select('.meta-icon') == [], '卡片图标块应一并移除'

    def test_sidebar_hidden_only_on_detail_endpoints(self, client, book_service):
        """详情端点打上 body.detail-page；列表页不得带上（否则全站导航会被误伤）。"""
        detail = BeautifulSoup(_render_detail(client, book_service), 'html.parser')
        assert 'detail-page' in (detail.body.get('class') or []), '详情页 body 应带 detail-page'

        with patch('app.routes.main.get_service') as mock_svc:
            mock_svc.return_value = _mock_book_service([_make_book()])
            home = BeautifulSoup(client.get('/?category=hardcover-fiction').get_data(as_text=True), 'html.parser')
        assert 'detail-page' not in (home.body.get('class') or []), '首页不该带 detail-page'

    def test_buy_links_preserve_urls_rel_and_order(self, client, book_service):
        """购买链接改样式不改契约：URL、rel、名称顺序全部保留。"""
        links = [
            {'name': 'Amazon', 'url': 'https://example.com/amazon'},
            {'name': 'Bookshop', 'url': 'https://example.com/bookshop'},
        ]
        html = _render_detail(client, book_service, buy_links=links)
        soup = BeautifulSoup(html, 'html.parser')
        anchors = soup.select('.buy-links a')
        assert [a.get_text(strip=True) for a in anchors] == ['Amazon', 'Bookshop']
        assert [a['href'] for a in anchors] == [link['url'] for link in links]
        for anchor in anchors:
            assert anchor.get('target') == '_blank'
            assert anchor.get('rel') == ['noopener', 'noreferrer']

    def test_back_link_and_tabs_preserved(self, client, book_service):
        """返回路由、标签按钮与 BookI18n 依赖的钩子一律保留。"""
        html = _render_detail(client, book_service)
        soup = BeautifulSoup(html, 'html.parser')
        back = soup.select_one('.back-btn')
        assert back is not None and back['href'], '返回按钮与 back_url 必须保留'
        assert soup.find(id='tab-description') is not None
        # BookI18n 依赖 .detail-title / .detail-author 与当前书籍字段
        assert soup.select_one('.detail-title') is not None
        assert soup.select_one('.detail-author') is not None
        assert 'BookI18n.registerAll' in html
        for field in ('isbn13', 'title_zh', 'description_zh', 'details', 'details_zh'):
            assert f'{field}:' in html, f'BookI18n 注册载荷丢了 {field}'


# ---------------------------------------------------------------------------
# D2. 首屏简介摘要的**语言择取**
# ---------------------------------------------------------------------------


def _intro_payload(html: str):
    """取首屏简介块：渲染文本 + 两种语言的 data 原文（无简介时返回 None）。"""
    soup = BeautifulSoup(html, 'html.parser')
    el = soup.select_one('.detail-intro-text')
    if el is None:
        assert soup.select_one('.detail-intro-empty') is not None, (
            '首屏既没有 .detail-intro-text 也没有 .detail-intro-empty'
        )
        return None
    return {
        'text': el.get_text(' ', strip=True),
        'zh': el.get('data-intro-zh') or '',
        'en': el.get('data-intro-en') or '',
    }


class TestFirstScreenIntroLocale:
    """首屏简介摘要必须按当前语言择语，并提供运行时切换用的语言钩子。

    回归：改版初版写的是 `{% set _intro = _desc_zh or _desc_en %}` —— 只要中文侧有值就
    永远选中文，英文 SSR（?lang=en）渲染出的首屏摘要仍是中文；而 `.detail-intro-text`
    是一段没有 data 钩子的纯文本，`switchDetailLang` 也完全没管它，运行时切到 EN 同样
    换不过来。这里锁两件事：SSR 择语正确 + 两种语言的原文都在 DOM 里（供运行时择一）。
    """

    ZH = '这是一段中文简介。'
    EN = 'This is the English synopsis.'

    def test_english_ssr_picks_english_when_available(self, client, book_service):
        html = _render_detail(client, book_service, lang='en', description=self.EN, description_zh=self.ZH)
        intro = _intro_payload(html)
        assert intro is not None
        assert intro['text'] == self.EN, f'英文 SSR 的首屏摘要应选英文，实际 {intro["text"]!r}'

    def test_chinese_ssr_picks_chinese_when_available(self, client, book_service):
        html = _render_detail(client, book_service, lang='zh', description=self.EN, description_zh=self.ZH)
        intro = _intro_payload(html)
        assert intro is not None
        assert intro['text'] == self.ZH, f'中文 SSR 的首屏摘要应选中文，实际 {intro["text"]!r}'

    @pytest.mark.parametrize('lang', ['zh', 'en'])
    def test_bilingual_intro_carries_both_languages_for_runtime_switch(self, client, book_service, lang):
        """运行时切换靠 data 属性择语，两种语言的原文必须随 DOM 一起下发。"""
        html = _render_detail(client, book_service, lang=lang, description=self.EN, description_zh=self.ZH)
        intro = _intro_payload(html)
        assert intro is not None
        assert intro['zh'] == self.ZH, '首屏简介缺中文原文，运行时切到中文会变空白'
        assert intro['en'] == self.EN, '首屏简介缺英文原文，运行时切到英文会变空白'

    @pytest.mark.parametrize(
        ('lang', 'description', 'description_zh', 'expected'),
        [
            ('zh', 'English only synopsis.', None, 'English only synopsis.'),
            ('zh', None, '只有中文简介。', '只有中文简介。'),
        ],
    )
    def test_intro_falls_back_to_the_only_available_language(
        self, client, book_service, lang, description, description_zh, expected
    ):
        """只有一侧有简介时不得渲染空白 —— 回落到另一侧（真实回落，不是空态）。"""
        html = _render_detail(client, book_service, lang=lang, description=description, description_zh=description_zh)
        intro = _intro_payload(html)
        assert intro is not None, '有简介（任一语言）时不该渲染空态'
        assert intro['text'] == expected

    def test_intro_block_keeps_the_full_synopsis_in_the_description_tab(self, client, book_service):
        """首屏摘要是有意保留的摘要；完整简介仍必须在「图书简介」标签页里。"""
        long_en = self.EN + ' ' + ('A trailing sentence kept only in the tab. ' * 3)
        html = _render_detail(client, book_service, lang='en', description=long_en, description_zh=None)
        soup = BeautifulSoup(html, 'html.parser')
        panel = soup.select_one('#panel-description')
        assert panel is not None
        assert long_en.strip() in panel.get_text(' ', strip=True), '完整简介必须仍在简介标签页内'

    def test_placeholder_description_renders_empty_state(self, client, book_service):
        html = _render_detail(client, book_service, lang='zh', description='No summary available.', description_zh=None)
        soup = BeautifulSoup(html, 'html.parser')
        assert soup.select_one('.detail-intro-text') is None
        assert soup.select_one('.detail-intro-empty') is not None, '占位串不算简介，应走空态'
        assert 'No summary available.' not in soup.select_one('.detail-intro').get_text(' ', strip=True)

    def test_switch_detail_lang_updates_the_intro(self):
        """`switchDetailLang` 必须真的更新首屏简介 —— 从模板里执行该函数验证真实行为。

        没有浏览器 harness，这里把模板 extra_js 里与本函数相关的片段抽出来放进 node:vm
        跑一遍：断言切到 EN 显示英文原文、切回 ZH 显示中文原文、缺一侧时回落另一侧。
        """
        import shutil
        import subprocess

        node = shutil.which('node')
        if node is None:  # pragma: no cover - 环境没有 node 时跳过，不假装通过
            pytest.skip('node 不可用，跳过 switchDetailLang 行为验证')

        template = (TEMPLATES / 'book_detail.html').read_text(encoding='utf-8')
        script = re.search(r'function switchDetailLang\(lang\)\s*\{.*?\n    \}', template, re.DOTALL)
        assert script, '模板里找不到 switchDetailLang，测试本身可能失效'
        harness = _SWITCH_LANG_HARNESS.replace('__SWITCH_DETAIL_LANG__', script.group(0))

        result = subprocess.run(
            [node, '--input-type=module', '-e', harness],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f'switchDetailLang 行为验证失败：{result.stderr or result.stdout}'
        assert 'OK' in result.stdout, result.stdout


#: 用 node:vm 加载 switchDetailLang 的**源码片段**并断言真实 DOM 写入行为。
#: 迷你 DOM 只实现该函数用到的 API（querySelector/querySelectorAll/getElementById/classList/style）。
_SWITCH_LANG_HARNESS = r"""
import assert from 'node:assert/strict';
import vm from 'node:vm';

function makeEl(overrides = {}) {
    const el = {
        dataset: {}, style: {}, textContent: '',
        classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
                     contains(c) { return this._s.has(c); }, toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); } },
        querySelector: () => null,
        ...overrides,
    };
    return el;
}

// 首屏简介：中英原文都在 data 上（与模板渲染结果一致）
function intro(zh, en) {
    const el = makeEl({ dataset: { introZh: zh, introEn: en } });
    el.textContent = zh || en;
    return el;
}

function run(introEl, lang) {
    const nodes = { '.detail-intro-text': introEl };
    const context = vm.createContext({
        console,
        document: {
            querySelector: sel => nodes[sel] || null,
            querySelectorAll: () => [],
            getElementById: () => null,
        },
        t: key => key,
    });
    vm.runInContext(`__SWITCH_DETAIL_LANG__`, context);
    context.switchDetailLang(lang);
    return introEl.textContent;
}

const NONE = makeEl({ dataset: {} });
for (const [lang, zh, en, expected] of [
    ['en', '\u4e2d\u6587\u6458\u8981\u3002', 'English synopsis.', 'English synopsis.'],
    ['zh', '\u4e2d\u6587\u6458\u8981\u3002', 'English synopsis.', '\u4e2d\u6587\u6458\u8981\u3002'],
    // 缺英文 -> 回落中文；缺中文 -> 回落英文（真实回落，不是空白）
    ['en', '\u4e2d\u6587\u6458\u8981\u3002', '', '\u4e2d\u6587\u6458\u8981\u3002'],
    ['zh', '', 'English synopsis.', 'English synopsis.'],
]) {
    const actual = run(intro(zh, en), lang);
    assert.equal(actual, expected, 'lang=' + lang + ' zh=' + zh + ' en=' + en + ' got=' + actual);
}
// 没有简介块时不得抛错（空态页面同样走这个函数）
assert.equal(run(NONE, 'en'), '');
console.log('OK');
"""


# ---------------------------------------------------------------------------
# E. 获奖图书作者
# ---------------------------------------------------------------------------


def _seed_award_book(db, *, author):
    from app.models.schemas import Award, AwardBook

    award = Award(name='Test Award', name_en='Test Award', country='美国', description='d')
    db.session.add(award)
    db.session.commit()
    book = AwardBook(
        award_id=award.id,
        title='The Night Compass',
        title_zh='夜之罗盘',
        author=author,
        year=2024,
        category='最佳长篇小说',
        isbn13='9780000000123',
        description='A test description.',
        is_displayable=True,
    )
    db.session.add(book)
    db.session.commit()
    return book.id


class TestAwardBookAuthorRendering:
    """获奖图书作者：DB 里有值就必须显示，真缺时用一致的本地化兜底。"""

    @pytest.mark.parametrize('ua', [DESKTOP_UA, MOBILE_UA])
    @pytest.mark.parametrize(('lang', 'expected'), [('zh', 'Penn Cole'), ('en', 'Penn Cole')])
    def test_known_author_renders_on_both_layouts(self, client, db, ua, lang, expected):
        book_id = _seed_award_book(db, author='Penn Cole')
        html = client.get(f'/award-book/{book_id}?lang={lang}', headers={'User-Agent': ua}).get_data(as_text=True)
        soup = BeautifulSoup(html, 'html.parser')
        author = soup.select_one('.detail-author, .m-detail-author')
        assert author is not None, '获奖图书详情应渲染作者行'
        assert expected in author.get_text(' ', strip=True), f'作者丢失：{author.get_text(strip=True)!r}'

    @pytest.mark.parametrize('ua', [DESKTOP_UA, MOBILE_UA])
    @pytest.mark.parametrize(('lang', 'expected'), [('zh', '未知作者'), ('en', 'Unknown')])
    def test_missing_author_uses_localised_fallback(self, client, db, ua, lang, expected):
        """真缺作者时用与全站卡片一致的本地化兜底，且不留空行。

        `award_books.author` 是 NOT NULL，所以"真缺"在库里表现为抓取侧的占位串
        （'Unknown' / 'N/A' / 空白）而不是 NULL —— 这正是 PLACEHOLDER_TEXTS 的语义。
        三种形态都打一遍，避免只覆盖一种就以为修好了。
        """
        for raw in ('', '   ', 'Unknown', 'N/A'):
            book_id = _seed_award_book(db, author=raw)
            html = client.get(f'/award-book/{book_id}?lang={lang}', headers={'User-Agent': ua}).get_data(as_text=True)
            soup = BeautifulSoup(html, 'html.parser')
            author = soup.select_one('.detail-author, .m-detail-author')
            assert author is not None
            text = author.get_text(' ', strip=True)
            assert expected in text, f'作者 {raw!r} 未回落到本地化兜底：{text!r}'
            assert text != '·', '作者行不该只剩分隔符'

    @pytest.mark.parametrize('ua', [DESKTOP_UA, MOBILE_UA])
    def test_missing_author_fallback_follows_the_active_language(self, client, db, ua):
        """缺省作者标签必须**跟随当前语言**，不能焊死在 SSR 语言上。

        回归：`data-en` 与 `data-zh` 都被赋成当前 locale 的 `_shown_author`，于是以中文
        SSR 的页面里英文侧也是「未知作者」，`applyLanguage('en')` 重写成同一个中文串 ——
        语言切换看起来"没反应"。这里锁两侧确实是**不同**语言的值：
        中文侧是中文、英文侧是 'Unknown'（来自既有 en 目录，不发明新文案）。
        """
        book_id = _seed_award_book(db, author='')
        html = client.get(f'/award-book/{book_id}?lang=zh', headers={'User-Agent': ua}).get_data(as_text=True)
        soup = BeautifulSoup(html, 'html.parser')
        author = soup.select_one('.detail-author, .m-detail-author')
        assert author is not None, '缺省作者仍应渲染作者行'
        zh, en = author.get('data-zh') or '', author.get('data-en') or ''
        assert zh and en, '缺省作者两侧语言都必须是真实值，否则切换后会出现空白'
        assert zh != en, f'data-zh 与 data-en 相同（{zh!r}），语言切换会粘在初始语言上'
        assert zh == '未知作者', f'中文侧应为中文兜底，实际 {zh!r}'
        assert en == 'Unknown', f'英文侧应为既有英文兜底，实际 {en!r}'
        # 已知作者的人名不翻译：两侧同值是有意的
        known_id = _seed_award_book(db, author='Penn Cole')
        known = BeautifulSoup(
            client.get(f'/award-book/{known_id}?lang=zh', headers={'User-Agent': ua}).get_data(as_text=True),
            'html.parser',
        ).select_one('.detail-author, .m-detail-author')
        assert known.get('data-zh') == known.get('data-en') == 'Penn Cole'

    def test_shape_award_book_exposes_author(self, app, db):
        """`_shape_award_book` 曾整条漏掉 author（awards 列表卡片作者行恒空）。"""
        from app.models.schemas import AwardBook
        from app.routes.main import _shape_award_book

        book_id = _seed_award_book(db, author='Penn Cole')
        shaped = _shape_award_book(db.session.get(AwardBook, book_id))
        assert shaped['author'] == 'Penn Cole'


# ---------------------------------------------------------------------------
# E2. 获奖图书详情：详细信息标签页的诚实性 + 移动端书目元数据
# ---------------------------------------------------------------------------


def _seed_award_book_full(db, **overrides):
    from app.models.schemas import Award, AwardBook

    award = Award(name='Test Award', name_en='Test Award', country='美国', description='d')
    db.session.add(award)
    db.session.commit()
    fields = {
        'title': 'The Night Compass',
        'title_zh': '夜之罗盘',
        'author': 'Penn Cole',
        'year': 2024,
        'category': '最佳长篇小说',
        'isbn13': '9780000000123',
        'publisher': 'Test Publisher',
        'publication_year': 2023,
        'description': 'A test description.',
        'is_displayable': True,
    }
    fields.update(overrides)
    book = AwardBook(award_id=award.id, **fields)
    db.session.add(book)
    db.session.commit()
    return book.id


class TestAwardBookDetailsTabHonesty:
    """桌面获奖详情此前**无条件**渲染「详细信息」，且按钮/面板共用 id。"""

    def _render(self, client, db, ua, **overrides) -> str:
        book_id = _seed_award_book_full(db, **overrides)
        return client.get(f'/award-book/{book_id}?lang=zh', headers={'User-Agent': ua}).get_data(as_text=True)

    @staticmethod
    def _details_button(soup: BeautifulSoup):
        return soup.select_one('.tab-btn[data-tab="details"], .m-tab-btn[data-tab="details"]')

    @pytest.mark.parametrize('ua', [DESKTOP_UA, MOBILE_UA])
    @pytest.mark.parametrize(
        'value', ['', None, '暂无详细描述', 'No detailed description available.', '英文', '英语', '-']
    )
    def test_language_only_or_placeholder_details_create_no_tab_or_panel(self, client, db, ua, value):
        """没有实质详情时，标签按钮与面板都不出现（两端同口径）。"""
        soup = BeautifulSoup(self._render(client, db, ua, details=value), 'html.parser')
        assert self._details_button(soup) is None, f'details={value!r} 不该产生「详细信息」标签'
        assert soup.select_one('[data-panel="details"], #panel-details') is None, (
            f'details={value!r} 不该产生「详细信息」面板'
        )
        # 只在整个**内容区**里找正文，不能拿全页文本断言：页脚/导航里本来就有 '-'。
        # 桌面内容区是 .detail-info-section，移动端是 .m-detail-tabs-wrapper。
        region = soup.select_one('.detail-info-section, .m-detail-tabs-wrapper')
        assert region is not None, '找不到详情内容区，测试本身可能失效'
        if value:
            assert value not in region.get_text(' ', strip=True), '语言标记/占位串不该当正文渲染'

    @pytest.mark.parametrize('ua', [DESKTOP_UA, MOBILE_UA])
    def test_real_details_still_render_tab_and_panel(self, client, db, ua):
        """反向断言：真有详情时标签与面板必须出现，正文可见。"""
        soup = BeautifulSoup(self._render(client, db, ua, details='A substantial detail paragraph.'), 'html.parser')
        assert self._details_button(soup) is not None, '有详情时「详细信息」标签必须出现'
        assert soup.select_one('[data-panel="details"], #panel-details') is not None
        assert 'A substantial detail paragraph.' in soup.get_text(' ', strip=True)

    def test_desktop_ids_are_unique_and_tabs_resolve_to_the_panel(self, client, db):
        """按钮用 tab-*、面板用 panel-*：同 id 出现两次既无效 HTML 也会打坏切页逻辑。

        回归：桌面模板的简介与详情按钮、面板**四个元素**两两同名
        （`id="tab-description"` / `id="tab-details"` 各两次），而 `switchTab` 是用
        `tab-${tabName}` 找面板的 —— 命中的其实是按钮，标签切换根本切不动。
        """
        soup = BeautifulSoup(
            self._render(client, db, DESKTOP_UA, details='A substantial detail paragraph.'), 'html.parser'
        )
        ids = [el['id'] for el in soup.select('[id]')]
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f'获奖详情页出现重复 id：{sorted(dupes)}'
        assert soup.select_one('button#tab-description') is not None
        assert soup.select_one('button#tab-details') is not None
        assert soup.select_one('div#panel-description') is not None
        assert soup.select_one('div#panel-details') is not None
        # switchTab 必须按 panel-* 找面板（而非按钮 id）
        assert 'getElementById(`panel-${tabName}`)' in str(soup), 'switchTab 应解析 panel-* 面板 id'

    def test_desktop_synopsis_precedes_metadata_and_has_no_repeated_title(self, client, db):
        """简介排在元信息之前，且不再有一个重复书名的标题块占首屏。"""
        soup = BeautifulSoup(self._render(client, db, DESKTOP_UA), 'html.parser')
        order = [id(n) for n in soup.select('.detail-intro, .detail-meta, .detail-tabs')]
        intro, meta, tabs = (
            soup.select_one('.detail-intro'),
            soup.select_one('.detail-meta'),
            soup.select_one('.detail-tabs'),
        )
        assert intro is not None and meta is not None and tabs is not None
        assert order == [id(intro), id(meta), id(tabs)], '顺序应为 简介 → 元信息 → 标签页'
        assert soup.select_one('#panel-description') is not None
        assert soup.select_one('.detail-header-info') is None, '重复的标题块应已移除'
        for row in soup.select('.detail-meta-row'):
            assert row.find('dt') is not None and row.find('dd') is not None

    def test_desktop_keeps_buy_links_and_back_behaviour(self, client, db):
        """购买链接容器、返回按钮等既有交互钩子必须原样保留。

        注意：`AwardBook.buy_links` 是**裸 JSON 文本列**（与 `NewBook.get_buy_links`
        不同，模型上没有解析器），模板直接 `{% for link in book.buy_links %}` 迭代的是
        字符串。这是本次改版之前就存在的行为，不属于本次修复范围，这里只锁
        "改版没有把购买链接块、返回按钮这些既有结构删掉/改坏"。
        """
        html = self._render(client, db, DESKTOP_UA)
        soup = BeautifulSoup(html, 'html.parser')
        assert soup.select_one('#btn-back') is not None, '返回按钮必须保留'
        # 没有购买链接数据时整块隐藏（空列表对用户没有价值）
        assert soup.select('.buy-links-list') == []
        # 购买链接块的结构与样式入口仍在模板里（有数据时才会渲染）
        template = (TEMPLATES / 'award_book_detail.html').read_text(encoding='utf-8')
        assert 'detail-buy-links' in template and 'buy-links-list' in template
        assert 'rel="noopener noreferrer"' in template, '购买链接的 rel 安全属性必须保留'

    def test_mobile_keeps_bibliographic_metadata_without_details(self, client, db):
        """移动端回归：没有 details 正文时，ISBN / 出版社**仍必须可见**。

        回归：书目元数据 dl 被关在条件渲染的 details 面板里，没有实质详情时整块消失 ——
        ISBN、出版社、出版年份这些真数据跟着一起没了。
        """
        soup = BeautifulSoup(self._render(client, db, MOBILE_UA, details=None), 'html.parser')
        assert self._details_button(soup) is None, '没有 details 正文时不该有「详细信息」标签'
        assert soup.select_one('[data-panel="details"]') is None, '也不该有空面板'
        meta = soup.select_one('.m-meta-list')
        assert meta is not None, '没有 details 时书目元数据仍须渲染'
        text = meta.get_text(' ', strip=True)
        assert '9780000000123' in text, 'ISBN 丢失'
        assert 'Test Publisher' in text, '出版社丢失'
        assert '2023' in text, '出版年份丢失'
        # 元数据应在简介面板内（简介之后），不是被藏起来的另一块
        desc_panel = soup.select_one('[data-panel="description"]')
        assert desc_panel.select_one('.m-meta-list') is not None, '书目元数据应常驻简介面板'
        assert desc_panel.select_one('.m-detail-text') is not None, '简介正文仍应在元数据之前'

    def test_mobile_details_panel_carries_only_the_prose(self, client, db):
        """有详情时，details 面板只放正文（元数据已上移），且保留懒加载钩子。"""
        soup = BeautifulSoup(
            self._render(client, db, MOBILE_UA, details='A substantial detail paragraph.'), 'html.parser'
        )
        panel = soup.select_one('[data-panel="details"]')
        assert panel is not None
        assert 'A substantial detail paragraph.' in panel.get_text(' ', strip=True)
        assert panel.select_one('.m-meta-list') is None, '元数据不该在 details 面板里重复一份'
        assert panel.select_one('.m-tab-panel-extra[data-source="google-books"]') is not None, (
            'Google Books 懒加载落点必须保留'
        )


# ---------------------------------------------------------------------------
# F. 结构化数据与 JSON-LD 未被改坏
# ---------------------------------------------------------------------------


class TestStructuredDataIntact:
    def test_jsonld_author_still_present(self, client, db):
        book_id = _seed_award_book(db, author='Penn Cole')
        html = client.get(f'/award-book/{book_id}?lang=zh', headers={'User-Agent': DESKTOP_UA}).get_data(as_text=True)
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all('script', type='application/ld+json'):
            data = json.loads(tag.get_text())
            if isinstance(data, dict) and data.get('@type') == 'Book':
                assert data.get('author', {}).get('name') == 'Penn Cole'
                return
        raise AssertionError('页面没有 @type=Book 的 ld+json')
