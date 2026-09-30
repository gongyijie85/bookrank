"""渲染 templates/new_books.html 并把 HTML 写到 stdout。

用途：`tests/test_frontend_newbooks_state.mjs` 需要**真实模板**产出的内联脚本与 DOM
结构，但它本身是 Node 测试。前端测试用 `spawnSync` 调用本脚本、直接消费 stdout，
因此永远跑的是工作区里当前的模板，不存在"快照过期"这一失效模式。

约束：只依赖 Jinja2，不 import Flask / 不 import 应用代码 —— 渲染用的过滤器与全局
都是与 `app/__init__.py` 注册的显示层 helper 同形的最小实现；被测的是前端状态机，
不是这些 helper 本身（helper 的真实行为由 pytest 侧用例覆盖）。

用法：
    python tests/fixtures/render_new_books.py                     # HTML 走 stdout（空数据集）
    python tests/fixtures/render_new_books.py --with-books [--locale=zh|en]
        # 只渲染 templates/_macros.html 的**真实** new_book_card 宏产出一张 SSR 卡片
        # （前端回归封面 alt 双语留痕用；不复制镜像宏）

**进程输出契约：stdout 恒为 UTF-8，与父环境的 locale / PYTHONIOENCODING 无关。**
Windows 控制台默认代码页是 GBK（cp936），模板内联脚本注释里含 U+2194（↔，
templates/new_books.html）这类 GBK 编不出的字符，`sys.stdout.write` 会直接抛
`UnicodeEncodeError`（exit 非 0、stdout 为空）。调用方（node 测试）固定按 UTF-8
解码 stdout，因此这里在写出的同时显式把 stdout 重配为 UTF-8，而不是指望调用方
或运行环境干净——回归覆盖见 tests/test_frontend_newbooks_state.mjs 的
「渲染器在非 UTF-8 父环境下仍输出 UTF-8」用例。

渲染失败会直接抛错（非零退出码），调用方据此失败，不做任何兜底。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent.parent


def build_env(locale: str = 'en') -> Environment:
    env = Environment(loader=FileSystemLoader(str(ROOT / 'templates')), undefined=StrictUndefined)
    # 模板用到的过滤器/全局：原样返回，保持"渲染得出来"这一唯一职责。
    env.filters['category_name'] = lambda v, *a: v
    env.filters['language_name'] = lambda v, *a: v
    env.filters['price_display'] = lambda v, *a: v
    env.filters['bilingual'] = lambda a, b, *rest: a
    env.filters['award_term'] = lambda v, *a: v
    env.filters['cover_src'] = lambda v: v
    env.filters['cover_src_or_default'] = lambda v: v
    env.filters['publication_state'] = lambda v: 'upcoming'
    env.filters['publication_state_label'] = lambda v, *a: 'Upcoming'
    env.filters['sanitize_html'] = lambda v: v
    env.filters['tojson'] = lambda v: __import__('json').dumps(v)
    env.globals['_'] = lambda s, *a, **k: s
    env.globals['gettext'] = env.globals['_']
    env.globals['ngettext'] = lambda s, p, n: s if n == 1 else p
    env.globals['get_locale'] = lambda: locale
    env.globals['csp_nonce'] = lambda: 'TESTNONCE'
    env.globals['now'] = lambda: date(2026, 1, 1)
    env.globals['split_volume_marker'] = lambda t: (t or '', '')
    env.globals['dist_url'] = lambda name: '/static/' + name
    env.globals['PLACEHOLDER_TEXTS'] = []
    env.globals['url_for'] = lambda *a, **k: '/generated'

    class _FakeRequest:
        url = 'http://local.test/new-books'
        url_root = 'http://local.test/'
        host_url = 'http://local.test/'
        path = '/new-books'
        full_path = '/new-books'
        args: dict[str, str] = {}
        endpoint = 'main.new_books'

    env.globals['request'] = _FakeRequest()
    env.globals['session'] = {}
    env.globals['config'] = {}
    return env


def render(locale: str = 'en', template_name: str = 'new_books.html', **overrides) -> str:
    """按 `app/routes/main.py:_load_new_books_data` 的同一批变量渲染（空数据集）。"""
    tpl = build_env(locale).get_template(template_name)
    context = dict(
        page=1,
        total=0,
        total_pages=1,
        per_page=20,
        books=[],
        publishers=[],
        # 分类下拉框的真实选项：前端测试要断言"选中项文案随语言重绘"，必须让
        # 用户真的选得中一个分类（空列表时只剩 value="" 的「全部分类」占位符，
        # 任何断言都会落到占位符上）。这两个键与生产 CATEGORY_EN_TO_ZH 的
        # Business→商业 / Fiction→小说 对应项一致，分类标签由下拉框 value 驱动
        # （value 就是规范中文键），不需要再写死一份显示文案。
        categories=[{'name': '商业', 'count': 1}, {'name': '小说', 'count': 1}],
        stats={'total_books': 0, 'active_publishers': 0},
        selected_publication_status='all',
        data_load_failed=False,
        stats_unavailable=False,
        publisher_counts_unavailable=False,
        publisher_book_counts={},
        publisher_kind={},
        publishers_unavailable=False,
        publisher_sections_unavailable=False,
        selected_publisher=None,
        selected_category=None,
        selected_days=30,
        search_query='',
        view_mode='grid',
        future_preview_days=14,
        recommended_books=[],
        publisher_sections=[],
        category_alias_labels={'Business': '商业', 'Fiction': '小说'},
        publisher_labels={},
        active_tab='new_books',
    )
    context.update(overrides)
    context['publisher_kind'] = {int(key): value for key, value in context['publisher_kind'].items()}
    return tpl.render(**context)


def _sample_book():
    """new_book_card 宏会读到的最小字段集（与生产模型的同名属性同形）。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=7,
        title='Dune',
        title_zh='沙丘',
        author='Author',
        isbn13='9780000000007',
        isbn10=None,
        cover_url='/cache/images/dune.jpg',
        publisher=SimpleNamespace(name='出版社', name_en='Publisher'),
        price=None,
        is_recently_published=False,
        category='Business',
        publication_date=date(2026, 1, 1),
    )


def render_card(locale: str = 'zh') -> str:
    """渲染一张真实 new_book_card 宏产出的 SSR 卡片。

    只 import 真实宏再调用（`{% from "_macros.html" import ... %}`），不在夹具里
    复制一份镜像模板 —— 测的一定是工作区当前的宏。
    """
    env = build_env(locale)
    tpl = env.from_string('{% from "_macros.html" import new_book_card %}{{ new_book_card(book) }}')
    return tpl.render(book=_sample_book())


if __name__ == '__main__':
    import sys

    args = sys.argv[1:]
    locale = next((a.split('=', 1)[1] for a in args if a.startswith('--locale=')), 'en')

    # 见模块 docstring 的 UTF-8 输出契约：显式重配 stdout，抵消 GBK 控制台 /
    # PYTHONIOENCODING=gbk 之类的父环境。
    sys.stdout.reconfigure(encoding='utf-8')
    # 只把 HTML 写 stdout（测试直接消费它）；日志走 stderr，避免污染渲染结果。
    if '--with-books' in args:
        sys.stdout.write(render_card(locale))
    else:
        context_arg = next((a.split('=', 1)[1] for a in args if a.startswith('--context=')), '{}')
        template_name = 'mobile/new_books.html' if '--mobile' in args else 'new_books.html'
        sys.stdout.write(render(locale, template_name, **__import__('json').loads(context_arg)))
