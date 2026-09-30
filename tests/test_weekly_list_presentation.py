"""周报列表 / rail / 移动列表 / 详情面包屑的前端 Jinja 渲染回归测试。

覆盖缺陷（Leader 真实浏览器复现）：GET /reports/weekly?lang=en 的卡片标题仍是中文
标准标题「纽约时报畅销书周报」、月份徽标硬编码「09月」、统计口径显示
「Total books: 15 books」（15 实为跨分类上榜条目数，非去重书数），与详情页
「NYT Weekly Bestseller Report」「15 List entries」不一致；卡片 data-title 与
详情页 <title>/og/twitter/JSON-LD headline 仍取 report.title，与显示标题脱节。

口径约定（与 app/utils/weekly_report_presentation.py 一致）：
- total_* 展示为「上榜记录 / List entries」，单位「条 / entries」，绝不用「本 / books」；
- 模板只本地化系统标准标题（title_display），任意人工 DB 标题原样透传；
- 未知总量按 *_known 门控整项不渲染，绝不臆造为 0；已知 0 照常显示；
- 搜索 JS 读取的 data-title 必须与卡片可见标题同源。

HTML 提取一律用 stdlib html.parser 的简单提取器（不用正则反复匹配，避免
CodeQL 指出的回溯风险与对换行/空白的过度依赖）。

模板渲染与路由 main.py:1355 一致：content_data 由 prepare_report_presentation(report,
locale=...)['content'] 附着后渲染。测试不触发真实路由（避免 expected-week 自愈线程），
但在渲染前调用 app.preprocess_request() 走真实的 before_request 流程，初始化
g.csp_nonce——否则模板里 `nonce or csp_nonce()` 的兜底分支会命中导入宏上下文中
不存在的 csp_nonce 函数（不为此削弱生产 CSP 或改生产宏）。
"""

import json
from datetime import date
from html.parser import HTMLParser

from flask import render_template

from app.models.schemas import WeeklyReport
from app.utils.weekly_report_presentation import prepare_report_presentation

STANDARD_TITLE = '纽约时报畅销书周报'
STANDARD_TITLE_EN = 'NYT Weekly Bestseller Report'
CUSTOM_TITLE = '年中盘点：编辑荐书特辑'


def _content(total_books=15, total_new=3, total_rising=4, total_falling=2):
    return {
        'total_books': total_books,
        'total_new': total_new,
        'total_rising': total_rising,
        'total_falling': total_falling,
        'new_books': [],
        'top_changes': [],
        'featured_books': [],
        'top_risers': [],
        'longest_running': [],
        'category_stats': {},
    }


def _make_report(db, title, week_start, week_end, content, locale):
    report = WeeklyReport(
        report_date=week_end,
        week_start=week_start,
        week_end=week_end,
        title=title,
        summary='',
        content=json.dumps(content, ensure_ascii=False),
    )
    db.session.add(report)
    db.session.commit()
    # 与 routes/main.py 列表路由同样的附着方式
    report.content_data = prepare_report_presentation(report, locale=locale)['content']
    return report


def _sections(reports):
    groups: dict[tuple[int, int], list] = {}
    for report in reports:
        groups.setdefault((report.report_date.year, report.report_date.month), []).append(report)
    return [{'year': y, 'month': m, 'reports': rs} for (y, m), rs in sorted(groups.items(), reverse=True)]


def _render(app, template, reports, path):
    with app.test_request_context(path):
        app.preprocess_request()  # 真实 before_request：生成 g.csp_nonce
        return render_template(
            template,
            reports=reports,
            report_sections=_sections(reports),
            latest_report=reports[0] if reports else None,
            is_generating=False,
            active_tab='weekly',
        )


def _render_detail(app, report, path):
    prepared = prepare_report_presentation(report, locale='en' if 'lang=en' in path else 'zh')
    with app.test_request_context(path):
        app.preprocess_request()  # 真实 before_request：生成 g.csp_nonce
        return render_template(
            'weekly_report_detail.html',
            report=report,
            content=prepared['content'],
            safe_summary=prepared['summary'],
            summary_source=prepared['summary_source'],
            active_tab='weekly',
        )


class _TextsExtractor(HTMLParser):
    """收集目标 tag(+class 命中) 元素的可见文本，空白归一化。

    同 tag 嵌套计数配对（如 h3 内再套 h3 时不提前截断）；只依赖标签结构，
    不做正则反复匹配。
    """

    def __init__(self, tag, cls):
        super().__init__(convert_charrefs=True)
        self._tag = tag
        self._cls = cls
        self.items = []
        self._depth = 0
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if self._depth:
            if tag == self._tag:
                self._depth += 1
            return
        if tag != self._tag:
            return
        if self._cls is not None and self._cls not in dict(attrs).get('class', '').split():
            return
        self._depth = 1
        self._buf = []

    def handle_endtag(self, tag):
        if self._depth and tag == self._tag:
            self._depth -= 1
            if self._depth == 0:
                self.items.append(' '.join(''.join(self._buf).split()))

    def handle_data(self, data):
        if self._depth:
            self._buf.append(data)


