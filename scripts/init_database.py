"""
初始化数据库

创建所有必要的数据库表结构。
"""
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.database import db

def init_database():
    """初始化数据库"""
    print("🚀 开始初始化数据库...")
    
    # 创建Flask应用
    app = create_app()
    
    with app.app_context():
        # 创建所有表
        print("📚 创建数据库表...")
        db.create_all()
        print("✅ 数据库表创建完成")
        
        # 初始化出版社数据
        print("\n📢 初始化出版社数据...")
        from app.services.new_book_service import NewBookService
        service = NewBookService()
        count = service.init_publishers()
        print(f"✅ 成功初始化 {count} 个出版社")
        
        # 测试同步数据
        print("\n🔄 测试同步新书数据...")
        try:
            # 同步Google Books数据
            publishers = service.get_publishers(active_only=True)
            for publisher in publishers:
                if publisher.crawler_class == 'GoogleBooksCrawler':
                    print(f"  同步 {publisher.name} 数据...")
                    result = service.sync_publisher_books(publisher.id, max_books=10)
                    print(f"  结果: {result}")
                    break
        except Exception as e:
            print(f"⚠️ 同步测试失败: {e}")
    
    print("\n🎉 数据库初始化完成！")

if __name__ == "__main__":
    init_database()
