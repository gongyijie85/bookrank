"""
检查所有出版社状态
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def check_database():
    """检查数据库中的出版社和书籍数据"""
    print("\n" + "="*60)
    print("🗄️ 检查数据库状态")
    print("="*60)
    
    try:
        app = create_app()
        with app.app_context():
            from app.models.database import db
            from app.models.new_book import NewBook, Publisher
            
            # 检查出版社
            publishers = Publisher.query.order_by(Publisher.name_en).all()
            print(f"\n📚 出版社总数: {len(publishers)}")
            
            print("\n" + "-"*60)
            print(f"{'出版社':<20} {'英文名':<25} {'状态':<8} {'书籍数':<8}")
            print("-"*60)
            
            for pub in publishers:
                book_count = NewBook.query.filter_by(publisher_id=pub.id).count()
                status = "✅ 启用" if pub.is_active else "❌ 禁用"
                print(f"{pub.name:<20} {pub.name_en:<25} {status:<8} {book_count:<8}")
            
            print("-"*60)
            
            # 检查所有新书
            total_books = NewBook.query.count()
            displayable_books = NewBook.query.filter_by(is_displayable=True).count()
            
            print(f"\n📖 新书总数: {total_books}")
            print(f"📖 可展示书籍: {displayable_books}")
            
            # 按出版社统计
            print(f"\n📊 按出版社统计:")
            from sqlalchemy import func
            stats = db.session.query(
                Publisher.name_en,
                func.count(NewBook.id).label('count')
            ).outerjoin(NewBook, Publisher.id == NewBook.publisher_id
            ).group_by(Publisher.id
            ).order_by(func.count(NewBook.id).desc()
            ).all()
            
            for name, count in stats:
                print(f"  {name}: {count} 本")
            
            return publishers
            
    except Exception as e:
        print(f"\n❌ 数据库检查失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def check_crawler_classes():
    """检查爬虫类是否都可用"""
    print("\n" + "="*60)
    print("🔍 检查爬虫类")
    print("="*60)
    
    crawlers_to_check = [
        ('Google Books', 'google_books', 'GoogleBooksCrawler'),
        ('Open Library', 'open_library', 'OpenLibraryCrawler'),
        ('Penguin Random House', 'penguin_random_house', 'PenguinRandomHouseCrawler'),
        ('Simon & Schuster', 'simon_schuster', 'SimonSchusterCrawler'),
        ('Hachette', 'hachette', 'HachetteCrawler'),
        ('HarperCollins', 'harpercollins', 'HarperCollinsCrawler'),
        ('Macmillan', 'macmillan', 'MacmillanCrawler'),
    ]
    
    available = []
    missing = []
    
    for name, module_name, class_name in crawlers_to_check:
        try:
            module = __import__(f'app.services.publisher_crawler.{module_name}', fromlist=[class_name])
            crawler_cls = getattr(module, class_name)
            print(f"✅ {name}: {class_name} 可用")
            available.append((name, crawler_cls))
        except Exception as e:
            print(f"❌ {name}: 无法导入 - {e}")
            missing.append(name)
    
    print(f"\n📊 可用: {len(available)}, 缺失: {len(missing)}")
    return available


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔍 出版社状态检查")
    print("="*60)
    
    # 检查数据库
    publishers = check_database()
    
    # 检查爬虫类
    crawlers = check_crawler_classes()
    
    print("\n" + "="*60)

