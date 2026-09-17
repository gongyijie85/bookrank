"""共享卡片链接 / 日期语义 / 筛选状态 的聚焦测试。

覆盖三处实际失效：
1. 卡片链接 —— 封面与书名必须指向**同一个**既有详情路由，且列表里不再显示明文 ISBN；
   BookI18n 切语言时不能把标题容器 textContent 覆盖掉内层 <a>（书名变死文本、卡片不可点）。
2. 日期语义 —— 状态只由 publication_date 决定：未来=即将出版，过去/今天=已出版，
   无日期=出版日期待确认；绝不拿 created_at（发现时间）冒充出版日期。
3. 筛选状态 —— 选中筛选后必须同时同步控件 / URL / chips / 计数 / 结果 / 分页，
   且 chip 只移除自己。
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / 'templates' / 'new_books.html'
MACROS = ROOT / 'templates' / '_macros.html'
MOBILE_TPL = ROOT / 'templates' / 'mobile' / 'new_books.html'
BOOK_I18N = ROOT / 'static' / 'js' / 'book-i18n.js'


def _read(p: Path) -> str:
    return p.read_text(encoding='utf-8')


def _zh_client(app):
    """带 zh 的测试客户端（SSR 语言由 ?lang= / lang cookie 决定）。"""
    client = app.test_client()
    client.set_cookie('lang', 'zh')
    return client


def _isolated_request(app, path: str):
    """在**自己的 app context** 里建一个请求上下文（见下方 locale 隔离用例）。

    每个请求各配一个 app context，而不是把 locale 钉成全局策略：这样 EN / ZH 两个
    请求各自解析自己的语言，互不串味。
    """
    with app.app_context():
        return app.test_request_context(path)


def _mobile_html(source, lang: str = 'en') -> str:
    """取移动端模板渲染结果：经 UA 触发 render_adaptive 的移动分支。

    `source` 可以是 Flask app，也可以是已设好 locale 的 test_client。
    """
    client = source.test_client() if hasattr(source, 'test_client') else source
    query = '?lang=' + lang if lang != 'en' else ''
    return client.get(
        '/new-books' + query,
        headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'},
    ).get_data(as_text=True)


def _seed_books(db, *, dated: bool = True) -> dict[str, int]:
    """造三本书：未来出版 / 已出版 / 无出版日期（只有发现时间）。"""
    from app.models.new_book import NewBook, Publisher

    publisher = Publisher(name='测试出版社', name_en='Test Publisher', crawler_class='TestCrawler')
    db.session.add(publisher)
    db.session.commit()

    today = date.today()
    rows = {
        'upcoming': NewBook(
            publisher_id=publisher.id,
            title='Upcoming Title',
            title_zh='未来之书',
            author='Author A',
            isbn13='9780000000001',
            category='Business',
            publication_date=today + timedelta(days=5),
            is_displayable=True,
        ),
        'published': NewBook(
            publisher_id=publisher.id,
            title='Published Title',
            title_zh='已出版之书',
            author='Author B',
            isbn13='9780000000002',
            category='Fiction',
            publication_date=today - timedelta(days=3),
            is_displayable=True,
        ),
        'pending': NewBook(
            publisher_id=publisher.id,
            title='Undated Title',
            title_zh='日期待确认之书',
            author='Author C',
            isbn13='9780000000003',
            category='Biography & Autobiography',
            publication_date=None,
            is_displayable=True,
        ),
    }
    for book in rows.values():
        db.session.add(book)
    db.session.commit()
    return {name: book.id for name, book in rows.items()}


# ---------------------------------------------------------------------------
# 1. 共享卡片：封面 + 书名指向同一详情路由
# ---------------------------------------------------------------------------


class TestSharedCardDetailLink:
    """SSR 卡片、AJAX renderBookCard、移动端都必须给出同一个详情路由。"""

    def test_ssr_card_cover_and_title_share_one_route(self, app, db, client):
        with app.app_context():
            ids = _seed_books(db)

        html = client.get('/new-books').get_data(as_text=True)

        for label, book_id in ids.items():
            card = re.search(
                rf'<div class="book-card" data-book-id="{book_id}".*?(?=<div class="book-card"|</div>\s*</div>\s*$)',
                html,
                re.S,
            )
            assert card, f'{label}: 未渲染出卡片'
            block = card.group(0)
            expected = f'/new-book/{book_id}'
            cover = re.search(r'<a class="book-cover-link" href="([^"]+)"', block)
            title = re.search(r'<div class="book-title"[^>]*>\s*<a href="([^"]+)"', block)
            assert cover, f'{label}: 封面缺少详情链接'
            assert title, f'{label}: 书名缺少详情链接'
            assert cover.group(1) == expected, f'{label}: 封面链接指向 {cover.group(1)}'
            assert title.group(1) == expected, f'{label}: 书名链接指向 {title.group(1)}'

    def test_no_nested_interactive_elements_in_cards(self, app, db, client):
        """封面/书名是链接，但不得互相嵌套（会吃掉点击目标）。"""
        with app.app_context():
            _seed_books(db)

        html = client.get('/new-books').get_data(as_text=True)
        # 书名链接里不能再出现第二个 <a>
        for block in re.findall(r'<div class="book-title"[^>]*>(.*?)</div>', html, re.S):
            assert block.count('<a ') <= 1, f'书名容器里出现嵌套链接: {block}'
        # 封面链接块里不能嵌 <a>
        for block in re.findall(r'<a class="book-cover-link".*?</a>', html, re.S):
            assert '<a ' not in block[block.index('>') + 1 :], '封面链接内部嵌套了另一个链接'

    def test_isbn_is_data_only_in_lists(self, app, db, client):
        """列表里不再有明文 ISBN；ISBN 只留在 data-isbn / data-book-id 元数据上。"""
        with app.app_context():
            _seed_books(db)

        html = client.get('/new-books').get_data(as_text=True)
        assert 'book-isbn' not in html, 'SSR 列表仍在渲染 .book-isbn 明文块'
        assert 'data-isbn="9780000000001"' in html, 'ISBN 元数据丢失，BookI18n 无法注册'

        ajax = client.get('/api/new-books?days=30').get_json()
        assert ajax['success'], ajax
        for book in ajax['data']['books']:
            assert book['isbn13'], 'API 不再返回 isbn13 元数据'

    def test_ajax_render_book_card_links_cover_and_title(self):
        """AJAX 重绘的 renderBookCard 同样给出封面 + 书名链接（同一路由）。

        断言用的是源码里的**实际**字面量（HTML 用单引号，属性用双引号）——
        写成别的引号形式会永远为假，等于没测。
        """
        body = _read(TPL)
        start = body.find('function renderBookCard(book)')
        assert start != -1, 'renderBookCard 未找到'
        end = body.find('\nfunction ', start + 10)
        card = body[start:end]

        assert '\'<a class="book-cover-link" href="\' + detailUrl' in card, 'AJAX 卡片封面缺少详情链接'
        assert "'\"><a href=\"' + detailUrl + '\">'" in card, 'AJAX 书名未指向详情路由'
        assert 'detailUrl' in card, 'AJAX 卡片没有统一的详情路由变量'
        assert 'isbnHtml' not in card, 'AJAX 卡片仍在渲染明文 ISBN'
        assert 'esc(book.isbn13 || book.isbn10' in card, 'AJAX 卡片丢了 data-isbn 元数据'

    def test_mobile_newbooks_card_links_to_detail_route(self, app, db):
        with app.app_context():
            _seed_books(db)

        html = _mobile_html(app)
        assert re.search(r'<a href="/new-book/\d+" class="m-card m-book-card">', html), '移动端新书卡片未指向详情路由'


class TestBookI18nTitleLinkPreservation:
    """BookI18n 的标题更新逻辑（真实 DOM 行为测试见 tests/test_frontend_newbooks_state.mjs）。

    这里只钉住源码结构：切语言必须走「先找内层链接」的分支，而不是无条件
    覆盖标题容器 —— 后者会把 <a> 一起抹掉。
    """

    def _fn_source(self) -> str:
        src = _read(BOOK_I18N)
        start = src.find('function _updateTitleInCard')
        assert start != -1, '_updateTitleInCard 未找到'
        end = src.find('\n    function ', start + 10)
        return src[start:end]

    def test_prefers_inner_link_over_container_text(self):
        body = self._fn_source()
        assert "querySelector('a.browse-card-title-link')" in body, '未识别卷号并排卡片的内层书名链接'
        assert "querySelector('a[href]')" in body, '缺少通用内层链接兜底'
        # 有链接时必须在改链接文本后 return，不能继续覆盖容器
        link_branch = body[body.find('if (link)') :]
        assert 'return;' in link_branch.split('}')[0] + link_branch[:40], '找到链接后仍会覆盖标题容器'

    def test_plain_heading_still_supported(self):
        body = self._fn_source()
        assert '_updateElement(titleEl, text)' in body, '纯标题（无链接）路径丢失'
        assert 'card.matches' in body, '标题即卡片本身的路径（获奖页）丢失'


# ---------------------------------------------------------------------------
# 2. 日期语义
# ---------------------------------------------------------------------------


class TestPublicationDateSemantics:
    def test_state_mapping(self):
        from app.utils.book_labels import publication_state

        today = date(2026, 1, 10)
        assert publication_state(today + timedelta(days=1), today=today) == 'upcoming'
        assert publication_state(today, today=today) == 'published'
        assert publication_state(today - timedelta(days=1), today=today) == 'published'
        assert publication_state(None, today=today) == 'pending'
        assert publication_state('', today=today) == 'pending'

    def test_labels_per_locale(self):
        """显式 locale 参数必须优先于当前渲染 locale（模板传 `_l`，见下方 app context 用例）。"""
        from app.utils.book_labels import publication_state_label

        today = date(2026, 1, 10)
        future = today + timedelta(days=3)
        past = today - timedelta(days=3)
        unknown = today + timedelta(days=1)

        assert publication_state_label(future, 'zh', today=today) == '即将出版'
        assert publication_state_label(future, 'en', today=today) == 'Upcoming'
        assert publication_state_label(past, 'zh', today=today) == '已出版'
        assert publication_state_label(past, 'en', today=today) == 'Published'
        assert publication_state_label(unknown, 'zh', today=today) == '即将出版'
        assert publication_state_label(unknown, 'en', today=today) == 'Upcoming'
        assert publication_state_label(None, 'zh', today=today) == '出版日期待确认'
        assert publication_state_label(None, 'en', today=today) == 'Publication date pending'
        # locale 前缀（zh_CN / en-US）与其它 display helper 同口径
        assert publication_state_label(future, 'zh_CN', today=today) == '即将出版'
        assert publication_state_label(future, 'en-US', today=today) == 'Upcoming'

    def test_locale_is_isolated_per_request_context(self, app):
        """EN / ZH 请求各自解析出自己的语言（上下文隔离，而非全局策略）。

        这里给每个请求配一个独立的 app context（而不是共用同一个）：EN 请求解析出 en、
        ZH 请求解析出 zh，两者互不串味。断言的是 `get_locale()` 的**可观察行为**，
        不碰 Flask-Babel 内部的缓存属性。
        """
        from flask_babel import get_locale

        from app.utils.book_labels import publication_state_label

        today = date(2026, 1, 10)
        future = today + timedelta(days=3)

        with _isolated_request(app, '/new-books?lang=en'):
            assert str(get_locale()).startswith('en'), 'EN 请求的 locale 解析失败'
        with _isolated_request(app, '/new-books?lang=zh'):
            assert str(get_locale()).startswith('zh'), 'ZH 请求的 locale 解析失败'

        # 状态文案按显式传入的 locale 渲染
        assert publication_state_label(future, 'en', today=today) == 'Upcoming'
        assert publication_state_label(future, 'zh', today=today) == '即将出版'

    def test_ssr_templates_pass_the_resolved_locale_explicitly(self):
        """两处模板调用点都要把 `_l` 传给日期状态过滤器（不靠 app context 缓存）。"""
        macro = _read(MACROS)
        assert macro.count('publication_state_label(_l)') == 2, '宏未显式传入已解析的 _l'
        assert 'publication_state_label }}' not in macro, '仍有依赖 app context 缓存的调用'
        mobile = _read(MOBILE_TPL)
        assert 'publication_state_label(_l)' in mobile, '移动端未显式传入已解析的 _l'

    def test_ssr_language_switches_in_one_context(self, app, db):
        """同一 app context 内先 EN 后 ZH 渲染整页：日期状态各自正确（真实渲染路径）。"""
        with app.app_context():
            _seed_books(db)
            client = app.test_client()
            en_html = client.get('/new-books').get_data(as_text=True)
            zh_html = client.get('/new-books?lang=zh').get_data(as_text=True)

        assert 'Upcoming' in en_html, 'EN 页未渲染英文日期状态'
        assert 'Published' in en_html, 'EN 页未渲染英文「已出版」'
        assert '即将出版' in zh_html, 'ZH 页未渲染中文日期状态'
        assert '已出版' in zh_html, 'ZH 页未渲染中文「已出版」'
        # 只在日期标签块内判定泄漏：卡片上的 data-en="Upcoming Title" 是书名，不是状态文案
        zh_tags = ' '.join(re.findall(r'<span class="book-tag tag-date[^"]*"[^>]*>(.*?)</span>', zh_html, re.S))
        assert zh_tags, 'ZH 页未渲染日期标签'
        assert 'Upcoming' not in zh_tags, 'ZH 页日期标签泄漏了英文状态'
        assert 'Published' not in zh_tags, 'ZH 页日期标签泄漏了英文「已出版」'
        en_tags = ' '.join(re.findall(r'<span class="book-tag tag-date[^"]*"[^>]*>(.*?)</span>', en_html, re.S))
        assert 'Upcoming' in en_tags and 'Published' in en_tags, 'EN 页日期标签缺英文状态'
        assert '即将出版' not in en_tags, 'EN 页日期标签泄漏了中文状态'

    def test_ssr_renders_each_state(self, app, db, client):
        with app.app_context():
            _seed_books(db)

        html = client.get('/new-books').get_data(as_text=True)
        assert '即将出版' in html, '未来出版日期未标注「即将出版」'
        assert '已出版' in html, '过去出版日期未标注「已出版」'
        assert '出版日期待确认' in html, '无日期未标注「出版日期待确认」'

    def test_ssr_never_treats_discovery_time_as_publication_date(self, app, db, client):
        """只有 created_at 的书不得被说成已出版，也不得显示 created_at 当日期。"""
        from app.models.new_book import NewBook, Publisher

        with app.app_context():
            publisher = Publisher(name='发现时间社', name_en='Discovery Co', crawler_class='TestCrawler')
            db.session.add(publisher)
            db.session.commit()
            db.session.add(
                NewBook(
                    publisher_id=publisher.id,
                    title='Discovered Today',
                    title_zh='今天被发现的书',
                    author='Author D',
                    isbn13='9780000000999',
                    category='Fiction',
                    publication_date=None,
                    created_at=datetime.now(UTC),
                    is_displayable=True,
                )
            )
            db.session.commit()

        # 显式请求中文页：默认 EN 页渲染的是英文待确认文案（'Publication date pending'），
        # 下面断言的是中文可见标签，必须走 zh 渲染路径，不能靠缺译时的中文兜底。
        html = _zh_client(app).get('/new-books?lang=zh').get_data(as_text=True)
        # 按真实 DOM 结构取卡片：手写正则表达"卡片边界"既脆又会自相矛盾
        # （把 body 切到日期标签之前，再去 body 里找那个标签）。
        soup = BeautifulSoup(html, 'html.parser')
        card = soup.select_one('.book-card[data-isbn="9780000000999"]')
        # 卡片必须真的渲染出来，否则后面的断言会退化成"空东西里找不到坏东西"而静默通过。
        assert card, '未渲染出「今天被发现的书」的卡片'
        # 无日期卡片必须带待确认徽章，且文案是「出版日期待确认」
        date_tag = card.select_one('.tag-date.tag-muted')
        assert date_tag, '无日期卡片未渲染 tag-date tag-muted 待确认徽章'
        assert '出版日期待确认' in date_tag.get_text(), '无 publication_date 时未标注待确认'
        # created_at（发现时间）不得被当成出版日期渲染到卡片可见文本里
        assert date.today().isoformat() not in card.get_text(), '发现时间（created_at）被当成了出版日期渲染'

    def test_ajax_matches_ssr_date_semantics(self, app, db, client):
        with app.app_context():
            _seed_books(db)

        payload = client.get('/api/new-books?days=30').get_json()
        assert payload['success'], payload
        by_title = {b['title']: b for b in payload['data']['books']}

        from app.utils.book_labels import publication_state

        assert publication_state(by_title['Upcoming Title']['publication_date']) == 'upcoming'
        assert publication_state(by_title['Published Title']['publication_date']) == 'published'
        assert by_title['Undated Title']['publication_date'] is None

    def test_mobile_renders_date_states(self, app, db):
        """移动端同一张卡片用 locale 感知的状态文案（en 页给 Upcoming/Published）。"""
        with app.app_context():
            _seed_books(db)

        html = _mobile_html(app)
        meta = re.findall(r'<p class="m-book-card-meta">(.*?)</p>', html, re.S)
        assert meta, '移动端未渲染卡片元信息'
        assert any('Upcoming' in m or '已出版' in m or 'Published' in m for m in meta), (
            f'移动端未渲染日期状态: {meta[:3]}'
        )
        assert any('出版日期待确认' in m or 'Publication date pending' in m for m in meta), '移动端未标注待确认日期'

        zh_meta = re.findall(
            r'<p class="m-book-card-meta">(.*?)</p>',
            _mobile_html(app, lang='zh'),
            re.S,
        )
        assert any('即将出版' in m for m in zh_meta), f'移动端中文页缺「即将出版」: {zh_meta[:3]}'
        assert any('已出版' in m for m in zh_meta), f'移动端中文页缺「已出版」: {zh_meta[:3]}'
        assert any('出版日期待确认' in m for m in zh_meta), '移动端中文页缺「出版日期待确认」'

    def test_window_scope_still_past_days_plus_future_14(self):
        """窗口口径未被本次改动放宽/收紧：过去 N 天 + 未来 14 天 + 近期无日期。"""
        from app.services.new_book.query_service import NewBookQueryService

        src = NewBookQueryService._apply_publication_window.__doc__ or ''
        code = NewBookQueryService._apply_publication_window
        import inspect

        body = inspect.getsource(code)
        assert 'timedelta(days=14)' in body, '未来预告窗口不再是 14 天'
        assert 'created_at' in body, '近期无日期书目不再按发现时间纳入'
        assert 'future_grace_date' in src or 'publication_date' in body


# ---------------------------------------------------------------------------
# 3. 分类规范映射（中文页不再显示英文别名）
# ---------------------------------------------------------------------------


class TestCategoryCanonicalMapping:
    def test_chinese_locale_maps_english_aliases(self):
        from app.utils.book_labels import category_name

        assert category_name('Business', 'zh') == '商业'
        assert category_name('Fiction', 'zh') == '小说'
        assert category_name('Biography & Autobiography', 'zh') == '传记'
        assert category_name('商业', 'zh') == '商业'

    def test_unknown_alias_stays_honest(self):
        from app.utils.book_labels import category_name

        assert category_name('Nonesuch Genre', 'zh') == 'Nonesuch Genre'
        assert category_name('Nonesuch Genre', 'en') == 'Nonesuch Genre'

    def test_reuses_publisher_data_single_source_of_truth(self):
        from app.services.publisher_data import CATEGORY_EN_TO_ZH
        from app.utils.book_labels import category_alias_labels

        labels = category_alias_labels()
        assert labels.get('Business') == CATEGORY_EN_TO_ZH['Business']
        # 不另建部分表：导出的就是同一份键集
        assert set(labels) == set(CATEGORY_EN_TO_ZH)

    def test_api_exposes_category_zh(self, app, db, client):
        with app.app_context():
            _seed_books(db)

        payload = client.get('/api/new-books?days=30').get_json()
        books = {b['title']: b for b in payload['data']['books']}
        assert books['Upcoming Title']['category_zh'] == '商业', 'AJAX 缺 category_zh'
        assert books['Undated Title']['category_zh'] == '传记', '同义英文别名未归一'

    def test_ssr_chinese_page_shows_chinese_category(self, app, db):
        with app.app_context():
            _seed_books(db)

        html = _zh_client(app).get('/new-books?lang=zh').get_data(as_text=True)
        assert '商业' in html, 'SSR 中文页未显示中文分类'
        assert re.search(r'tag-category">Business<', html) is None, '中文页仍显示英文别名 Business'

    def test_ajax_render_uses_category_zh(self):
        body = _read(TPL)
        assert 'book.category_zh' in body, 'AJAX 卡片未使用 category_zh'


# ---------------------------------------------------------------------------
# 3b. 双语数据载荷（data-cat-* / data-date-* / data-just-*）不得随 SSR 语言翻转
# ---------------------------------------------------------------------------


class TestBilingualPayload:
    """`data-*-zh` 槽位在任何 SSR 语言下都必须是中文。

    历史 bug：用当前 locale 的 gettext 生成 zh 槽位（`data-date-zh="{{ _('即将出版') }}"`），
    英文目录填好后 EN 渲染会把 'Upcoming' 写进 zh 槽位，EN→ZH 再也切不回中文。

    允许**显式指定语言**的 helper 表达式（`publication_state_label('zh')` /
    `category_name('zh')`）：它们与后端固定中文表同源，与 SSR locale 无关，正是正确写法。
    禁止的是当前 locale 的 gettext（`_(...)`），它的结果会随 SSR 语言翻转。
    """

    def _attrs(self, html: str, attr: str) -> list[str]:
        return re.findall(rf'{attr}="([^"]*)"', html)

    def test_macros_zh_slots_avoid_current_locale_gettext(self):
        macro = _read(MACROS)
        for attr in ('data-date-zh', 'data-just-zh', 'data-cat-zh'):
            for value in re.findall(rf'{attr}="([^"]*)"', macro):
                # 只要不是「当前 locale 的 gettext」，显式 locale helper 与字面量都合法
                assert '{{ _(' not in value, f'{attr} 仍由当前 locale 的 gettext 生成（会随 SSR 语言翻转）: {value}'
        assert 'data-date-zh="出版日期待确认"' in macro, '无日期卡片缺固定中文 data-date-zh'
        assert 'data-just-zh="刚上市"' in macro, '「刚上市」徽标缺固定中文 data-just-zh'

    def test_ssr_en_page_keeps_chinese_zh_slots(self, app, db):
        with app.app_context():
            _seed_books(db)

        en_html = app.test_client().get('/new-books').get_data(as_text=True)
        date_zh = self._attrs(en_html, 'data-date-zh')
        assert date_zh, 'EN 页未渲染 data-date-zh 载荷'
        assert '即将出版' in date_zh, 'EN 页 zh 槽位丢了中文「即将出版」'
        assert '已出版' in date_zh, 'EN 页 zh 槽位丢了中文「已出版」'
        assert '出版日期待确认' in date_zh, 'EN 页 zh 槽位丢了中文「出版日期待确认」'
        for value in date_zh:
            assert 'Upcoming' not in value and 'Published' not in value, f'EN 页 zh 槽位被英文污染: {value}'

    def test_ssr_zh_page_keeps_english_en_slots(self, app, db):
        with app.app_context():
            _seed_books(db)

        zh_html = _zh_client(app).get('/new-books?lang=zh').get_data(as_text=True)
        date_en = self._attrs(zh_html, 'data-date-en')
        assert date_en, 'ZH 页未渲染 data-date-en 载荷'
        assert 'Upcoming' in date_en and 'Published' in date_en, 'ZH 页 en 槽位缺英文状态'
        for value in date_en:
            assert '即将出版' not in value and '已出版' not in value, f'ZH 页 en 槽位被中文污染: {value}'

    def test_category_slots_are_canonical_both_ways(self, app, db):
        with app.app_context():
            _seed_books(db)

        html = app.test_client().get('/new-books').get_data(as_text=True)
        # 用解析后的 DOM（实体已解码，且不含内联脚本文本）而不是正则扫源码：
        # 源码里的 '&amp;' 与脚本内拼出的属性串都会让正则得到假象。
        soup = BeautifulSoup(html, 'html.parser')
        pairs = {(el.get('data-cat-zh'), el.get('data-cat-en')) for el in soup.select('[data-cat-zh][data-cat-en]')}
        assert pairs, '未渲染 data-cat-zh / data-cat-en 载荷'
        assert ('商业', 'Business') in pairs, f'分类双语槽位不是规范值: {sorted(pairs)}'
        assert ('传记', 'Biography & Autobiography') in pairs, f'同义别名未归一: {sorted(pairs)}'
        # 过滤选项用 canonicalize 后的短名，两种写法都必须各自规范（不混淆、不丢值）
        assert all(zh and en for zh, en in pairs), f'分类槽位有空值: {sorted(pairs)}'

    def test_all_publishers_option_zh_slot_is_chinese(self, app, db):
        with app.app_context():
            _seed_books(db)

        html = app.test_client().get('/new-books').get_data(as_text=True)
        option = re.search(r'<option value=""[^>]*data-pub-name-zh="([^"]*)"', html)
        assert option, '「全部出版社」选项缺 data-pub-name-zh'
        assert option.group(1) == '全部出版社', f'EN 页 zh 槽位被英文污染: {option.group(1)}'

    def test_mobile_zh_slots_are_chinese(self, app, db):
        with app.app_context():
            _seed_books(db)

        html = _mobile_html(app)  # en
        assert 'data-date-zh="出版日期待确认"' in html, '移动端 EN 页 zh 槽位被污染'
        mobile_src = _read(MOBILE_TPL)
        for value in re.findall(r'data-date-zh="([^"]*)"', mobile_src):
            assert '{{' not in value or 'publication_state_label' in value, f'移动端 zh 槽位由 gettext 生成: {value}'


# ---------------------------------------------------------------------------
# 4. 筛选状态机（源码级行为断言 + 渲染级检查）
# ---------------------------------------------------------------------------


class TestFilterStateMachine:
    def _script(self) -> str:
        body = _read(TPL)
        start = body.find('<script nonce=')
        end = body.rfind('</script>')
        return body[start:end]

    def test_single_source_of_truth_helpers_exist(self):
        script = self._script()
        for fn in (
            'readFilterState',
            'buildQueryString',
            'parseQueryString',
            'syncControls',
            'syncFilterChrome',
            'restoreFromUrl',
            'resetFilters',
            'chipUrlWithout',
        ):
            assert f'function {fn}' in script, f'缺少筛选状态函数 {fn}'

    def test_apply_filter_syncs_chrome_and_url(self):
        script = self._script()
        start = script.find('function applyFilter(')
        end = script.find('\nfunction ', start + 10)
        body = script[start:end]
        assert 'loadBooks(queryString, { push: true })' in body, '控件改动未 pushState'
        assert 'readFilterState()' in body, 'applyFilter 未从控件读 state'

    def test_history_push_only_on_user_action(self):
        script = self._script()
        # 恢复路径必须 replace，语言重绘也必须 replace
        assert 'loadBooks(buildQueryString(parsed.state, parsed.page), { replace: true })' in script
        assert script.count('{ replace: true }') >= 2, '语言重绘未走 replaceState'
        assert 'sameQueryString(queryString)' in script, '相同条件仍会重复 pushState'
        # popstate 监听不得 pushState
        pop = script.find("window.addEventListener('popstate'")
        assert pop != -1, '缺少 popstate 监听'
        assert 'restoreFromUrl()' in script[pop : pop + 200]

    def test_chip_removal_preserves_other_conditions(self):
        script = self._script()
        start = script.find('function chipUrlWithout(')
        end = script.find('\nfunction ', start + 10)
        body = script[start:end]
        assert 'delete state[key]' in body, 'chip 移除不是只删自己'
        assert 'buildQueryString(state, 1)' in body

        # 真实 SSR chip 链接也保留 days 与其它条件
        html_doc = _read(TPL)
        assert 'data-chip-key="category"' in html_doc
        assert 'data-chip-key="publisher"' in html_doc
        assert 'data-chip-key="search"' in html_doc

    def test_chip_urls_preserve_other_conditions_rendered(self, app, db, client):
        with app.app_context():
            _seed_books(db)

        html = client.get('/new-books?category=商业&days=30&search=Title').get_data(as_text=True)
        category_chip = re.search(r'<a class="filter-chip" href="([^"]+)" data-chip-key="category"', html)
        assert category_chip, '选中分类后没有渲染分类 chip'
        href = category_chip.group(1).replace('&amp;', '&')
        assert 'category=' not in href, '移除分类的 chip 仍带着分类'
        assert 'search=Title' in href, '移除分类时丢了搜索条件'
        assert 'days=30' in href, '移除分类时丢了时间窗口'

    def test_selected_filter_renders_chip_on_ssr(self, app, db, client):
        with app.app_context():
            _seed_books(db)

        html = client.get('/new-books?category=商业&days=180').get_data(as_text=True)
        assert 'data-chip-key="category"' in html, 'SSR 选中筛选未渲染 chip'
        assert re.search(r'<option value="商业"[^>]*selected', html), '下拉框未回填选中项'

    def test_language_source_is_current_language_not_stale_global(self):
        script = self._script()
        assert 'window.__APP_LANG__' in script  # 仅用于初始化
        start = script.find('function updateResultSummary')
        end = script.find('\nfunction ', start + 10)
        body = script[start:end]
        assert 'currentLanguage' in body, '计数/范围徽章仍读 stale window.__APP_LANG__'
        assert 'window.__APP_LANG__' not in body, '计数/范围徽章使用了页面加载期的旧语言'

    def test_reset_uses_state_pipeline_not_full_reload(self):
        script = self._script()
        start = script.find("document.getElementById('btn-clear')")
        assert start != -1, 'btn-clear 绑定丢失'
        body = script[start : start + 220]
        assert 'resetFilters()' in body, '重置仍是整页跳转'
        assert 'window.location.href = \'{{ url_for("main.new_books") }}\'' not in script

    def test_load_and_retry_behaviour_preserved(self):
        script = self._script()
        assert 'id="btn-retry"' in script, '错误态重试按钮丢失'
        assert 'loading-skeleton' in script, '加载骨架丢失'
        assert 'isLoading = false;' in script, 'isLoading 未复位'

    def test_concurrent_requests_use_latest_request_strategy(self):
        """加载中改选/返回不得丢弃新请求：AbortController + 请求代次判定，最新者胜出。

        真实行为由 tests/test_frontend_newbooks_state.mjs 的 DOM 级用例覆盖，
        这里只钉住源码结构（防止有人把 `if (isLoading) return` 恢复回来）。
        """
        script = self._script()
        start = script.find('function loadBooks(')
        end = script.find('\nfunction ', start + 10)
        body = script[start:end]
        # 只看可执行行（注释里描述历史 bug 时会提到旧写法）
        code = '\n'.join(line for line in body.splitlines() if not line.strip().startswith(('//', '/*', '*', '*/')))
        assert 'if (isLoading) return' not in code, 'loadBooks 仍在丢弃并发请求'
        assert 'AbortController' in body, '未中止被取代的在途请求'
        assert 'loadSeq' in body, '缺少请求代次（latest-request）判定'
        # 三处归属判定：完成 / 失败 / finally（复位 isLoading 与 inFlightController）
        assert body.count('reqId !== loadSeq') >= 3, '完成/失败/复位路径未丢弃过期请求'
        # isLoading 必须仍在 fetch 之前置真、且只在最新请求的 finally 里复位：
        # 提前复位会让 languagechange 以为"没有在途请求"，从而中止并重发一次。
        assert body.index('isLoading = true;') < body.index('fetch(url'), 'isLoading 未在请求前置于真'
        finally_block = body[body.index('.finally(') :]
        assert 'if (reqId !== loadSeq) return;' in finally_block, 'finally 未做代次判定'
        assert 'isLoading = false;' in finally_block, 'isLoading 未由最新请求的 finally 复位'
        assert 'inFlightController = null;' in finally_block, 'inFlightController 未由 finally 释放'
        assert body.count('isLoading = false;') == 1, 'isLoading 存在提前复位的第二处'
        # 快照请求时的 state：响应回来时控件可能已被改成别的条件
        assert 'requestState' in body, '未捕获本次请求的筛选状态'
        assert 'new URLSearchParams(queryString)' not in code, '仍直接读可变 queryString'

    def test_card_click_does_not_hijack_title_link(self):
        script = self._script()
        start = script.find("document.getElementById('books-container')?.addEventListener('click'")
        body = script[start : start + 400]
        assert "e.target.closest('a[href]')" in body, '整卡跳转仍会覆盖标题链接'


class TestNarrowFilterLayout:
    """390px 下筛选栏不得互相压盖：两列栅格 + 全宽搜索 + ≥44px 主控件。"""

    def test_scoped_two_column_layout_added(self):
        css = _read(ROOT / 'static' / 'css' / 'charts.css')
        scope = css[css.find('.charts-page.awards-page .filter-bar,') :]
        assert '.charts-page.new-books-page .filter-bar' in scope
        assert 'grid-template-columns: repeat(2, minmax(0, 1fr))' in scope
        assert 'grid-column: 1 / -1' in scope, '搜索未占满整行，仍会与 select 压盖'
        assert 'min-width: 0' in scope, '未消掉 min-width 与 flex-shrink 的对抗'

    def test_primary_controls_are_touch_sized(self):
        css = _read(ROOT / 'static' / 'css' / 'charts.css')
        scope = css[css.find('.charts-page.awards-page .filter-bar,') :]
        assert 'min-height: 44px' in scope, '窄视口主控件不足 44px'

    def test_meta_and_chip_font_sizes(self):
        css = _read(ROOT / 'static' / 'css' / 'charts.css')
        scope = css[css.find('.charts-page.awards-page .filter-bar,') :]
        assert 'font-size: 13px' in scope, 'chips/元信息字号未落到 13–14px'

    def test_mobile_publisher_search_is_touch_sized(self):
        tpl = _read(ROOT / 'templates' / 'mobile' / 'publishers.html')
        assert 'min-height:44px' in tpl, '移动端出版社搜索框不足 44px'

    def test_mobile_newbooks_primary_controls(self):
        tpl = _read(MOBILE_TPL)
        assert tpl.count('min-height:44px') >= 4, '移动端新书筛选主控件不足 44px'

    def test_mobile_category_tabs_are_touch_sized(self):
        css = _read(ROOT / 'static' / 'mobile' / 'css' / 'mobile.css')
        tab = css[css.find('.m-cat-tab {') :]
        tab = tab[: tab.find('}')]
        assert 'min-height' in tab, '移动端分类 chip 触控高度未定义'
