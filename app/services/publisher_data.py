"""
出版社数据定义和静态数据导入辅助

从新书速递同步逻辑中提取，与实例状态分离。
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ==================== 出版社定义 ====================

DEFAULT_PUBLISHERS: list[dict[str, str | bool]] = [
    {
        'name': 'Google Books',
        'name_en': 'Google Books',
        'website': 'https://books.google.com',
        'crawler_class': 'GoogleBooksCrawler',
        # 通用关键词搜索，不限定出版社，实测会把公版经典的重印版当新书返回
        # （如1926年的《罗杰疑案》、1871年的《米德尔马契》），默认不启用。
        'is_active': False,
    },
    {
        'name': 'Open Library',
        'name_en': 'Open Library',
        'website': 'https://openlibrary.org',
        'crawler_class': 'OpenLibraryCrawler',
        # 实测直接不返回任何结果，默认不启用。
        'is_active': False,
    },
    {
        'name': '企鹅兰登',
        'name_en': 'Penguin Random House',
        'website': 'https://www.penguinrandomhouse.com',
        'crawler_class': 'PrhApiCrawler',
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
        # 工单 #112：官网首页对 Render 出口 IP 返回不同页面（本地可抓、生产自
        # 2026-06-22 起零入库），切回 Google Books 出版社通道（与 S&S 同模式）
        'crawler_class': 'HachetteGoogleCrawler',
    },
    {
        'name': '哈珀柯林斯',
        'name_en': 'HarperCollins',
        'website': 'https://www.harpercollins.com',
        # 工单 #112：同上，站点抓取在生产失效且详情页被 Cloudflare 拦截拿不到
        # 出版日期，切回 Google Books 出版社通道（带完整出版日期）
        'crawler_class': 'HarperCollinsGoogleCrawler',
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

# 英文分类到中文的映射表（sanitize_category 使用）
CATEGORY_EN_TO_ZH: dict[str, str] = {
    'Fiction': '小说',
    'Nonfiction': '非虚构',
    'Mystery': '悬疑',
    'Romance': '言情',
    'Thriller': '惊悚',
    'Science Fiction': '科幻',
    'Fantasy': '奇幻',
    'Biography': '传记',
    'History': '历史',
    'Children': '儿童读物',
    'Young Adult': '青少年',
    'Business': '商业',
    'Self-Help': '自助',
    'General': '综合',
    'general': '综合',
    'Young Adult Fiction': '青少年小说',
    'Juvenile Fiction': '儿童小说',
    'Juvenile Nonfiction': '儿童非小说',
    'Health & Fitness': '健康养生',
    'Literary Criticism': '文学评论',
}

VALID_CATEGORIES: set[str] = {
    '小说',
    '非虚构',
    '悬疑',
    '言情',
    '惊悚',
    '科幻',
    '奇幻',
    '传记',
    '历史',
    '儿童读物',
    '青少年',
    '商业',
    '自助',
    'Fiction',
    'Nonfiction',
    'Mystery',
    'Romance',
    'Thriller',
    'Science Fiction',
    'Fantasy',
    'Biography',
    'History',
    'Children',
    'Young Adult',
    'Business',
    'Self-Help',
}

# 旧爬虫 -> 新爬虫的迁移映射
CRAWLER_MIGRATION: dict[str, str] = {
    'SimonSchusterCrawler': 'SimonSchusterGoogleCrawler',
    # 工单 #112：站点爬虫在生产失效（2026-06-22 起零入库），切回 Google Books 通道；
    # 此前的反向迁移（Google -> 站点）已废弃移除
    'HachetteCrawler': 'HachetteGoogleCrawler',
    'HarperCollinsCrawler': 'HarperCollinsGoogleCrawler',
    'MacmillanGoogleCrawler': 'MacmillanCrawler',
    'PenguinRandomHouseCrawler': 'PrhApiCrawler',
}

# 营销关键词过滤（_sanitize_category 使用）
MARKETING_KEYWORDS: list[str] = [
    'learn more',
    'read more',
    'see what',
    'take the quiz',
    'join our',
    'browse all',
    'how to',
    'on the rise',
    'you need to',
    'you love',
    'audiobook',
    'events',
    'new releases',
    'new stories',
    'lists, essays',
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
    """清洗分类数据，过滤营销文案，统一英文分类为中文"""
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
    # 英文分类映射为中文
    return CATEGORY_EN_TO_ZH.get(category, category)


def resolve_static_data_dir(static_data_dir: str | Path | None = None) -> Path:
    """解析静态数据目录路径"""
    from flask import current_app, has_app_context

    if static_data_dir:
        return Path(static_data_dir)
    if has_app_context() and current_app.static_folder:
        return Path(current_app.static_folder) / 'data'
    return Path(__file__).resolve().parents[2] / 'static' / 'data'
