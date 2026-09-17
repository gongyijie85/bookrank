"""卡片简介完整展示 + 详情页"详细信息"面板渲染（前端三问题的回归锁）。

对应两个前端缺陷：

**封面下方简介被截断**（`templates/index.html` + `static/js/index.js` + CSS）
  服务端按 `[:80]` 截断、客户端按 `slice(0, 100)` 截断，再叠加 `.card-desc` 的
  `-webkit-line-clamp: 2`，三层一起把长简介砍成开头一句。修复后简介整段下发。

**详情页"详细信息"内容缺失**（`templates/book_detail.html`）
  原实现是 `{% if details_zh %} … {% elif details %} … {% endif %}`，**没有 else 分支**，
  且 `details_zh` 只做真值判断不做 trim/占位串归一化。于是
  `details_zh='   '`（只有空白）会渲染出一个空的中文块并吞掉英文分支，
  `details='No detailed description available.'` 时整个面板空白 —— 页面看起来就是
  "详细介绍没出来"。

这里刻意从**渲染结果**断言（简介文本是否完整出现、面板是否有可见正文），
而不是断言模板字符串，避免把实现细节当成契约。
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from app.models.book import Book

CSS_DIR = Path(__file__).resolve().parent.parent / 'static' / 'css'

#: 明显超过旧的 80 字服务端截断阈值，用来证明没有按长度砍
LONG_DESCRIPTION = (
    '这是一段刻意写得很长的图书简介，用来验证封面下方的简介不再被截断。'
    '它包含足够多的字数，使得任何按固定字数裁剪的实现都会在中间断开，'
    '而完整渲染的实现会把最后这句话也原样呈现出来。'
)
LONG_DESCRIPTION_TAIL = '而完整渲染的实现会把最后这句话也原样呈现出来。'


def _make_book(**overrides):
    defaults = {
        'id': '9780143127550',
        'title': 'Test Book',
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
        'details': 'Test details',
        'publication_dt': '2023-10-01',
        'page_count': '320',
        'language': 'en',
        'buy_links': [],
        'isbn13': '9780143127550',
        'isbn10': '014312755X',
        'price': '28.00',
        'title_zh': None,
        'description_zh': None,
        'details_zh': None,
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
    """临时注册 book_service，测完无条件还原。

    注意别依赖 session 级 app 上的残留注册表：`test_main_routes_extended.py`
    的 TestWeeklyReports 会把 book_service pop 掉且不还原，跨文件跑时后续
    依赖真实服务注册表的用例会静默渲染成错误页。
    """
    original = app.extensions.get('book_service')
    try:
        yield lambda books: app.extensions.__setitem__('book_service', _mock_book_service(books))
    finally:
        if original is None:
            app.extensions.pop('book_service', None)
        else:
            app.extensions['book_service'] = original


def _details_panel(html: str):
    """取详情页 #panel-details 的可见正文，以及英文原文折叠块内的文本。"""
    soup = BeautifulSoup(html, 'html.parser')
    panel = soup.find(id='panel-details')
    assert panel is not None, '详情页应始终渲染 #panel-details 容器'
    toggled = panel.find(class_='lang-toggle-content')
    toggled_text = toggled.get_text(strip=True) if toggled else ''
    # 可见正文 = 面板全文 - 默认折叠（display:none）的英文块
    visible = panel.get_text(' ', strip=True)
    if toggled_text:
        visible = visible.replace(toggled_text, ' ', 1).strip()
    return soup, panel, visible, toggled_text


