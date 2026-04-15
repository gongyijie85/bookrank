"""
比较不同数据源的爬取结果

测试不同爬虫获取的新书数据，对比出版社网站和Google Books的一致性。
"""
import os
import sys
import logging
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.publisher_crawler import (
    OpenLibraryCrawler, GoogleBooksCrawler,
    PenguinRandomHouseCrawler, SimonSchusterCrawler,
    HachetteCrawler, HarperCollinsCrawler, MacmillanCrawler
)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_crawler(crawler_class, category='fiction', max_books=10):
    """测试单个爬虫"""
    try:
        logger.info(f"\n🧪 测试 {crawler_class.__name__}...")
        crawler = crawler_class()
        books = []
        
        with crawler:
            for book in crawler.get_new_books(category=category, max_books=max_books):
                books.append(book)
                logger.info(f"  - {book.title} ({book.author})")
                if book.publication_date:
                    logger.info(f"    出版日期: {book.publication_date}")
                if book.isbn13:
                    logger.info(f"    ISBN: {book.isbn13}")
        
        logger.info(f"✅ {crawler_class.__name__} 爬取完成，共获取 {len(books)} 本书")
        return books
    except Exception as e:
        logger.error(f"❌ {crawler_class.__name__} 测试失败: {e}")
        return []

def compare_crawlers():
    """比较不同爬虫的结果"""
    logger.info("🚀 开始比较不同数据源的爬取结果...")
    
    # 测试不同爬虫
    crawlers = [
        (GoogleBooksCrawler, "Google Books"),
        (OpenLibraryCrawler, "Open Library"),
        # (PenguinRandomHouseCrawler, "Penguin Random House"),  # 被反爬
        # (SimonSchusterCrawler, "Simon & Schuster"),  # 被反爬
        # (HachetteCrawler, "Hachette"),  # 被反爬
        # (HarperCollinsCrawler, "HarperCollins"),  # 被反爬
        # (MacmillanCrawler, "Macmillan"),  # 被反爬
    ]
    
    results = {}
    for crawler_class, name in crawlers:
        books = test_crawler(crawler_class)
        results[name] = books
    
    # 分析结果
    logger.info("\n📊 结果分析:")
    for name, books in results.items():
        recent_books = [b for b in books if b.publication_date and b.publication_date.year >= 2024]
        logger.info(f"{name}: 共 {len(books)} 本，2024年后出版: {len(recent_books)} 本")
    
    # 对比Google Books和其他数据源
    if 'Google Books' in results and 'Open Library' in results:
        google_books = {b.title.lower() for b in results['Google Books']}
        open_library_books = {b.title.lower() for b in results['Open Library']}
        
        common_books = google_books & open_library_books
        logger.info(f"\n🔄 共同书籍: {len(common_books)}")
        for book in common_books:
            logger.info(f"  - {book}")
        
        google_only = google_books - open_library_books
        logger.info(f"\n📚 Google Books 独有: {len(google_only)}")
        for book in list(google_only)[:5]:  # 只显示前5本
            logger.info(f"  - {book}")
        
        open_only = open_library_books - google_books
        logger.info(f"\n📚 Open Library 独有: {len(open_only)}")
        for book in list(open_only)[:5]:  # 只显示前5本
            logger.info(f"  - {book}")

if __name__ == "__main__":
    compare_crawlers()
