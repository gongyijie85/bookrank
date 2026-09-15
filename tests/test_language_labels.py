"""语言名中英对照的回归（#236）。

`Config.LANGUAGE_MAP` 只有中文名，`google_books_client.py:202` 在抓取时就把「英语」这类
值写进了库，所以英文页显示中文。修法是显示期按 locale 反查（`app/utils/book_labels.py`），
不改数据、不依赖 gettext（库里来的串模板抽不到，手工塞 `.po` 也会被下次 update 清掉）。
"""

from pathlib import Path

from app.config import Config
from app.utils.book_labels import _ZH_TO_EN, language_name

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
