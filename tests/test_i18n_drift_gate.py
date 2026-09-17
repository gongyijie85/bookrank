"""给 CI 门禁自己的解析器兜底（`scripts/check_i18n_drift.py`）。

门禁工具若静默失效，比没有门禁更糟：它会给出"通过"的结论。实测过程中这个解析器连着两版
都把 `#, fuzzy` 漏掉了（先是在 msgid 分支重置标记，后是把重置放进在记录前就会调用的 flush），
只有注入探针条目的反向验证才暴露出来。这些用例把那两个缺陷钉死。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from check_i18n_drift import parse_entries

SNIPPET = """msgid ""
msgstr ""
"Project-Id-Version: PROJECT VERSION\\n"
"POT-Creation-Date: 2026-09-15 00:00+0800\\n"

#. translator-note
#: templates/x.html:1
#, fuzzy
msgid "奖项筛选"
msgstr "Filter"

#: templates/x.html:2
msgid "类别筛选"
msgstr "Category filter"

#~ msgid "已退休的词条"
#~ msgstr "Retired"

msgid "一个很长的词条名字，长到必须换行才写得下，"
"第二段拼回去之后才能与下一条区分开"
msgstr "long one"

msgid "一个很长的词条名字，长到必须换行才写得下，"
"第二段不同所以它们是两条不同的 msgid"
msgstr "long two"
"""


def test_fuzzy_flag_is_detected():
    """`#, fuzzy` 在 msgid **之前**，必须归给紧随其后的那条。"""
    _, fuzzy = parse_entries(SNIPPET)
    assert fuzzy == {'奖项筛选'}, f'实际识别到的 fuzzy: {sorted(fuzzy)}'


def test_non_fuzzy_entries_are_not_flagged():
    entries, _ = parse_entries(SNIPPET)
    assert entries['类别筛选'] == 'Category filter'


def test_multiline_msgids_are_stitched_not_truncated():
    """续行若被丢弃，两条长词条会撞成同一个 key，漂移就查不出来了。"""
    entries, _ = parse_entries(SNIPPET)
    longs = {m: s for m, s in entries.items() if m.startswith('一个很长的词条名字')}
    assert len(longs) == 2, f'多行 msgid 被折叠了，实际条数 {len(longs)}'
    assert longs.get(next(m for m in longs if m.endswith('区分开'))) == 'long one'
    assert longs.get(next(m for m in longs if m.endswith('不同的 msgid'))) == 'long two'
    assert not [m for m in entries if m.endswith('"') or m.endswith('\\')], '续行的引号没剥净'


def test_header_and_obsolete_entries_are_ignored():
    entries, _ = parse_entries(SNIPPET)
    assert '' not in entries, '头部元数据条目不该进结果'
    assert '已退休的词条' not in entries, 'obsolete（#~）条目不该算漂移'
