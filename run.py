"""
Render 部署启动入口

用于 Render 部署的启动文件
"""
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)

# 导入应用
from app import app, db
from app.models.schemas import Award
from app.models.new_book import Publisher
from app.initialization import init_awards_data, init_sample_books


def run_migrations():
    """运行数据库迁移"""
    with app.app_context():
        print("🚀 运行数据库迁移...")
        try:
            from flask_migrate import Migrate, upgrade as _upgrade
            m = Migrate(app, db)
            _upgrade()
            print("✅ 数据库迁移完成")
            return True
        except Exception as e:
            print(f"⚠️  数据库迁移失败: {e}")
            print("📋 尝试直接添加缺失字段...")
            try:
                _add_missing_columns()
                print("✅ 缺失字段已补充")
                return True
            except Exception as e2:
                print(f"❌ 补充字段也失败: {e2}")
                return False


def _add_missing_columns():
    """手动添加缺失的中文字段（迁移失败时的备用方案）"""
    columns_to_add = [
        ("title_zh", "VARCHAR(500)"),
        ("description_zh", "TEXT"),
        ("details_zh", "TEXT"),
        ("translated_at", "TIMESTAMP"),
    ]
    
    engine = db.engine
    for col_name, col_type in columns_to_add:
        try:
            inspector = db.inspect(engine)
            existing_cols = [c['name'] for c in inspector.get_columns('book_metadata')]
            
            if col_name not in existing_cols:
                sql = f'ALTER TABLE book_metadata ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                db.session.execute(db.text(sql))
                print(f"   + 添加字段: {col_name}")
                
            db.session.commit()
        except Exception:
            db.session.rollback()


def init_database():
    """初始化数据库（首次部署时调用）"""
    with app.app_context():
        print("🔧 检查数据库...")
        
        migration_ok = run_migrations()
        
        if not migration_ok:
            print("📋 迁移失败，尝试 create_all...")
            db.create_all()
        
        if Award.query.count() == 0:
            print("📦 初始化奖项数据...")
            init_awards_data(app)
        
        if Publisher.query.count() == 0:
            print("🏢 初始化出版社数据...")
            from app.services.new_book_service import NewBookService
            service = NewBookService()
            service.init_publishers()
        
        print("🎉 数据库初始化完成")


init_database()

application = app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
