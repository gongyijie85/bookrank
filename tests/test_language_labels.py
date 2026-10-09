"""语言名中英对照的回归（#236）。

`Config.LANGUAGE_MAP` 只有中文名，`google_books_client.py:202` 在抓取时就把「英语」这类
值写进了库，所以英文页显示中文。修法是显示期按 locale 反查（`app/utils/book_labels.py`），
不改数据、不依赖 gettext（库里来的串模板抽不到，手工塞 `.po` 也会被下次 update 清掉）。
"""

import re
from datetime import UTC
from pathlib import Path

import pytest

from app.config import Config
from app.utils.book_labels import (
    _AWARD_CATEGORY_ZH_TO_EN,
    _COUNTRY_ZH_TO_EN,
    _ZH_TO_EN,
    _category_zh_to_en,
    award_term,
    bilingual,
    category_alias_labels,
    category_name,
    language_name,
)

TEMPLATES = Path(__file__).resolve().parent.parent / 'templates'


def test_en_names_cover_every_mapped_language():
    """值级 parity：LANGUAGE_MAP 的每个中文名都得有英文名，反之亦然。

    只比键集合的 parity 测试曾在 #235 放过真实分歧（`and` vs `&`），这里直接比集合内容。
    新增语种若漏配英文，英文页会退回显示中文 —— 这条先红。
    """
    assert set(_ZH_TO_EN) == set(Config.LANGUAGE_MAP.values()), (
        f'缺英文名的语言: {set(Config.LANGUAGE_MAP.values()) - set(_ZH_TO_EN)}；'
        f'多余的英文名: {set(_ZH_TO_EN) - set(Config.LANGUAGE_MAP.values())}'
    )


def test_language_name_follows_locale(app):
    assert language_name('英语', 'en') == 'English'
    assert language_name('西班牙语', 'en') == 'Spanish'
    assert language_name('英语', 'zh_CN') == '英语'
    with app.test_request_context('/?lang=zh'):
        assert language_name('英语', None) == '英语'
    with app.test_request_context('/?lang=en'):
        assert language_name('英语', None) == 'English'


def test_language_name_is_passthrough_for_unknown_and_empty():
    """Google 偶尔直接回原始码（`en`/`zu`）；未收录的原样返回，绝不编造译名。"""
    assert language_name('zu', 'en') == 'zu'
    assert language_name('', 'en') == ''
    assert language_name(None, 'en') == ''


def test_filter_is_registered_on_the_jinja_env(app):
    assert app.jinja_env.filters['language_name'] is language_name


def test_templates_render_language_through_the_filter():
    """四处调用点必须都走过滤器：桌面 detail 那处原先是模板内联猜"英/中"两种。"""
    for rel in ('book_detail.html', 'mobile/index.html', 'mobile/book_detail.html'):
        src = (TEMPLATES / rel).read_text(encoding='utf-8')
        assert 'language_name' in src, f'{rel} 未经 language_name 过滤器'
    desktop = (TEMPLATES / 'book_detail.html').read_text(encoding='utf-8')
    assert "'英' in book.language" not in desktop, '旧的猜名逻辑仍在'


# --- 奖项名 / 国家 / 类别（#227）---


def test_award_term_covers_every_seeded_country_and_category():
    """两张枚举映射的键集必须盖住种子数据，否则英文页对应标签会凭空消失。"""
    from app.initialization.awards import AWARDS_FALLBACK_DATA
    from app.initialization.sample_award_books import SAMPLE_AWARD_BOOKS

    countries = {a['country'] for a in AWARDS_FALLBACK_DATA.values() if a.get('country')}
    categories = {b['category'] for b in SAMPLE_AWARD_BOOKS if b.get('category')}
    assert countries - set(_COUNTRY_ZH_TO_EN) == set(), f'缺英文名国家: {countries - set(_COUNTRY_ZH_TO_EN)}'
    assert categories - set(_AWARD_CATEGORY_ZH_TO_EN) == set(), (
        f'缺英文名奖项类别: {categories - set(_AWARD_CATEGORY_ZH_TO_EN)}'
    )


