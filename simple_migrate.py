#!/usr/bin/env python
"""
简单的数据库迁移脚本 - 解决路径问题
"""
import os
import sys
from pathlib import Path

# 强制使用项目目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["FLASK_APP"] = "app"
os.environ["FLASK_ENV"] = "development"

print("="*60)
print("🚀 简单数据库迁移脚本")
print("="*60)

# 步骤 1: 检查并导入 Flask-Migrate
print("\n📋 步骤 1/3: 检查依赖...")
try:
    from flask_migrate import init, migrate, upgrade
    from app import create_app
    print("✅ 所有依赖已导入")
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("\n请运行: pip install flask-talisman flask-cors flask-caching")
    sys.exit(1)

# 步骤 2: 初始化迁移目录
print("\n📋 步骤 2/3: 初始化迁移...")
migrations_dir = project_root / "migrations"

if not migrations_dir.exists():
    print("⏳ 初始化迁移目录...")
    app = create_app('development')
    with app.app_context():
        try:
            init(directory='migrations')
            print("✅ 迁移目录已创建")
        except Exception as e:
            print(f"⚠️  迁移目录可能已存在: {e}")
else:
    print("✅ 迁移目录已存在")

# 步骤 3: 生成迁移脚本
print("\n📋 步骤 3/3: 生成迁移脚本...")
app = create_app('development')
with app.app_context():
    try:
        migrate(directory='migrations', message='Initial migration - all tables')
        print("✅ 迁移脚本已生成")
        
        # 检查迁移文件
        versions_dir = migrations_dir / "versions"
        if versions_dir.exists():
            version_files = list(versions_dir.glob("*.py"))
            if version_files:
                print(f"✅ 找到 {len(version_files)} 个迁移文件")
                for f in version_files[-3:]:
                    print(f"   - {f.name}")
        
    except Exception as e:
        print(f"⚠️  迁移脚本可能已存在: {e}")

print("\n" + "="*60)
print("🎉 配置完成！")
print("="*60)
print("\n📝 下一步操作:")
print("1. 检查 migrations/versions/ 目录下的迁移文件")
print("2. 提交到 git:")
print("   git add migrations/ Procfile")
print("   git commit -m 'feat: add database migrations'")
print("   git push origin main")
print("\n3. 在 Render 上部署")
print("\n✅ 完成！")