class TestCardDescriptionNotTruncated:
    """问题一：封面下方的图书简介必须完整展示。"""

    @patch('app.routes.main.fetch_google_books_details')
    @patch('app.routes.main.merge_or_translate_book')
    def test_long_chinese_description_rendered_in_full(self, mock_merge, mock_fetch, client, book_service):
        book = _make_book(description=LONG_DESCRIPTION, description_zh=LONG_DESCRIPTION)
        book_service([book])

        html = client.get('/?category=hardcover-fiction&lang=zh').get_data(as_text=True)

        assert LONG_DESCRIPTION in html, '简介应按原文完整下发，不应按字数截断'
        assert LONG_DESCRIPTION_TAIL in html, '简介结尾必须出现在页面上（旧的 [:80] 截断会砍掉它）'

    @patch('app.routes.main.fetch_google_books_details')
    @patch('app.routes.main.merge_or_translate_book')
    def test_english_description_rendered_in_full(self, mock_merge, mock_fetch, client, book_service):
        long_en = (
            'A deliberately long English summary used to prove that the card no longer '
            'truncates the description at a fixed character count, so that this trailing '
            'sentence still shows up on the rendered page.'
        )
        book = _make_book(description=long_en)
        book_service([book])

        html = client.get('/?category=hardcover-fiction&lang=en').get_data(as_text=True)

        assert long_en in html
        assert 'still shows up on the rendered page.' in html

    @patch('app.routes.main.fetch_google_books_details')
    @patch('app.routes.main.merge_or_translate_book')
    def test_placeholder_summary_is_not_rendered_as_description(self, mock_merge, mock_fetch, client, book_service):
        """'No summary available.' 是抓取侧的"没有"标记，不该当成简介正文。"""
        book = _make_book(description='No summary available.')
        book_service([book])

        html = client.get('/?category=hardcover-fiction&lang=en').get_data(as_text=True)

        soup = BeautifulSoup(html, 'html.parser')
        card_descs = [el.get_text(strip=True) for el in soup.select('.card-desc')]
        assert 'No summary available.' not in card_descs


class TestCardDescCssDoesNotClamp:
    """问题一的 CSS 侧：`.card-desc` 不得再钳制行数。"""

    @staticmethod
    def _strip_comments(css_text: str) -> str:
        """注释里会提到 `-webkit-line-clamp`（说明修复缘由），比较前先去掉。"""
        return re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)

    @staticmethod
    def _rule_body(css_text: str, selector: str) -> str:
        match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css_text)
        assert match, f'{selector} 规则不存在，测试本身可能失效'
        return match.group(1)

    def test_components_card_desc_has_no_line_clamp(self):
        body = self._rule_body(
            self._strip_comments((CSS_DIR / 'components.css').read_text(encoding='utf-8')), '.card-desc'
        )
        assert 'line-clamp' not in body
        assert 'overflow: hidden' not in body

    def test_index_card_desc_has_no_line_clamp(self):
        css_text = self._strip_comments((CSS_DIR / 'index.css').read_text(encoding='utf-8'))
        # index.css 里 .card-desc 有多处（基础 + 移动端断点），逐条检查
        bodies = re.findall(r'\.card-desc\s*\{([^}]*)\}', css_text)
        assert bodies, '.card-desc 规则不存在，测试本身可能失效'
        for body in bodies:
            assert 'line-clamp' not in body
            assert 'overflow: hidden' not in body

    def test_compact_view_keeps_its_clamp(self):
        """紧凑五列是用户主动选择的密度档，钳制是有意保留的 —— 别顺手删掉。"""
        css_text = self._strip_comments((CSS_DIR / 'charts.css').read_text(encoding='utf-8'))
        rule = re.search(
            r'\[data-grid-view="compact"\]\s+\.card\s+\.card-desc\s*\{([^}]*)\}',
            css_text,
        )
        assert rule, '紧凑模式的 .card-desc 规则不存在'
        assert 'line-clamp' in rule.group(1)


