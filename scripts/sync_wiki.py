"""Sync Code Wiki/ -> GitHub wiki (ROADMAP #7).

Single-command, two modes (default dry-run):
  python scripts/sync_wiki.py            # report diff only
  python scripts/sync_wiki.py --push     # commit + push via gh auth git

Push uses the same credentials as `gh` (git config --global credential
helper will be used automatically if set by gh auth login).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_WIKI_DIR = REPO_ROOT / 'Code Wiki'
REMOTE_WIKI = 'https://github.com/gongyijie85/bookrank.wiki.git'


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _wiki_name(src_name: str) -> str:
    """Code Wiki 本地文件 → wiki 文件名映射。

    GitHub wiki 把首页固定为 Home.md；本地索引文件 'Code Wiki 索引.md'
    镜像到 wiki 即 Home.md。其余文件同名直传。
    """
    if src_name == 'Code Wiki 索引.md':
        return 'Home.md'
    return src_name


def main() -> int:
    push = '--push' in sys.argv
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clone = _run(['git', 'clone', REMOTE_WIKI, str(tmp_path / 'wiki')])
        if clone.returncode != 0:
            print('clone failed:', clone.stderr[:300])
            return 1
        wiki_dir = tmp_path / 'wiki'

        changed = 0
        for src in sorted(LOCAL_WIKI_DIR.glob('*.md')):
            dst_name = _wiki_name(src.name)
            dst = wiki_dir / dst_name
            if not dst.exists() or dst.read_text(encoding='utf-8') != src.read_text(encoding='utf-8'):
                changed += 1
                dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
                print(('UPDATED' if dst.exists() else 'ADDED'), dst_name)

        # removed files (existed in wiki, gone from Code Wiki)
        local_wiki_names = {_wiki_name(f.name) for f in LOCAL_WIKI_DIR.glob('*.md')}
        for f in wiki_dir.glob('*.md'):
            if f.name not in local_wiki_names:
                changed += 1
                f.unlink()
                print('REMOVED', f.name)

        if not changed:
            print('Wiki 已是最新（无差异）')
            return 0

        if not push:
            print(f'\n{dry_run_label()}: {changed} 个文件待同步（未推送）。加 --push 实际推送。')
            return 0

        # push via git (uses gh-credential-helper when configured)
        subprocess.run(['git', 'add', '-A'], cwd=wiki_dir, check=True)
        subprocess.run(['git', 'commit', '-m', 'sync: update Code Wiki mirror'], cwd=wiki_dir, check=False)
        push_res = _run(['git', 'push', 'origin', 'master'], cwd=wiki_dir)
        if push_res.returncode != 0:
            print('push failed:', push_res.stderr[:500])
            return 1
        print(f'推送成功：{changed} 个文件已同步')
    return 0


def dry_run_label() -> str:
    return 'DRY-RUN'


if __name__ == '__main__':
    sys.exit(main())
