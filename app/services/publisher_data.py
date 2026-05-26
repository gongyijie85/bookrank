"""
出版社数据定义和静态数据导入辅助

从 NewBookService 中提取，与实例状态分离。
"""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ==================== 出版社定义 ====================

DEFAULT_PUBLISHERS: list[dict[str, str]] = [
    {
        'name': 'Google Books',
        'name_en': 'Google Books',
        'website': 'https://books.google.com',
        'crawler_class': 'GoogleBooksCrawler',
    },
    {
        'name': 'Open Library',
        'name_en': 'Open Library',
        'website': 'https://openlibrary.org',
        'crawler_class': 'OpenLibraryCrawler',
    },
    {
        'name': '企鹅兰登',
        'name_en': 'Penguin Random House',
        'website': 'https://www.penguinrandomhouse.com',
        'crawler_class': 'PenguinRandomHouseCrawler',
    },
    {
        'name': '西蒙舒斯特',
        'name_en': 'Simon & Schuster',
        'website': 'https://www.simonandschuster.com',
        'crawler_class': 'SimonSchusterGoogleCrawler',
    },
    {
        'name': '阿歇特',
        'name_en': 'Hachette',
        'website': 'https://www.hachettebookgroup.com',
        'crawler_class': 'HachetteCrawler',
    },
    {
        'name': '哈珀柯林斯',
        'name_en': 'HarperCollins',
        'website': 'https://www.harpercollins.com',
        'crawler_class': 'HarperCollinsCrawler',
    },
    {
        'name': '麦克米伦',
        'name_en': 'Macmillan',
        'website': 'https://us.macmillan.com',
        'crawler_class': 'MacmillanCrawler',
    },
]

STATIC_DATA_FILES: dict[str, str] = {
    'google_books_books.json': 'Google Books',
    'open_library_books.json': 'Open Library',
    'penguin_random_house_books.json': 'Penguin Random House',
    'simon_schuster_books.json': 'Simon & Schuster',
    'hachette_books.json': 'Hachette',
    'harpercollins_books.json': 'HarperCollins',
    'macmillan_books.json': 'Macmillan',
}

VALID_CATEGORIES: set[str] = {
    '小说', '非虚构', '悬疑', '言情', '惊悚', '科幻', '奇幻',
    '传记', '历史', '儿童读物', '青少年', '商业', '自助',
    'Fiction', 'Nonfiction', 'Mystery', 'Romance', 'Thriller',
    'Science Fiction', 'Fantasy', 'Biography', 'History',
    'Children', 'Young Adult', 'Business', 'Self-Help',
}

# 旧爬虫 -> 新爬虫的迁移映射
CRAWLER_MIGRATION: dict[str, str] = {
    'SimonSchusterCrawler': 'SimonSchusterGoogleCrawler',
    'HachetteCrawler': 'HachetteCrawler',
    'HarperCollinsCrawler': 'HarperCollinsCrawler',
    'MacmillanCrawler': 'MacmillanCrawler',
    'HachetteGoogleCrawler': 'HachetteCrawler',
    'HarperCollinsGoogleCrawler': 'HarperCollinsCrawler',
    'MacmillanGoogleCrawler': 'MacmillanCrawler',
}

# Google Books 搜索爬虫列表
GOOGLE_BOOKS_CRAWLERS: set[str] = {
    'GoogleBooksCrawler',
    'PenguinRandomHouseCrawler',
    'SimonSchusterGoogleCrawler',
    'HarperCollinsCrawler',
    'MacmillanCrawler',
}

# 营销关键词过滤（_sanitize_category 使用）
MARKETING_KEYWORDS: list[str] = [
    'learn more', 'read more', 'see what', 'take the quiz',
    'join our', 'browse all', 'how to', 'on the rise',
    'you need to', 'you love', 'audiobook', 'events',
    'new releases', 'new stories', 'lists, essays',
]


# ==================== 辅助函数 ====================


def normalize_isbn(value: Any, length: int) -> str | None:
    """标准化 ISBN 格式"""
    if not value:
        return None
    clean = re.sub(r'[^0-9Xx]', '', str(value)).upper()
    return clean if len(clean) == length else None


def parse_static_date(value: Any) -> date | None:
    """解析静态数据中的日期"""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == '%Y':
                return date(parsed.year, 1, 1)
            if fmt == '%Y-%m':
                return date(parsed.year, parsed.month, 1)
            return parsed.date()
        except ValueError:
            continue
    return None


def coerce_publication_date(value: Any) -> date | None:
    """规范化出版日期（爬虫/静态数据通用）"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_static_date(value)


def parse_int_safe(value: Any) -> int | None:
    """安全解析整数"""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sanitize_category(category: str | None) -> str | None:
    """清洗分类数据，过滤营销文案"""
    if not category:
        return None
    category = category.strip()
    if len(category) > 30:
        return None
    category_lower = category.lower()
    for keyword in MARKETING_KEYWORDS:
        if keyword in category_lower:
            return None
    if re.search(r'[>!<]|http[s]?://', category):
        return None
    if '"' in category or '"' in category or '"' in category:
        return None
    return category


def resolve_static_data_dir(static_data_dir: str | Path | None = None) -> Path:
    """解析静态数据目录路径"""
    from flask import current_app, has_app_context

    if static_data_dir:
        return Path(static_data_dir)
    if has_app_context() and current_app.static_folder:
        return Path(current_app.static_folder) / 'data'
    return Path(__file__).resolve().parents[2] / 'static' / 'data'
