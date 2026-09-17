"""渲染 templates/new_books.html 并把 HTML 写到 stdout。

用途：`tests/test_frontend_newbooks_state.mjs` 需要**真实模板**产出的内联脚本与 DOM
结构，但它本身是 Node 测试。前端测试用 `spawnSync` 调用本脚本、直接消费 stdout，
因此永远跑的是工作区里当前的模板，不存在"快照过期"这一失效模式。

约束：只依赖 Jinja2，不 import Flask / 不 import 应用代码 —— 渲染用的过滤器与全局
都是与 `app/__init__.py` 注册的显示层 helper 同形的最小实现；被测的是前端状态机，
不是这些 helper 本身（helper 的真实行为由 pytest 侧用例覆盖）。

用法：
    python tests/fixtures/render_new_books.py        # HTML 走 stdout

渲染失败会直接抛错（非零退出码），调用方据此失败，不做任何兜底。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent.parent


def build_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(ROOT / 'templates')), undefined=StrictUndefined)
    # 模板用到的过滤器/全局：原样返回，保持"渲染得出来"这一唯一职责。
    env.filters['category_name'] = lambda v, *a: v
    env.filters['language_name'] = lambda v, *a: v
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
    env.globals['get_locale'] = lambda: 'en'
    env.globals['csp_nonce'] = lambda: 'TESTNONCE'
    env.globals['now'] = lambda: date(2026, 1, 1)
    env.globals['split_volume_marker'] = lambda t: (t or '', '')
    env.globals['dist_url'] = lambda name: '/static/' + name
    env.globals['PLACEHOLDER_TEXTS'] = []
    env.globals['url_for'] = lambda *a, **k: '/generated'

    class _FakeRequest:
        url = 'http://local.test/new-books'
        url_root = 'http://local.test/'
        path = '/new-books'
        full_path = '/new-books'
        args: dict[str, str] = {}
        endpoint = 'main.new_books'

    env.globals['request'] = _FakeRequest()
    env.globals['session'] = {}
    env.globals['config'] = {}
    return env


def render() -> str:
    """按 `app/routes/main.py:_load_new_books_data` 的同一批变量渲染（空数据集）。"""
    tpl = build_env().get_template('new_books.html')
    return tpl.render(
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
    )


if __name__ == '__main__':
    import sys

    # 只把 HTML 写 stdout（测试直接消费它）；日志走 stderr，避免污染渲染结果。
    sys.stdout.write(render())