class TestBookDetailDetailsPanel:
    """问题二：详情页"详细信息"面板必须始终有可见内容。"""

    def _render(self, client, book_service, lang: str = 'zh', **overrides) -> str:
        """渲染详情页。

        `lang` 必须显式带上：`_get_locale()` 的优先级是 URL 参数 > Cookie > Accept-Language，
        不带参数时语言取决于环境残留（cookie / 前序用例），空态文案的断言会随跑法不同而红绿
        —— 手工挑子集跑时实测渲染出英文 "No detailed description available"。
        """
        book_service([_make_book(**overrides)])
        with (
            patch('app.routes.main.fetch_google_books_details'),
            patch('app.routes.main.merge_or_translate_book'),
        ):
            response = client.get(f'/book/0?category=hardcover-fiction&lang={lang}')
        assert response.status_code == 200
        return response.get_data(as_text=True)

    def test_whitespace_only_details_zh_does_not_blank_the_panel(self, client, book_service):
        """回归：details_zh='   ' 曾渲染出一个空中文块并吞掉英文分支。"""
        html = self._render(
            client,
            book_service,
            details='The real detailed description from Google Books.',
            details_zh='   ',
        )
        _, _, visible, _ = _details_panel(html)
        assert 'The real detailed description from Google Books.' in visible

    @pytest.mark.parametrize(
        ('lang', 'placeholder'),
        [('zh', '暂无详细介绍'), ('en', 'No detailed description available')],
    )
    def test_missing_details_renders_empty_state_instead_of_blank_panel(self, client, book_service, lang, placeholder):
        """回归：details 为占位串时原实现两个分支都不命中，面板整块空白。

        两个 locale 各跑一次：空态文案本身来自 `_()`，只测一侧会让"英文页回落中文"
        这类泄漏漏网（本仓已多次踩过）。
        """
        html = self._render(
            client, book_service, lang=lang, details='No detailed description available.', details_zh=None
        )
        _, _, visible, _ = _details_panel(html)
        assert visible.strip(), '面板不应为空'
        assert placeholder in visible

    def test_english_placeholder_is_not_rendered_as_content(self, client, book_service):
        html = self._render(client, book_service, details='No detailed description available.', details_zh=None)
        _, _, visible, _ = _details_panel(html)
        assert 'No detailed description available.' not in visible

    def test_chinese_details_are_primary_with_english_toggle(self, client, book_service):
        html = self._render(
            client,
            book_service,
            details='English original details.',
            details_zh='中文详细介绍内容。',
        )
        soup, _, visible, toggled_text = _details_panel(html)
        assert '中文详细介绍内容。' in visible
        assert 'English original details.' in toggled_text, '英文原文应保留在折叠块内'
        assert soup.find(id='tab-details') is not None, '有详情时"详细信息"标签页应出现'

    def test_english_only_details_are_shown_without_toggle(self, client, book_service):
        html = self._render(client, book_service, details='English only details.', details_zh=None)
        soup, _, visible, toggled_text = _details_panel(html)
        assert 'English only details.' in visible
        assert toggled_text == '', '没有中文译文时不该出现"查看英文原文"折叠块'

    def test_no_details_hides_the_tab(self, client, book_service):
        html = self._render(client, book_service, details='', details_zh=None)
        soup, _, visible, _ = _details_panel(html)
        assert soup.find(id='tab-details') is None
        assert '暂无详细介绍' in visible


class TestIndexCoverIsProxied:
    """首页卡片封面不得把境外图床地址直接交给浏览器（国内直连即占位图）。"""

    @patch('app.routes.main.fetch_google_books_details')
    @patch('app.routes.main.merge_or_translate_book')
    def test_homepage_card_cover_is_rewritten_to_same_origin_proxy(self, mock_merge, mock_fetch, client, book_service):
        nyt = 'https://static01.nyt.com/bestsellers/images/9780316608329.jpg'
        book_service([_make_book(cover='', _original_cover=nyt)])

        html = client.get('/?category=hardcover-fiction').get_data(as_text=True)

        soup = BeautifulSoup(html, 'html.parser')
        img = soup.select_one('#books-grid img')
        assert img is not None
        assert img['src'].startswith('/cover?src='), f'首页封面应改走同源代理，实际为 {img["src"]}'
        assert not img['src'].startswith('https://'), '浏览器不应直接请求境外图床'
        scripts = ' '.join(tag.get('src') or '' for tag in soup.select('script[src]'))
        assert re.search(r'cover(?:\.[a-f0-9]+)?\.min\.js|js/cover\.js', scripts), (
            f'首页必须加载 cover.js，否则冷缓存占位图不会重试。实际 script src: {scripts}'
        )


class TestBookDetailCoverIsProxied:
    """问题三的渲染侧：详情页封面不得把境外图床地址直接交给浏览器。"""

    def test_original_cover_is_rewritten_to_same_origin_proxy(self, client, book_service):
        book_service([_make_book(cover='', _original_cover='https://storage.googleapis.com/du-prd/books/images/x.jpg')])
        with (
            patch('app.routes.main.fetch_google_books_details'),
            patch('app.routes.main.merge_or_translate_book'),
        ):
            html = client.get('/book/0?category=hardcover-fiction').get_data(as_text=True)

        soup = BeautifulSoup(html, 'html.parser')
        img = soup.select_one('.detail-cover img')
        assert img is not None
        # 关键不变量：浏览器只请求同源地址。原始外链被整体编码进 src 参数是预期行为
        # （服务端要拿它回源），所以这里断言"src 是同源相对路径"而不是"不含境外域名"。
        assert img['src'].startswith('/cover?src='), f'封面应改走同源代理，实际为 {img["src"]}'
        assert not img['src'].startswith('https://'), '浏览器不应直接请求境外图床'
        assert img['data-original'].startswith('/cover?src='), '回退链上的原始封面同样要过代理'
