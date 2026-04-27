#!/usr/bin/env python3
"""
重置数据库脚本 - 删除旧数据库并重新创建表结构
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def reset_database():
    """删除旧数据库文件"""
    db_files = [
        project_root / 'bestsellers.db',
        project_root / 'instance' / 'bookrank.db',
    ]
    
    deleted = []
    for db_file in db_files:
        if db_file.exists():
            try:
                os.remove(db_file)
                deleted.append(str(db_file))
                print(f"✅ 已删除: {db_file}")
            except Exception as e:
                print(f"⚠️ 无法删除 {db_file}: {e}")
    
    if not deleted:
        print("ℹ️ 没有找到旧数据库文件")
    else:
        print(f"\n共删除 {len(deleted)} 个数据库文件")
    
    return True

if __name__ == '__main__':
    reset_database()
