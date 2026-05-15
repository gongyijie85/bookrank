"""
对比不同数据源的爬取结果

测试Google Books和Open Library爬虫，对比它们获取的新书数据。
"""
import os
import sys
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.services.new_book_service import NewBookService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def compare_data_sources():
    """对比不同数据源"""
    app = create_app()
    
    with app.app_context():
        service = NewBookService()
        
        # 同步Google Books数据
        logger.info("\n🔄 同步 Google Books 数据...")
        google_result = service.sync_publisher_books(6, max_books=10)  # Google Books ID
        logger.info(f"Google Books 同步结果: {google_result}")
        
        # 同步Open Library数据
        logger.info("\n🔄 同步 Open Library 数据...")
        open_library_result = service.sync_publisher_books(7, max_books=10)  # Open Library ID
        logger.info(f"Open Library 同步结果: {open_library_result}")
        
        # 获取所有新书
        logger.info("\n📊 对比两个数据源的结果...")
        books, total = service.get_new_books(days=365, page=1, per_page=50)
        
        google_books = []
        open_library_books = []
        
        for book in books:
            if book.publisher.name_en == 'Google Books':
                google_books.append(book)
            elif book.publisher.name_en == 'Open Library':
                open_library_books.append(book)
        
        logger.info(f"\nGoogle Books 新书: {len(google_books)} 本")
        for book in google_books[:5]:
            logger.info(f"  - {book.title} ({book.publication_date if book.publication_date else '未知日期'})")
        
        logger.info(f"\nOpen Library 新书: {len(open_library_books)} 本")
        for book in open_library_books[:5]:
            logger.info(f"  - {book.title} ({book.publication_date if book.publication_date else '未知日期'})")
        
        # 分析出版日期
        google_recent = [b for b in google_books if b.publication_date and b.publication_date.year >= 2024]
        open_recent = [b for b in open_library_books if b.publication_date and b.publication_date.year >= 2024]
        
        logger.info(f"\n📅 2024年后出版的书籍:")
        logger.info(f"Google Books: {len(google_recent)}/{len(google_books)}")
        logger.info(f"Open Library: {len(open_recent)}/{len(open_library_books)}")

if __name__ == "__main__":
    compare_data_sources()