def test_bilingual_picks_english_field_and_falls_back_to_source_name():
    """双语字段择一，另一侧兜底：任一边为空都不能让标题变空白。"""
    assert bilingual('普利策奖', 'Pulitzer Prize', 'en') == 'Pulitzer Prize'
    assert bilingual('普利策奖', 'Pulitzer Prize', 'zh_CN') == '普利策奖'
    assert bilingual('普利策奖', '', 'en') == '普利策奖'
    assert bilingual('普利策奖', None, 'en') == '普利策奖'
    assert bilingual('', 'The Stand', 'zh_CN') == 'The Stand'
    assert bilingual(None, 'The Stand', 'zh_CN') == 'The Stand'


def test_award_term_hides_unmapped_term_on_english_page():
    """国家/类别是装饰性标签：英文页宁可没有，也不挂一段中文。"""
    assert award_term('美国', 'en') == 'United States'
    assert award_term('非虚构 (入围)', 'en') == 'Nonfiction (Shortlist)'
    assert award_term('某个新奖项类别', 'en') == ''
    assert award_term('某个新奖项类别', 'zh') == '某个新奖项类别'
    assert award_term('', 'en') == ''
    assert award_term(None, 'en') == ''


def test_award_filters_follow_request_locale(app):
    with app.test_request_context('/awards?lang=zh'):
        assert bilingual('布克奖', 'Booker Prize') == '布克奖'
        assert award_term('瑞典') == '瑞典'
    with app.test_request_context('/awards?lang=en'):
        assert bilingual('布克奖', 'Booker Prize') == 'Booker Prize'
        assert award_term('瑞典') == 'Sweden'


def test_award_filters_are_registered_on_the_jinja_env(app):
    assert app.jinja_env.filters['bilingual'] is bilingual
    assert app.jinja_env.filters['award_term'] is award_term


# --- 新书分类（#227 续）---


def test_category_name_covers_the_whole_written_enum():
    """新书分类的英文显示名从爬虫自己的 CATEGORY_EN_TO_ZH 反查，不再手抄第二张表。

    库里可能出现的中文分类值就是这张表的值集（`sanitize_category` 只会产出它），所以
    覆盖它 = 覆盖线上；`VALID_CATEGORIES` 是同一份事实的另一视图，一并断言。
    """
    from app.services.publisher_data import CATEGORY_EN_TO_ZH, VALID_CATEGORIES

    rev = _category_zh_to_en()
    assert set(CATEGORY_EN_TO_ZH.values()) <= set(rev)
    # VALID_CATEGORIES 混装了英文源词与中文结果两半，只有中文那半需要反查得到
    zh_members = {v for v in VALID_CATEGORIES if re.search('[一-鿿]', v)}
    assert zh_members <= set(rev), f'反查不到英文名: {zh_members - set(rev)}'
    assert rev['小说'] == 'Fiction'
    assert rev['儿童读物'] == 'Children'
    assert rev['综合'] == 'General', 'General/general 碰撞要取非全小写的那个'


def test_category_name_follows_locale_and_passes_unknown_through():
    """未知分类原样返回：chip 是可点筛选项，隐掉等于删选项（与 award_term 相反）。"""
    assert category_name('小说', 'en') == 'Fiction'
    assert category_name('健康养生', 'en') == 'Health & Fitness'
    assert category_name('小说', 'zh') == '小说'
    assert category_name('某个没登记的新分类', 'en') == '某个没登记的新分类'
    assert category_name('', 'en') == ''
    assert category_name(None, 'en') == ''


def test_category_name_follows_request_locale(app):
    with app.test_request_context('/new-books?lang=zh'):
        assert category_name('悬疑') == '悬疑'
    with app.test_request_context('/new-books?lang=en'):
        assert category_name('悬疑') == 'Mystery'


def test_category_name_filter_registered(app):
    assert app.jinja_env.filters['category_name'] is category_name


