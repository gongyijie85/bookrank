#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书籍数据同步脚本

该脚本用于同步所有出版社的新书数据，并将数据导出为静态 JSON 文件，
以便在 Render 免费版上使用。

使用方法：
    python update_books.py
"""

import os
import json
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('update_books.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 确保静态数据目录存在
STATIC_DATA_DIR = os.path.join('static', 'data')
os.makedirs(STATIC_DATA_DIR, exist_ok=True)


def sync_all_publishers():
    """同步所有出版社数据"""
    try:
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler
        from app.services.publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler
        from app.services.publisher_crawler.hachette import HachetteCrawler
        from app.services.publisher_crawler.harpercollins import HarperCollinsCrawler
        from app.services.publisher_crawler.macmillan import MacmillanCrawler
        from app.services.publisher_crawler.simon_schuster import SimonSchusterCrawler
        from app.services.publisher_crawler.open_library import OpenLibraryCrawler
    except ImportError as e:
        logger.error(f"导入模块失败: {e}")
        return {}

    publishers = {
        'google_books': GoogleBooksCrawler(),
        'penguin_random_house': PenguinRandomHouseCrawler(),
        'hachette': HachetteCrawler(),
        'harpercollins': HarperCollinsCrawler(),
        'macmillan': MacmillanCrawler(),
        'simon_schuster': SimonSchusterCrawler(),
        'open_library': OpenLibraryCrawler()
    }

    all_books = {}

    for publisher_name, crawler in publishers.items():
        logger.info(f"开始同步 {publisher_name}...")
        try:
            books = crawler.crawl()
            # 转换为字典格式
            books_dict = [book.to_dict() for book in books]
            all_books[publisher_name] = books_dict
            logger.info(f"{publisher_name} 同步完成，获取到 {len(books_dict)} 本书籍")
        except Exception as e:
            logger.error(f"同步 {publisher_name} 失败: {e}")
            all_books[publisher_name] = []

    return all_books


def export_to_static_files(books_data):
    """将书籍数据导出为静态 JSON 文件"""
    # 导出所有出版社数据
    all_data_path = os.path.join(STATIC_DATA_DIR, 'all_books.json')
    with open(all_data_path, 'w', encoding='utf-8') as f:
        json.dump(books_data, f, ensure_ascii=False, indent=2)
    logger.info(f"已导出所有数据到 {all_data_path}")

    # 为每个出版社单独导出数据
    for publisher_name, books in books_data.items():
        publisher_path = os.path.join(STATIC_DATA_DIR, f'{publisher_name}_books.json')
        with open(publisher_path, 'w', encoding='utf-8') as f:
            json.dump(books, f, ensure_ascii=False, indent=2)
        logger.info(f"已导出 {publisher_name} 数据到 {publisher_path}")

    # 创建更新时间文件
    update_time = {
        'timestamp': datetime.now().isoformat(),
        'publishers': list(books_data.keys()),
        'total_books': sum(len(books) for books in books_data.values())
    }
    update_time_path = os.path.join(STATIC_DATA_DIR, 'update_time.json')
    with open(update_time_path, 'w', encoding='utf-8') as f:
        json.dump(update_time, f, ensure_ascii=False, indent=2)
    logger.info(f"已更新时间戳到 {update_time_path}")


if __name__ == '__main__':
    logger.info("开始同步书籍数据...")
    
    # 同步所有出版社
    books_data = sync_all_publishers()
    
    # 导出为静态文件
    export_to_static_files(books_data)
    
    logger.info("同步完成！")
