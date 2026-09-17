"""书名尾部卷号标记的拆解（展示用）。

卡片标题在 `static/css/browse.css` 里限 3 行截断（`.browse-card-title` 的
`-webkit-line-clamp`），长书名的**尾部**会被裁掉 —— 而卷号恰恰总在尾部
（实测 100 本样本中 55 本英文书名以 `#NNN` 结尾）。同系列各卷因此显示为
完全相同的标题，观感上像站点在重复渲染同一本书。

`title_zh` 还经常**不含**卷号：同一系列的 7 卷中文名只落到 4 个不同字符串，
差异仅来自翻译漂移。所以卷号要从英文字段提取后**单独渲染**，不能指望
中文标题自带。

本模块只做纯文本拆解；渲染由 `templates/_macros.html` 的
`browse_book_card` 负责。

设计约束：**只认尾部标记**。中文标题里 `第N卷` 可能出现在中间并后接副标题
（如「足球小将 第二卷：黄金搭档」），英文亦有此形（`Tsubasa Volume 2 The
Golden Duo`）。从中间剥离会破坏书名，故这两类一律不拆。
"""

from __future__ import annotations

import re

# `#NNN` —— 实测主形态（100 本样本中 55 本英文、34 本中文命中）
_HASH_MARKER = re.compile(r'^(?P<stem>.+?)\s*#\s*(?P<number>\d+)\s*$')

# `Volume N` / `Vol. N` —— 实测 2 本
_WORD_MARKER = re.compile(
    r'^(?P<stem>.+?)\s+(?P<word>vol\.?|volume)\s*(?P<number>\d+)\s*$',
    re.IGNORECASE,
)

# `第N卷` / `第N册` / `第N部`（数字或中文数词）—— 实测 3 本
_CJK_MARKER = re.compile(
    r'^(?P<stem>.+?)\s*第\s*(?P<number>\d+|[一二三四五六七八九十百零〇两]+)\s*(?P<unit>[卷册部])\s*$'
)


def split_volume_marker(title: object) -> tuple[str, str]:
    """把书名尾部的卷号标记拆出来。

    返回 ``(stem, marker)``：``marker`` 为 ``''`` 表示未识别到卷号，
    此时 ``stem`` 即原书名。``stem`` 已去除尾部空白。

    只识别**尾部**标记 —— 见模块 docstring 的说明。
    整串仅为一个标记（如 ``'#07'``）时视为书名本身，不做拆分，避免把标题清空。
    """
    text = str(title).strip() if title else ''
    if not text:
        return '', ''

    match = _HASH_MARKER.match(text)
    if match:
        return match.group('stem').strip(), f'#{match.group("number")}'

    match = _WORD_MARKER.match(text)
    if match:
        word = match.group('word')
        number = match.group('number')
        return match.group('stem').strip(), f'{word} {number}'

    match = _CJK_MARKER.match(text)
    if match:
        unit = match.group('unit')
        number = match.group('number')
        return match.group('stem').strip(), f'第{number}{unit}'

    return text, ''
