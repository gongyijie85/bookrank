"""
Render 部署启动入口

用于 Render 部署的启动文件
"""
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)

# 导入应用
from app import app, db, migrate
from app.models.schemas import Award
from app.models.new_book import Publisher
from app.initialization import init_awards_data, init_sample_books


def init_database():
    """初始化数据库（首次部署时调用）"""
    with app.app_context():
        print("🔧 检查数据库...")
        
        # 运行数据库迁移
        print("🚀 运行数据库迁移...")
        try:
            migrate.upgrade()
            print("✅ 数据库迁移完成")
        except Exception as e:
            print(f"⚠️  数据库迁移失败: {e}")
            print("📋 尝试创建数据表...")
            # 如果迁移失败，尝试直接创建表
            db.create_all()
            print("✅ 数据表已就绪")
        
        # 检查是否需要初始化数据
        if Award.query.count() == 0:
            print("📦 初始化奖项数据...")
            init_awards_data(app)
        
        # 初始化出版社数据
        if Publisher.query.count() == 0:
            print("🏢 初始化出版社数据...")
            from app.services.new_book_service import NewBookService
            service = NewBookService()
            service.init_publishers()
        
        print("🎉 数据库初始化完成")


# 初始化数据库
init_database()

# Gunicorn 入口
application = app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
