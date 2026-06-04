#!/usr/bin/env python3
"""
永久修复获奖书单脏数据（title 字段为 ISBN）

复用 init_sample_award_books() 的修复逻辑：
- 按 (award_id, year, isbn13) 匹配现有 AwardBook
- 检测 title 是否像 ISBN（10/13 位纯数字）
- 命中 SAMPLE_AWARD_BOOKS 种子数据时，用真实书名覆盖
- 同时修复 title_zh 字段
- 标记 title 是 ISBN 且不在种子表里的记录为 deprecated + is_displayable=False

使用方法:
    # 本地 SQLite（默认 DATABASE_URL=sqlite:///bestsellers.db）
    python scripts/fix_award_book_titles.py

    # 生产 PostgreSQL（需要先把 Render 的 DATABASE_URL 临时导入到本地）
    # 1. 登录 Render → 数据库 → External Database URL → 复制
    # 2. PowerShell:
    #      $env:DATABASE_URL = "postgresql://user:pass@host/dbname"
    #      python scripts/fix_award_book_titles.py
    #      Remove-Item Env:DATABASE_URL
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.initialization.sample_award_books import _looks_like_isbn, init_sample_award_books
from app.models.schemas import AwardBook


def _count_isbn_titles() -> int:
    """统计 title 字段是 ISBN 的记录数（Python 过滤，跨数据库兼容）"""
    return sum(1 for b in AwardBook.query.all() if _looks_like_isbn(b.title))


def main() -> int:
    """执行修复流程并返回退出码"""
    app = create_app()

    with app.app_context():
        before_dirty = _count_isbn_titles()

        print('=' * 60)
        print('🔧 开始修复获奖书单 ISBN 脏数据')
        print('=' * 60)
        print(f'\n修复前疑似脏数据（title 字段是 ISBN）: {before_dirty} 条\n')

        init_sample_award_books(app)

        after_dirty = _count_isbn_titles()
        fixed_count = max(0, before_dirty - after_dirty)

        print('\n' + '=' * 60)
        print('📊 修复结果')
        print('=' * 60)
        print(f'  修复前脏数据: {before_dirty} 条')
        print(f'  修复后脏数据: {after_dirty} 条')
        print(f'  本次修复数:   {fixed_count} 条')
        print('=' * 60)

        return 0


if __name__ == '__main__':
    sys.exit(main())
