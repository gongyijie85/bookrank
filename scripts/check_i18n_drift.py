#!/usr/bin/env python3
"""CI 门禁：模板/代码里的 `_()` 与 `.po` 目录是否同步。

CI 原先只做 `pybabel compile`，从不 extract/update —— 于是"加了 `_()` 却没更新目录"
会静默通过，线上表现为英文页直接显示中文 msgid（本仓已多次踩过，如 精选三列/紧凑五列/
网格密度 三个词条在模板里躺了一整轮提交）。

判据必须是**语义级**的：extract/update 的输出会带大量无害抖动（`#:` 引用行号、
`POT-Creation-Date` 等头部时间），按文本 diff 比对会天天误报。这里把两侧都解析成
`{msgid: msgstr}` 再比较，并刻意忽略：

- 注释行（`#`、`#.`, `#:`, `#,`）以及 obsolete 条目（`#~`）——增删引用或词条退休不该红；
- 首条元数据块（`msgid ""`），其内容全是时间戳。

只跑 `msgfmt`/`compile` 的等价物不够，因为这个门禁的意义正在于"目录落后于代码"。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ('en', 'zh')


def parse_entries(text: str) -> tuple[dict[str, str], set[str]]:
    """把 .po/.pot 解析成 ({msgid: msgstr}, 带 fuzzy 标记的 msgid 集合)。

    丢弃注释、obsolete 条目与头部元数据；但 `#, fuzzy` 要单独记下来 —— msgfmt 默认跳过
    fuzzy 条目，运行时回落 msgid，光看 msgstr 是否为空根本发现不了。
    """
    entries: dict[str, str] = {}
    fuzzy: set[str] = set()
    msgid: str | None = None
    msgstr: str | None = None
    field: str | None = None
    entry_fuzzy = False  # 当前条目是否 fuzzy
    pending_fuzzy = False  # 注释块里读到、尚未归属任何 msgid 的 fuzzy 标记

    def flush() -> None:
        nonlocal msgid, msgstr, field, entry_fuzzy
        if msgid:
            entries[msgid] = msgstr or ''
            if entry_fuzzy:
                fuzzy.add(msgid)
        msgid, msgstr, field, entry_fuzzy = None, None, None, False

    for line in text.splitlines():
        if line.startswith('msgid '):
            flush()
            msgid, msgstr, field = _unquote(line[6:]), None, 'id'
            entry_fuzzy, pending_fuzzy = pending_fuzzy, False
        elif line.startswith('msgstr '):
            msgstr, field = _unquote(line[7:]), 'str'
        elif line.startswith('"'):
            body = _unquote(line)  # 整行就是 "…"，截掉首字符会让收尾引号剥不掉
            if field == 'id' and msgid is not None:
                msgid += body  # 多行 msgid 的续行必须拼回，否则长词条会撞成同一个 key
            elif field == 'str' and msgstr is not None:
                msgstr += body
        elif line.startswith('#,') and 'fuzzy' in line:
            pending_fuzzy = True
        elif line.startswith('#'):
            continue
        else:
            flush()
    flush()
    return entries, fuzzy


def _unquote(literal: str) -> str:
    if len(literal) >= 2 and literal[0] == '"' and literal[-1] == '"':
        literal = literal[1:-1]
    return literal.replace(r'\n', '\n').replace(r'\t', '\t').replace(r'\"', '"').replace('\\\\', '\\')


def run(*args: str, cwd: Path | None = None) -> None:
    proc = subprocess.run(list(args), cwd=cwd or ROOT, capture_output=True, text=True, encoding='utf-8')
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f'命令失败: {" ".join(args)}')


def main() -> int:
    src = ROOT / 'translations'
    work = Path(tempfile.mkdtemp(prefix='i18n-drift-'))
    try:
        dst = work / 'translations'
        shutil.copytree(src, dst)
        pot = dst / 'messages.pot'
        run('pybabel', 'extract', '-F', 'babel.cfg', '-o', str(pot), '.')
        run('pybabel', 'update', '-D', 'messages', '-i', str(pot), '-d', str(dst))

        bad = 0
        for locale in LOCALES:
            rel = Path('translations') / locale / 'LC_MESSAGES' / 'messages.po'
            committed, committed_fuzzy = parse_entries((ROOT / rel).read_text(encoding='utf-8'))
            fresh, fresh_fuzzy = parse_entries((work / rel).read_text(encoding='utf-8'))
            missing = sorted(set(fresh) - set(committed))  # 代码里有、目录里缺 —— 唯一阻塞项
            stale = sorted(set(committed) - set(fresh))  # 模板已删但目录仍留（仅提示）
            empties = sorted(m for m, s in fresh.items() if not s.strip())
            cjk_empties = [m for m in empties if any('\u4e00' <= c <= '\u9fff' for c in m)]
            ascii_empties = [m for m in empties if m not in set(cjk_empties)]
            if missing:
                bad += 1
                print(
                    f'::error::{locale}: 目录落后于代码，缺 {len(missing)} 条 msgid'
                    '（加了 _() 但没跑 make translations）'
                )
                for m in missing[:8]:
                    print(f'   缺 msgid: {m[:60]!r}')
            # 空译文**不阻塞**：zh 侧 msgid 本身就是中文，msgstr 为空是正确回落；en 侧的
            # 历史缺口由 tests/test_i18n_catalog.py 跟踪。判红会让门禁天天是红的，然后被忽略。
            # fuzzy 必须单独判：`pybabel update` 会给新条目标 fuzzy 并**借用相近词条的旧译文**
            # （实测 奖项筛选 被填成 "Filter"、类别筛选 被填成 "Category"），而 msgfmt 默认跳过
            # fuzzy 条目 —— 运行时直接回落中文 msgid，英文页照旧是中文，且按 `msgstr ""`
            # 找未译项的写法根本看不见它。
            # 判 committed 里的**所有** fuzzy，而不是只判新增：否则一次带 fuzzy 的提交就永久免检。
            # en 当前为 0 条，所以这条可以直接阻塞；zh 回落中文 msgid 本就是正确结果，只提示。
            if locale == 'en' and committed_fuzzy:
                bad += 1
                print(
                    f'::error::en: {len(committed_fuzzy)} 条 fuzzy 条目 —— msgfmt 会跳过它们，'
                    '运行时回落中文 msgid，且其 msgstr 是借用相近词条的错译'
                )
                for m in sorted(committed_fuzzy)[:8]:
                    print(f'   需去 fuzzy 并核对译文: {m[:60]!r}')
            elif locale == 'zh' and (fresh_fuzzy - committed_fuzzy):
                print(f'::warning::zh: 新增 {len(fresh_fuzzy - committed_fuzzy)} 条 fuzzy（zh 回落中文 msgid 可接受）')
            if locale == 'en' and cjk_empties:
                print(
                    f'::warning::en: {len(cjk_empties)} 条中文 msgid 缺英文译文，英文页会显示中文：'
                    + '、'.join(ascii(m[:16]) for m in cjk_empties[:4])
                )
            if locale == 'zh' and ascii_empties:
                print(
                    f'::warning::zh: {len(ascii_empties)} 条英文 msgid 缺中文译文，中文页会显示英文'
                    f'（例 {ascii_empties[0][:28]!a}）'
                )
            if not missing:
                tail = f'，另有 {len(stale)} 条旧词条已不被引用（可清理）' if stale else ''
                print(f'{locale}: 目录与代码同步（{len(committed)} 条）{tail}')
        if bad:
            print(
                '修复方式：仓库根目录执行 `make translations`（extract → update → compile），'
                '为新增 msgid 补译文后再提交。'
            )
        return 1 if bad else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
