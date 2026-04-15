"""
Render 部署后数据库初始化脚本

在 Render 部署后，需要运行此脚本来：
1. 创建所有数据表
2. 初始化奖项数据
3. 初始化出版社数据
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from app.models.schemas import Award
from app.models.new_book import Publisher
from app.initialization import init_awards_data, init_sample_books


def init_database():
    """初始化数据库"""
    with app.app_context():
        print("🔧 开始初始化数据库...")
        
        # 创建所有表
        print("📦 创建数据表...")
        db.create_all()
        print("✅ 数据表创建完成")
        
        # 初始化奖项数据
        print("🏆 初始化奖项数据...")
        init_awards_data(app)
        
        # 初始化示例书籍
        print("📚 初始化示例书籍...")
        init_sample_books(app)
        
        # 初始化出版社数据
        print("🏢 初始化出版社数据...")
        from app.services.new_book_service import NewBookService
        service = NewBookService()
        count = service.init_publishers()
        print(f"✅ 创建了 {count} 个出版社")
        
        print("\n🎉 数据库初始化完成！")


if __name__ == "__main__":
    init_database()