@pytest.mark.parametrize('category', Config.CATEGORIES)
@pytest.mark.parametrize('locale', ('en', 'zh'))
def test_category_name_covers_actual_nyt_labels(category, locale):
    """NYT 标签由实际配置派生；「商业」保留既有新书显示名优先级。"""
    zh = Config.CATEGORIES[category]
    en = Config.CATEGORY_NAMES_EN[category]
    if locale == 'en':
        expected = 'Business' if category == 'business-books' else en
        assert category_name(zh, locale) == expected
        assert category_name(en, locale) == en
    else:
        assert category_name(zh, locale) == zh
        assert category_name(en, locale) == zh


@pytest.mark.parametrize('locale', ('en', 'zh'))
def test_category_name_nyt_mapping_uses_current_config(monkeypatch, locale):
    """配置新增标签无需维护另一张显示映射表。"""
    monkeypatch.setitem(Config.CATEGORIES, 'future-test-category', '测试新增榜单')
    monkeypatch.setitem(Config.CATEGORY_NAMES_EN, 'future-test-category', 'Future Test List')
    source = '测试新增榜单' if locale == 'en' else 'Future Test List'
    expected = 'Future Test List' if locale == 'en' else '测试新增榜单'
    assert category_name(source, locale) == expected


def test_category_name_nyt_follows_request_locale_and_jinja_escaping(app):
    """周报调用使用请求 locale；未知标签保持原值，HTML 由 Jinja 自动转义。"""
    source = '<img src=x onerror=alert(1)>'
    with app.test_request_context('/weekly-reports/1?lang=en'):
        assert category_name('精装小说') == Config.CATEGORY_NAMES_EN['hardcover-fiction']
        template = app.jinja_env.from_string('{{ value | category_name }}')
        assert template.render(value=source) == '&lt;img src=x onerror=alert(1)&gt;'
    with app.test_request_context('/weekly-reports/1?lang=zh'):
        assert category_name('Hardcover Fiction') == Config.CATEGORIES['hardcover-fiction']


def test_category_name_nyt_preserves_all_publisher_aliases():
    """新增 NYT 展示映射不改变新书分类、规范名或前端别名字典。"""
    from app.services.publisher_data import CATEGORY_EN_TO_ZH

    original = dict(CATEGORY_EN_TO_ZH)
    assert category_alias_labels() == original
    for en, zh in original.items():
        assert category_name(en, 'zh') == zh
        assert category_name(en, 'en') == en
        assert category_name(zh, 'en') == _category_zh_to_en()[zh]
        assert category_name(zh, 'zh') == zh
    assert category_name('商业', 'en') == 'Business'
    assert category_alias_labels() == original
    assert original == CATEGORY_EN_TO_ZH


@pytest.mark.parametrize('locale', ('en', 'zh'))
@pytest.mark.parametrize('value', ('未登记榜单', '<script>alert(1)</script>', '', None))
def test_category_name_nyt_preserves_unknown_and_empty(value, locale):
    assert category_name(value, locale) == (value or '')


def test_award_templates_route_names_through_the_filters():
    """两端各 4 个文件都要走过滤器 —— 移动端是桌面端的平行副本，漏一端就是半套修复。

    只钉"整行裸输出"这种标签写法：`value="{{ award.name }}"` 是中文筛选键，必须留在属性里，
    按整页字符串判存在会把它误判成泄漏（第一版就这么写错了）。
    """
    rels = ('awards.html', 'mobile/awards.html', 'award_book_detail.html', 'mobile/award_book_detail.html')
    bare_field_line = re.compile(
        r'^\s*\{\{\s*(?:award\.name|category|book\.category|book\.award_name)\s*\}\}\s*$', re.M
    )
    for rel in rels:
        src = (TEMPLATES / rel).read_text(encoding='utf-8')
        assert 'bilingual(' in src or 'award_term' in src, f'{rel} 未经双语/枚举过滤器'
        leaked = bare_field_line.findall(src)
        assert not leaked, f'{rel} 仍有整行裸输出的中文字段: {leaked}'
    awards = (TEMPLATES / 'awards.html').read_text(encoding='utf-8')
    assert '{{ award.country' not in awards, '国家未经 award_term 直接输出'


