"""
简单测试Google Books爬虫

验证Google Books爬虫是否能正确获取2024年的新书。
"""
import os
import sys
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.publisher_crawler import GoogleBooksCrawler

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def test_google_books_crawler():
    """测试Google Books爬虫"""
    logger.info("🧪 测试 Google Books 爬虫...")
    
    try:
        crawler = GoogleBooksCrawler()
        books = []
        
        with crawler:
            # 测试不同分类
            categories = ['fiction', 'nonfiction', 'science']
            
            for category in categories:
                logger.info(f"\n📚 测试分类: {category}")
                count = 0
                
                for book in crawler.get_new_books(category=category, max_books=5, year_from=2024):
                    books.append(book)
                    count += 1
                    logger.info(f"  {count}. {book.title}")
                    logger.info(f"     作者: {book.author}")
                    if book.publication_date:
                        logger.info(f"     出版日期: {book.publication_date}")
                    if book.isbn13:
                        logger.info(f"     ISBN: {book.isbn13}")
                
                logger.info(f"✅ 分类 {category} 完成，获取 {count} 本书")
        
        logger.info(f"\n📊 总计获取 {len(books)} 本书")
        return books
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    test_google_books_crawler()
