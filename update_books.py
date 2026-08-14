#!/usr/bin/env python3
"""
书籍数据同步脚本

该脚本用于同步所有出版社的新书数据，并将数据导出为静态 JSON 文件，
以便在 Render 免费版上使用。

使用方法：
    python update_books.py
"""

import json
import logging
import os
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('update_books.log', encoding='utf-8')],
)
logger = logging.getLogger(__name__)

# 确保静态数据目录存在
STATIC_DATA_DIR = os.path.join('static', 'data')
os.makedirs(STATIC_DATA_DIR, exist_ok=True)


# 活跃爬虫的静态数据导出 slug：与 static/data/*_books.json 的兜底种子
# 文件名（app/services/publisher_data.py 的 STATIC_DATA_FILES）保持一致
_PUBLISHER_EXPORTS = [
    ('Google Books', 'google_books'),
    ('Penguin Random House', 'penguin_random_house'),
    ('Hachette', 'hachette'),
    ('HarperCollins', 'harpercollins'),
    ('Macmillan', 'macmillan'),
    ('Simon & Schuster', 'simon_schuster'),
    ('Open Library', 'open_library'),
]


def sync_all_publishers():
    """并行同步所有出版社数据（走注册表与新爬虫接口 CrawlRequest/CrawlOutcome）。

    v0.9.47：7 个出版社爬虫改为 ThreadPoolExecutor 并行。
    爬虫是 IO 密集型（HTTP 请求），线程足够，无需 multiprocessing。
    """
    try:
        from app.services.publisher_crawler import get_crawler_class
        from app.services.publisher_crawler.base_crawler import CrawlRequest
        from app.services.publisher_data import DEFAULT_PUBLISHERS
    except ImportError as e:
        logger.error(f'导入模块失败: {e}')
        return {}

    class_by_name_en = {p['name_en']: p['crawler_class'] for p in DEFAULT_PUBLISHERS}

    def _sync_one(item: tuple) -> tuple:
        """单个 publisher 同步任务（线程 worker）

        失败隔离：单个 publisher 失败不影响其他。
        """
        name_en, slug = item
        logger.info(f'开始同步 {name_en}...')
        try:
            crawler_cls = get_crawler_class(class_by_name_en[name_en])
            if crawler_cls is None:
                logger.error(f'爬虫类不可用: {name_en}')
                return slug, []
            crawler = crawler_cls()
            outcome = crawler.get_new_books(CrawlRequest(max_books=100))
            return slug, [book.to_dict() for book in outcome.books]
        except Exception as e:
            logger.error(f'同步 {name_en} 失败: {e}')
            return slug, []

    all_books: dict = {}

    # v0.9.47：使用线程池并行，max_workers 与 publisher 数量一致
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(
        max_workers=len(_PUBLISHER_EXPORTS), thread_name_prefix='pub-crawl'
    ) as executor:
        futures = {executor.submit(_sync_one, item): item for item in _PUBLISHER_EXPORTS}
        for future in as_completed(futures):
            slug, books = future.result()
            all_books[slug] = books
            logger.info(f'{slug} 同步完成，获取到 {len(books)} 本书籍')

    return all_books


def export_to_static_files(books_data):
    """将书籍数据导出为静态 JSON 文件"""
    # 导出所有出版社数据
    all_data_path = os.path.join(STATIC_DATA_DIR, 'all_books.json')
    with open(all_data_path, 'w', encoding='utf-8') as f:
        json.dump(books_data, f, ensure_ascii=False, indent=2)
    logger.info(f'已导出所有数据到 {all_data_path}')

    # 为每个出版社单独导出数据
    for publisher_name, books in books_data.items():
        publisher_path = os.path.join(STATIC_DATA_DIR, f'{publisher_name}_books.json')
        with open(publisher_path, 'w', encoding='utf-8') as f:
            json.dump(books, f, ensure_ascii=False, indent=2)
        logger.info(f'已导出 {publisher_name} 数据到 {publisher_path}')

    # 创建更新时间文件
    update_time = {
        'timestamp': datetime.now().isoformat(),
        'publishers': list(books_data.keys()),
        'total_books': sum(len(books) for books in books_data.values()),
    }
    update_time_path = os.path.join(STATIC_DATA_DIR, 'update_time.json')
    with open(update_time_path, 'w', encoding='utf-8') as f:
        json.dump(update_time, f, ensure_ascii=False, indent=2)
    logger.info(f'已更新时间戳到 {update_time_path}')


if __name__ == '__main__':
    logger.info('开始同步书籍数据...')

    # 同步所有出版社
    books_data = sync_all_publishers()

    # 导出为静态文件
    export_to_static_files(books_data)

    logger.info('同步完成！')