def test_price_display_hides_blanks_and_marks_bare_amounts(app):
    from decimal import Decimal

    from app.utils.book_labels import price_display

    assert price_display(None, 'zh') == ''
    assert price_display('', 'en') == ''
    assert price_display('  \t', 'en') == ''
    assert price_display(0, 'zh') == '0（币种未确认）'
    assert price_display(0, 'en') == '0 (currency unconfirmed)'
    assert price_display(2.5, 'zh') == '2.5（币种未确认）'
    assert price_display(Decimal('0'), 'en') == '0 (currency unconfirmed)'
    assert price_display('24.50', 'en') == '24.50 (currency unconfirmed)'
    for raw in ('$24.99', 'USD 24.99', 'EUR 18,50', 'JPY 1200', '￥88.00'):
        assert price_display(raw, 'en') == raw
        assert price_display(raw, 'zh') == raw
    with app.test_request_context('/?lang=zh'):
        assert price_display(0) == '0（币种未确认）'
    with app.test_request_context('/?lang=en'):
        assert price_display(0) == '0 (currency unconfirmed)'
    rendered = app.jinja_env.from_string('{{ value|price_display("en") }}').render(value=0)
    assert rendered == '0 (currency unconfirmed)'
    assert app.jinja_env.filters['price_display'] is price_display


def test_award_result_kind_is_explicit_status_enum(app):
    from app.utils.book_labels import award_result_kind

    assert award_result_kind('小说 (获奖)') == 'winner'
    assert award_result_kind('Fiction (Winner)') == 'winner'
    assert award_result_kind('小说 (入围)') == 'shortlisted'
    assert award_result_kind('Fiction (Shortlist)') == 'shortlisted'
    assert award_result_kind('Longlist') == 'shortlisted'
    assert award_result_kind('Fiction') == 'unspecified'
    assert award_result_kind(None) == 'unspecified'
    assert award_result_kind('unknown shelf') == 'unspecified'
    assert award_result_kind('Winnerish') == 'unspecified'
    assert award_result_kind('诺贝尔文学奖') == 'unspecified'
    assert award_result_kind('Fiction (Winner)', 'Q37922') == 'author_honor'
    assert award_result_kind('小说 (获奖)', 'Q37922') == 'author_honor'
    assert app.jinja_env.filters['award_result_kind'] is award_result_kind


def test_publication_state_follows_utc_date_not_local_today(monkeypatch):
    from datetime import date as real_date
    from datetime import datetime as real_datetime

    from app.utils import book_labels as labels

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 9, 29, 23, 59, tzinfo=UTC)

    class FrozenDate(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 9, 30)

    monkeypatch.setattr(labels, 'datetime', FrozenDateTime)
    monkeypatch.setattr(labels, 'date', FrozenDate)
    assert labels.publication_state(FrozenDate(2026, 9, 30)) == 'upcoming'
    assert labels.publication_state(FrozenDate(2026, 9, 29)) == 'published'
    assert labels.publication_state(None) == 'pending'
    assert labels.publication_state(FrozenDate(2026, 9, 30), today=real_date(2026, 9, 30)) == 'published'


def test_award_result_kind_rejects_negated_and_conflicting_winners():
    from app.utils.book_labels import award_result_kind as kind

    assert kind('未获奖') == 'unspecified'
    assert kind('not winner') == 'unspecified'
    assert kind('Fiction (Shortlisted, not winner)') == 'shortlisted'
    assert kind('Fiction (Winner, Shortlist)') == 'unspecified'
    assert kind('未获奖 (入围)') == 'shortlisted'
    assert kind('Winner') == 'winner'
    assert kind('Shortlist') == 'shortlisted'
    assert kind('未获奖', 'Q37922') == 'author_honor'
    assert kind('Fiction (Winner, Shortlist)', 'Q37922') == 'author_honor'


def test_award_result_kind_rejects_negated_shortlist_phrases():
    from app.utils.book_labels import award_result_kind as kind

    assert kind('未入围') == 'unspecified'
    assert kind('not shortlisted') == 'unspecified'
    assert kind('未入围', 'Q37922') == 'author_honor'
    assert kind('not shortlisted', 'Q37922') == 'author_honor'
