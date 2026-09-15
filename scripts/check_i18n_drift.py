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


def parse_entries(text: str) -> dict[str, str]:
    """把 .po/.pot 解析成 {msgid: msgstr}，丢弃注释、obsolete 条目与头部元数据。"""
    entries: dict[str, str] = {}
    msgid: str | None = None
    msgstr: str | None = None
    field: str | None = None

    def flush() -> None:
        if msgid is not None and msgid != '' and msgstr is not None:
            entries[msgid] = msgstr

    for line in text.splitlines():
        if line.startswith('msgid '):
            flush()
            msgid, msgstr, field = _unquote(line[6:]), None, None
        elif line.startswith('msgstr '):
            msgstr, field = _unquote(line[7:]), 'str'
        elif line.startswith('"'):
            body = _unquote(line[1:])
            if field == 'id' and msgid is not None:
                msgid += body
            elif field == 'str' and msgstr is not None:
                msgstr += body
        elif line.startswith('#'):
            continue  # 注释与 obsolete：语义无关
        else:
            flush()
            msgid, msgstr, field = None, None, None
    flush()
    return entries


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
            committed = parse_entries((ROOT / rel).read_text(encoding='utf-8'))
            fresh = parse_entries((work / rel).read_text(encoding='utf-8'))
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
