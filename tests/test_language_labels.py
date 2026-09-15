"""语言名中英对照的回归（#236）。

`Config.LANGUAGE_MAP` 只有中文名，`google_books_client.py:202` 在抓取时就把「英语」这类
值写进了库，所以英文页显示中文。修法是显示期按 locale 反查（`app/utils/book_labels.py`），
不改数据、不依赖 gettext（库里来的串模板抽不到，手工塞 `.po` 也会被下次 update 清掉）。
"""

import re
from pathlib import Path

from app.config import Config
from app.utils.book_labels import (
    _AWARD_CATEGORY_ZH_TO_EN,
    _COUNTRY_ZH_TO_EN,
    _ZH_TO_EN,
    award_term,
    bilingual,
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