def _texts(html, tag, cls=None):
    parser = _TextsExtractor(tag, cls)
    parser.feed(html)
    return parser.items


class _AttrsExtractor(HTMLParser):
    """收集 tag(+class 命中) 元素的属性字典列表（用于 data-* 契约）。"""

    def __init__(self, tag, cls):
        super().__init__(convert_charrefs=True)
        self._tag = tag
        self._cls = cls
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag != self._tag:
            return
        a = dict(attrs)
        if self._cls is not None and self._cls not in a.get('class', '').split():
            return
        self.rows.append(a)


def _card_attrs(html):
    parser = _AttrsExtractor('div', 'report-card')
    parser.feed(html)
    return parser.rows


class _MetaExtractor(HTMLParser):
    def __init__(self, attr, key):
        super().__init__(convert_charrefs=True)
        self._attr = attr
        self._key = key
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag != 'meta':
            return
        a = dict(attrs)
        if a.get(self._attr) == self._key:
            self.values.append(a.get('content', ''))


def _meta_content(html, key):
    attr = 'property' if key.startswith('og:') else 'name'
    parser = _MetaExtractor(attr, key)
    parser.feed(html)
    return parser.values


class _JsonLdExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._buf = None
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type') == 'application/ld+json':
            self._buf = []

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._buf is not None:
            self.documents.append(json.loads(''.join(self._buf)))
            self._buf = None


def _json_ld_documents(html):
    parser = _JsonLdExtractor()
    parser.feed(html)
    return parser.documents


def _article_headline(html):
    for doc in _json_ld_documents(html):
        if doc.get('@type') == 'Article':
            return doc.get('headline')
    return None


# ---- 英文列表页：标题 / 月份 / 统计口径与详情一致 ----


