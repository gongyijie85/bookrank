"""模板静态守卫：禁止在 Jinja 模板里给 gettext 的 `_` 绑定名字。

`app/__init__.py` 把 gettext 以别名 `_` 注入 Jinja 全局，模板里任何
`{% set _ = ... %}` / `{% for _ in ... %}` / 名为 `_` 的宏参数都会遮蔽它，
之后同一作用域内的 `_('…')` 会抛 `'NoneType' object is not callable` 直接 500。

这类写法常常只是"丢弃副作用返回值"的占位，改名即可（如 `_unused`）。
"""

import re
from collections.abc import Iterator
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'templates'

TAG = re.compile(r'{%-?\s*(.*?)\s*-?%}', re.S)

# 会向作用域绑定名字的标签 -> 该标签内变量名出现的位置
ASSIGNMENT_OPS = re.compile(r'^set\s+(.+?)\s*(?:=|\+=|-=|\*=|/=|%=)', re.S)
FOR_TARGETS = re.compile(r'^for\s+(.+?)\s+in\s', re.S)
CALL_TARGET = re.compile(r'^call\s+(\w+)')
MACRO_PARAMS = re.compile(r'^macro\s+\w+\s*\((.*)\)$', re.S)
WITH_VARS = re.compile(r'^with\s+(.+)$', re.S)


def _bound_names(tag_body: str) -> Iterator[str]:
    """产出一个 Jinja 标签会绑定进作用域的所有变量名。"""
    body = tag_body.strip()

    match = ASSIGNMENT_OPS.match(body)
    if match:
        for target in match.group(1).split(','):
            yield target.strip().split('=')[0].strip()
        return

    match = FOR_TARGETS.match(body)
    if match:
        for target in match.group(1).split(','):
            yield target.strip()
        return

    match = MACRO_PARAMS.match(body)
    if match:
        for param in match.group(1).split(','):
            name = param.split('=')[0].split(':')[0].strip()
            if name:
                yield name
        return

    match = CALL_TARGET.match(body)
    if match:
        yield match.group(1)
        return

    match = WITH_VARS.match(body)
    if match:
        for part in re.split(r'\s+and\s+|,', match.group(1)):
            name = part.split('=')[0].strip()
            if name:
                yield name


def _offenders() -> list[str]:
    found: list[str] = []
    for path in sorted(TEMPLATE_DIR.rglob('*.html')):
        text = path.read_text(encoding='utf-8')
        for match in TAG.finditer(text):
            if '_' in (name for name in _bound_names(match.group(1))):
                line = text[: match.start()].count('\n') + 1
                found.append(
                    'templates/'
                    + str(path.relative_to(TEMPLATE_DIR))
                    + ':'
                    + str(line)
                    + '  {% '
                    + match.group(1).strip()
                    + ' %}'
                )
    return found


def test_template_dir_found_something():
    assert sorted(TEMPLATE_DIR.rglob('*.html')), f'未在 {TEMPLATE_DIR} 找到模板，规则可能已失效'


def test_no_template_binds_gettext_underscore():
    offenders = _offenders()

    assert not offenders, (
        '模板给 gettext 的 `_` 绑定了名字，会遮蔽翻译函数并在后续 `_(...)` 处抛 '
        "'NoneType' object is not callable。请改用其它变量名（如 `_unused`）。\n" + '\n'.join(offenders)
    )
