#!/usr/bin/env python
"""
数据库迁移初始化脚本
用于在本地生成 Flask-Migrate 迁移文件
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db

def init_migrations():
    """初始化数据库迁移"""
    app = create_app('development')
    
    with app.app_context():
        # 导入 Flask-Migrate
        try:
            from flask_migrate import Migrate, init, migrate, upgrade
            
            # 初始化迁移
            if not (project_root / 'migrations').exists():
                print("📦 初始化迁移目录...")
                init(directory='migrations')
            
            # 创建迁移脚本
            print("🔧 生成迁移脚本...")
            migrate(directory='migrations', message='Initial migration - all tables')
            
            print("✅ 迁移脚本已生成！")
            print("\n下一步操作：")
            print("1. 检查 migrations/versions/ 目录下的迁移脚本")
            print("2. 运行 `flask db upgrade` 应用迁移")
            
        except ImportError:
            print("❌ Flask-Migrate 未安装")
            print("请运行: pip install Flask-Migrate")
            return False
        
        return True

if __name__ == '__main__':
    print("🚀 BookRank 数据库迁移初始化")
    print("=" * 50)
    
    # 设置环境变量
    os.environ.setdefault('FLASK_APP', 'app')
    os.environ.setdefault('FLASK_ENV', 'development')
    
    success = init_migrations()
    sys.exit(0 if success else 1)