def test_en_list_card_title_month_and_stats_match_detail(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=en')

    # 卡片标题走 title_display，与详情页一致
    assert _texts(html, 'h3', 'news-title') == [STANDARD_TITLE_EN]
    # 月份徽标不再出现中文「09月」
    assert '09月' not in html
    assert _texts(html, 'span', 'news-month') == ['09']
    # 统计口径：与详情同为 List entries，绝不出现 Total books / "15 books"
    assert 'Total books' not in html
    assert '15 books' not in html
    assert 'List entries：15' in html


def test_zh_list_card_title_month_and_stats(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'zh')
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=zh')

    assert _texts(html, 'h3', 'news-title') == [STANDARD_TITLE]
    assert _texts(html, 'span', 'news-month') == ['09月']
    # 中文口径同步收敛到「上榜记录」（与详情一致），不再出现「总书数」
    assert '总书数' not in html
    assert '上榜记录：15' in html


# ---- 搜索契约：data-title 与卡片可见标题同源 ----


def test_card_data_title_matches_visible_title(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=en')

    # 搜索 JS 读 data-title：英文页必须是英文显示标题，否则搜「NYT」漏卡
    cards = _card_attrs(html)
    assert [c.get('data-title') for c in cards] == _texts(html, 'h3', 'news-title')
    assert [c.get('data-title') for c in cards] == [STANDARD_TITLE_EN]

    # 人工标题两侧同源：data-title 也是原样透传的自定义标题
    report.title = CUSTOM_TITLE
    report.content_data = prepare_report_presentation(report, locale='en')['content']
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=en')
    cards = _card_attrs(html)
    assert [c.get('data-title') for c in cards] == _texts(html, 'h3', 'news-title')
    assert [c.get('data-title') for c in cards] == [CUSTOM_TITLE]


# ---- 横向 rail ----


def test_en_cards_use_title_display_and_entry_counts_without_rail(app, db):
    sep = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    aug = _make_report(
        db,
        CUSTOM_TITLE,
        date(2026, 8, 24),
        date(2026, 8, 30),
        _content(total_books=8, total_new=0),
        'en',
    )
    html = _render(app, 'weekly_reports.html', [sep, aug], '/reports/weekly?lang=en')

    # 冗余浏览侧栏(browse-report-title rail)已移除:结果集合只出现一次。
    assert _texts(html, 'span', 'browse-report-title') == []

    cards = _card_attrs(html)
    assert len(cards) == 2, f'expected exactly one result collection with two cards, got {len(cards)}'

    titles = _texts(html, 'h3', 'news-title')
    # EN 显示标题走 title_display;人工标题原样保留。
    assert STANDARD_TITLE_EN in titles
    assert CUSTOM_TITLE in titles

    months = _texts(html, 'span', 'news-month')
    assert '09' in months and '08' in months
    assert all('月' not in m for m in months)

    # 条目口径计数保留:英文页显示 entries,不再出现 books。
    assert '15 entries' in html
    assert '15 books' not in html


# ---- 任意人工 DB 标题保持原样，不被翻译 ----


def test_custom_db_title_preserved_verbatim_in_en(app, db):
    report = _make_report(db, CUSTOM_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=en')

    assert _texts(html, 'h3', 'news-title') == [CUSTOM_TITLE]
    assert STANDARD_TITLE_EN not in html


# ---- 未知总量不臆造 0，已知 0 照常显示 ----


def test_unknown_totals_omitted_not_zero(app, db):
    report = _make_report(
        db,
        STANDARD_TITLE,
        date(2026, 9, 21),
        date(2026, 9, 27),
        _content(total_new=None, total_rising=0, total_falling=None),
        'en',
    )
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=en')

    # 未知项整项不渲染（不以 0 顶替）
    assert 'New on list' not in html
    assert 'Falling' not in html
    # 已知 0 仍显示 0
    assert 'Rising：0' in html


def test_unknown_totals_omitted_in_zh(app, db):
    report = _make_report(
        db,
        STANDARD_TITLE,
        date(2026, 9, 21),
        date(2026, 9, 27),
        _content(total_new=None, total_rising=0, total_falling=None),
        'zh',
    )
    html = _render(app, 'weekly_reports.html', [report], '/reports/weekly?lang=zh')

    assert '新上榜：0' not in html
    assert '下降：0' not in html
    assert '上升：0' in html
    assert '上榜记录：15' in html


# ---- 移动列表页 ----


def test_mobile_list_title_localized_and_entries_label(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render(app, 'mobile/weekly_reports.html', [report], '/reports/weekly?lang=en')

    assert _texts(html, 'h3', 'm-report-title') == [STANDARD_TITLE_EN]
    assert 'Total books' not in html
    assert len(_texts(html, 'p', 'm-report-sub')) == 1
    assert '15 entries' in _texts(html, 'p', 'm-report-sub')[0]
    assert _texts(html, 'span', 'm-report-chip') == ['New on list 3', 'Rising 4', 'Falling 2']
    assert '15 books' not in html


def test_mobile_list_custom_title_preserved(app, db):
    report = _make_report(db, CUSTOM_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render(app, 'mobile/weekly_reports.html', [report], '/reports/weekly?lang=en')

    assert _texts(html, 'h3', 'm-report-title') == [CUSTOM_TITLE]


# ---- 详情页面包屑 ----


def test_detail_breadcrumb_uses_title_display(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render_detail(app, report, '/reports/weekly/2026-09-27?lang=en')

    assert _texts(html, 'span', 'breadcrumb-current') == [STANDARD_TITLE_EN]


def test_detail_breadcrumb_zh_and_custom(app, db):
    standard = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'zh')
    html = _render_detail(app, standard, '/reports/weekly/2026-09-27?lang=zh')
    assert _texts(html, 'span', 'breadcrumb-current') == [STANDARD_TITLE]

    # 人工标题场景在同一对象上改标题后重新渲染（_render_detail 内部重新
    # prepare），不再插入第二条同 week_start/week_end 的记录，尊重唯一约束。
    standard.title = CUSTOM_TITLE
    html = _render_detail(app, standard, '/reports/weekly/2026-09-27?lang=en')
    # 人工标题在面包屑也保持原样
    assert _texts(html, 'span', 'breadcrumb-current') == [CUSTOM_TITLE]


# ---- 详情页 <title> / og / twitter / JSON-LD headline 与正文标题一致 ----


def test_detail_head_and_jsonld_use_title_display(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    html = _render_detail(app, report, '/reports/weekly/2026-09-27?lang=en')

    assert _texts(html, 'title') == [f'{STANDARD_TITLE_EN} - BookRank']
    assert _meta_content(html, 'og:title') == [f'{STANDARD_TITLE_EN} - BookRank']
    assert _meta_content(html, 'twitter:title') == [f'{STANDARD_TITLE_EN} - BookRank']
    assert _article_headline(html) == STANDARD_TITLE_EN
    # 头部元数据与正文 h1 同源
    assert _texts(html, 'h1', 'news-hero-title') == [STANDARD_TITLE_EN]


def test_detail_head_custom_title_verbatim(app, db):
    report = _make_report(db, STANDARD_TITLE, date(2026, 9, 21), date(2026, 9, 27), _content(), 'en')
    report.title = CUSTOM_TITLE
    html = _render_detail(app, report, '/reports/weekly/2026-09-27?lang=en')

    assert _texts(html, 'title') == [f'{CUSTOM_TITLE} - BookRank']
    assert _meta_content(html, 'og:title') == [f'{CUSTOM_TITLE} - BookRank']
    assert _article_headline(html) == CUSTOM_TITLE
