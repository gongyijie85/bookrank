"""Render current frontend templates with isolated display data for Node UX QA."""

import ast
import importlib
import importlib.util
import json
import sys
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType

from flask import Flask
from jinja2 import FileSystemLoader

sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
task = json.load(sys.stdin)
root = Path(task['root'])
spec = importlib.util.spec_from_file_location('actual_labels', root / 'app/utils/book_labels.py')
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)
actual_utils = ModuleType('ux_qa_utils')
actual_utils.__path__ = [str(root / 'app/utils')]
sys.modules[actual_utils.__name__] = actual_utils
reports = importlib.import_module('ux_qa_utils.weekly_report_presentation')
# Load only the actual constant data and pure predicate, without importing API services.
helper_path = root / 'app/utils/api_helpers.py'
helper_tree = ast.parse(helper_path.read_text(encoding='utf8'), filename=str(helper_path))
helper_globals = {}
for name in ('PLACEHOLDER_TEXTS', '_NON_SUBSTANTIVE_DETAILS'):
    assignment = next(
        node
        for node in helper_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    assert isinstance(assignment.value, ast.Call)
    assert isinstance(assignment.value.func, ast.Name) and assignment.value.func.id == 'frozenset'
    helper_globals[name] = frozenset(ast.literal_eval(assignment.value.args[0]))
predicate = next(
    node for node in helper_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'is_non_substantive_details'
)
exec(compile(ast.Module(body=[predicate], type_ignores=[]), str(helper_path), 'exec'), helper_globals)
app = Flask(__name__, static_folder=str(root / 'static'))
for endpoint, rule in [
    ('index', '/'),
    ('rankings', '/rankings'),
    ('awards', '/awards'),
    ('publishers', '/publishers'),
    ('new_books', '/new-books'),
    ('weekly_reports', '/reports/weekly'),
    ('weekly_report_detail', '/reports/weekly/<date>'),
    ('export_weekly_report', '/reports/weekly/<date>/export'),
    ('profile', '/profile'),
    ('about', '/about'),
    ('book_detail', '/book/<int:book_index>'),
    ('award_book_detail', '/award-book/<int:book_id>'),
    ('new_book_detail', '/new-book/<int:book_id>'),
    ('award_book_cover', '/award-book/<int:book_id>/cover'),
    ('cover_proxy', '/cover'),
]:
    app.add_url_rule(rule, endpoint='main.' + endpoint, view_func=lambda: '')
app.jinja_loader = FileSystemLoader(str(root / 'templates'))
env = app.jinja_env
locale = task.get('locale', 'zh')
env.globals.update(
    _=lambda value, **params: value % params if params else value,
    gettext=lambda value, **params: value % params if params else value,
    get_locale=lambda: locale,
    csp_nonce=lambda: 'QA-NONCE',
    dist_url=lambda value: value,
    now=lambda: datetime(2026, 9, 30),
    PLACEHOLDER_TEXTS=helper_globals['PLACEHOLDER_TEXTS'],
    split_volume_marker=lambda value: (value or '', ''),
    is_non_substantive_details=helper_globals['is_non_substantive_details'],
)
for name in ('price_display', 'award_result_kind', 'positive_int_text'):
    env.filters[name] = getattr(labels, name)
env.filters['bilingual'] = lambda zh, en='', *args: (en or zh) if locale == 'en' else (zh or en)
for name in (
    'category_name',
    'language_name',
    'award_term',
    'cover_src',
    'cover_src_or_default',
    'sanitize_html',
    'format_title',
    'markdown',
):
    env.filters[name] = lambda value, *args: value or ''
env.filters['publication_state'] = lambda value: 'pending'
env.filters['publication_state_label'] = lambda value, *args: 'Pending'
env.filters['positive_int'] = lambda value: int(value) if str(value).isdigit() and int(value) > 0 else None
env.filters['is_invalid_publisher'] = lambda value: not value or value in ('Unknown', 'Unknown Publisher')
env.filters['is_valid_isbn'] = lambda value: (
    bool(value) and len(str(value).replace('-', '').replace(' ', '')) in (10, 13)
)
env.filters['clean_isbn'] = lambda value: str(value).replace('-', '').replace(' ', '')
env.filters['report_title'] = reports.localize_report_title


class DOM(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        index = len(self.nodes)
        self.nodes.append({'tag': tag, 'attrs': dict(attrs), 'text': '', 'ownText': '', 'ancestors': self.stack.copy()})
        if tag not in {
            'area',
            'base',
            'br',
            'col',
            'embed',
            'hr',
            'img',
            'input',
            'link',
            'meta',
            'param',
            'source',
            'track',
            'wbr',
        }:
            self.stack.append(index)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.nodes[self.stack[index]]['tag'] == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, value):
        for index in self.stack:
            self.nodes[index]['text'] += value
        if self.stack:
            self.nodes[self.stack[-1]]['ownText'] += value


with app.test_request_context(task.get('url', '/?lang=zh')):
    context = task.get('context', {})

    def display_dates(value):
        if isinstance(value, list):
            return [display_dates(item) for item in value]
        if isinstance(value, dict):
            return {
                key: date.fromisoformat(item)
                if key in ('week_start', 'week_end', 'report_date') and isinstance(item, str)
                else datetime.fromisoformat(item)
                if key in ('created_at', 'updated_at') and isinstance(item, str)
                else display_dates(item)
                for key, item in value.items()
            }
        return value

    context = display_dates(context)
    for name in ('publisher_kind', 'publisher_book_counts'):
        if isinstance(context.get(name), dict):
            context[name] = {int(key): value for key, value in context[name].items()}
    if 'new_book_detail' in task['name']:

        class Book(dict):
            __getattr__ = dict.__getitem__

            def get_buy_links(self):
                return self.get('buy_links', [])

        context['book'] = Book(context['book'])
    html = env.get_template(task['name']).render(**context)
    dom = DOM()
    dom.feed(html)
    print(json.dumps({'html': html, 'nodes': dom.nodes}, ensure_ascii=False))
