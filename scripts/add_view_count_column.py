#!/usr/bin/env python3
"""添加 view_count 列到 weekly_reports 表"""

import sys
from sqlalchemy import inspect, text
from app import create_app
from app.models.database import db


def add_view_count_column():
    """添加 view_count 列到 weekly_reports 表"""
    app = create_app()
    
    with app.app_context():
        try:
            # 检查 weekly_reports 表是否存在
            inspector = inspect(db.engine)
            if 'weekly_reports' in inspector.get_table_names():
                # 检查 view_count 列是否存在
                with db.engine.connect() as conn:
                    result = conn.execute(text("PRAGMA table_info(weekly_reports)"))
                    columns = [row[1] for row in result]
                    
                    if 'view_count' not in columns:
                        # 添加 view_count 列
                        conn.execute(text("ALTER TABLE weekly_reports ADD COLUMN view_count INTEGER DEFAULT 0"))
                        print("✅ 成功添加 view_count 列到 weekly_reports 表")
                    else:
                        print("ℹ️ view_count 列已经存在")
            else:
                print("❌ weekly_reports 表不存在")
        except Exception as e:
            print(f"❌ 执行失败: {e}")
            return False
    return True


if __name__ == "__main__":
    success = add_view_count_column()
    sys.exit(0 if success else 1)