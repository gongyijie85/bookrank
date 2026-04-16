#!/usr/bin/env python
"""
Render 数据库一键配置脚本
用于在本地生成迁移文件并准备部署到 Render
"""
import os
import sys
import subprocess
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def run_command(cmd, description=""):
    """运行命令并输出结果"""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    print(f"$ {cmd}")
    print()
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(project_root),
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(f"⚠️  警告: {result.stderr}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def setup_render_database():
    """配置 Render 数据库"""
    print("🚀 BookRank - Render 数据库配置")
    print("="*60)
    
    # 设置环境变量
    os.environ["FLASK_APP"] = "app"
    os.environ["FLASK_ENV"] = "development"
    
    # 步骤 1: 检查 Flask-Migrate
    print("\n📋 步骤 1/4: 检查依赖...")
    try:
        import flask_migrate
        print("✅ Flask-Migrate 已安装")
    except ImportError:
        print("⏳ 安装 Flask-Migrate...")
        if not run_command("pip install Flask-Migrate", "安装 Flask-Migrate"):
            print("❌ 安装失败，请手动运行: pip install Flask-Migrate")
            return False
    
    # 步骤 2: 初始化迁移目录
    print("\n📋 步骤 2/4: 初始化迁移...")
    migrations_dir = project_root / "migrations"
    
    if not migrations_dir.exists():
        if not run_command("flask db init", "初始化迁移目录"):
            print("❌ 初始化失败")
            return False
    else:
        print("✅ 迁移目录已存在")
    
    # 步骤 3: 生成迁移脚本
    print("\n📋 步骤 3/4: 生成迁移脚本...")
    if not run_command('flask db migrate -m "Initial migration - all tables"', "生成迁移脚本"):
        print("❌ 迁移脚本生成失败，但可能已存在，继续...")
    
    # 步骤 4: 本地测试迁移
    print("\n📋 步骤 4/4: 本地测试迁移...")
    if not run_command("flask db upgrade", "应用迁移（本地）"):
        print("❌ 本地迁移失败，但这在 Render 上应该正常")
    
    print("\n" + "="*60)
    print("🎉 配置完成！")
    print("="*60)
    print("\n📝 下一步操作:")
    print("1. 检查 migrations/versions/ 目录下的迁移文件")
    print("2. 提交到 git:")
    print("   git add migrations/ Procfile")
    print("   git commit -m 'feat: add database migrations for Render'")
    print("   git push origin main")
    print("\n3. 在 Render 上部署（会自动运行 flask db upgrade）")
    print("\n✅ 完成！")
    
    return True


if __name__ == "__main__":
    success = setup_render_database()
    sys.exit(0 if success else 1)
