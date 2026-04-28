"""
Penguin Random House（企鹅兰登）出版社爬虫

使用 Google Books API 获取 Penguin Random House 出版社的书籍数据。
避免直接爬取出版社网站（Cloudflare 403 防护）。

Google Books 查询语法:
- publisher:"Penguin Random House" 可筛选特定出版社
"""
import logging
from typing import Any

from .google_books import GoogleBooksCrawler

logger = logging.getLogger(__name__)


class PenguinRandomHouseCrawler(GoogleBooksCrawler):
    """
    Penguin Random House 出版社爬虫（基于 Google Books API）

    通过 Google Books API 的 publisher 筛选获取 Penguin Random House 出版的书籍，
    避免直接爬取官网导致的 403 问题。

    官方网站：https://www.penguinrandomhouse.com/
    """

    PUBLISHER_NAME = "企鹅兰登"
    PUBLISHER_NAME_EN = "Penguin Random House"
    PUBLISHER_WEBSITE = "https://www.penguinrandomhouse.com"
    CRAWLER_CLASS_NAME = "PenguinRandomHouseCrawler"

    # Google Books 出版社查询名称（含空格需加引号）
    GOOGLE_PUBLISHER_QUERY = '"Penguin Random House"'

    CATEGORY_MAP = {
        'fiction': '小说',
        'nonfiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'thriller': '惊悚',
        'science_fiction': '科幻',
        'fantasy': '奇幻',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young_adult': '青少年',
        'business': '商业',
        'self_help': '自助',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 0.8

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'nonfiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'thriller', 'name': '惊悚'},
            {'id': 'science_fiction', 'name': '科幻'},
            {'id': 'fantasy', 'name': '奇幻'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young_adult', 'name': '青少年'},
            {'id': 'business', 'name': '商业'},
            {'id': 'self_help', 'name': '自助'},
        ]

    def _build_query_params(
        self,
        subject: str,
        max_results: int,
        start_index: int = 0,
    ) -> dict[str, Any]:
        """构建查询参数，添加 publisher 筛选"""
        query_parts = [f"publisher:{self.GOOGLE_PUBLISHER_QUERY}"]

        if subject and subject != "general":
            query_parts.append(f"subject:{subject}")
        else:
            query_parts.append("books")

        params = {
            "q": " ".join(query_parts),
            "maxResults": min(max_results, 40),
            "startIndex": start_index,
            "printType": "books",
            "langRestrict": "en",
            "orderBy": "newest",
        }

        if self._key_is_valid and self._api_key:
            params["key"] = self._api_key

        return params

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
        year_from: int | None = None,
    ):
        """
        获取 Penguin Random House 新书列表

        通过 Google Books API 的 publisher 筛选获取。
        """
        logger.info(
            "正在通过 Google Books API 获取 %s 的新书...",
            self.PUBLISHER_NAME_EN,
        )
        yield from super().get_new_books(
            category=category,
            max_books=max_books,
            year_from=year_from,
        )
