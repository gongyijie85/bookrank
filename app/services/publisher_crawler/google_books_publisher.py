"""
Google Books 出版社搜索爬虫

通过 Google Books API 的 inpublisher: 查询语法，按出版社名搜索新书。
适用于没有自己 API 的出版社（如 Simon & Schuster、Hachette、HarperCollins、Macmillan）。

API 文档: https://developers.google.com/books/docs/v1/reference/volumes/list
查询语法: https://developers.google.com/books/docs/v1/using#PerformingSearch

用法:
    为每个出版社创建独立的子类，只需设置 PUBLISHER_NAME、PUBLISHER_NAME_EN、
    PUBLISHER_WEBSITE 和 SEARCH_QUERIES 即可。
"""
import logging
from datetime import datetime
from typing import Any, Generator

from .google_books import GoogleBooksCrawler
from .base_crawler import BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class GoogleBooksPublisherCrawler(GoogleBooksCrawler):
    """
    Google Books 出版社搜索爬虫基类

    通过 inpublisher: 查询语法搜索特定出版社的新书。
    子类只需配置以下属性：

    - PUBLISHER_NAME: 出版社中文名
    - PUBLISHER_NAME_EN: 出版社英文名
    - PUBLISHER_WEBSITE: 出版社官网
    - CRAWLER_CLASS_NAME: 爬虫类名
    - SEARCH_QUERIES: 搜索关键词列表（用于组合 inpublisher: 查询）
    """

    # 子类需要覆盖
    SEARCH_QUERIES: list[str] = ["books"]

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
        year_from: int | None = None,
    ) -> Generator[BookInfo, None, None]:
        """
        按出版社名搜索新书

        使用 inpublisher: 语法限制搜索范围到指定出版社，
        再结合关键词搜索获取该出版社的新书。

        Args:
            category: 未使用（保持接口兼容）
            max_books: 最大获取数量
            year_from: 出版年份起（默认近3年）

        Yields:
            BookInfo 对象
        """
        current_year = datetime.now().year
        min_year = year_from or (current_year - 3)

        logger.info(
            "正在从 Google Books 搜索 %s 的新书 (%s-%s)...",
            self.PUBLISHER_NAME_EN, min_year, current_year,
        )

        self._validate_api_key()

        collected = 0
        seen_isbns: set[str] = set()

        for query in self.SEARCH_QUERIES:
            if collected >= max_books:
                break

            search_query = f'inpublisher:"{self.PUBLISHER_NAME_EN}" {query}'
            logger.info("搜索查询: %s", search_query)

            start_index = 0
            max_pages = 3  # 每个关键词最多翻3页

            for page in range(max_pages):
                if collected >= max_books:
                    break

                remaining = max_books - collected
                params = {
                    "q": search_query,
                    "maxResults": min(remaining, 40),
                    "startIndex": start_index,
                    "printType": "books",
                    "langRestrict": "en",
                    "orderBy": "newest",  # 按出版日期降序
                }

                if self._key_is_valid and self._api_key:
                    params["key"] = self._api_key

                try:
                    response = self._session.get(
                        self.BASE_URL,
                        params=params,
                        timeout=self.config.timeout,
                    )

                    if response.status_code == 400 and self._key_is_valid:
                        logger.warning("API Key 可能已失效，尝试无Key模式")
                        self._key_is_valid = False
                        params.pop("key", None)
                        response = self._session.get(
                            self.BASE_URL,
                            params=params,
                            timeout=self.config.timeout,
                        )

                    response.raise_for_status()
                    data = response.json()

                except Exception as e:
                    logger.error("Google Books API 请求失败: %s", e)
                    break

                items = data.get("items", [])
                if not items:
                    logger.info("查询 '%s' 第 %d 页无更多结果", query, page + 1)
                    break

                total_items = data.get("totalItems", 0)

                for item in items:
                    if collected >= max_books:
                        break

                    volume_info = item.get("volumeInfo", {})
                    published_date = volume_info.get("publishedDate", "")

                    if not self._is_recent_book(published_date, min_year):
                        continue

                    # 去重：用 ISBN 或标题
                    isbn_key = self._get_isbn_key(volume_info)
                    if isbn_key in seen_isbns:
                        continue
                    seen_isbns.add(isbn_key)

                    book_info = self._parse_volume_info(volume_info, "general")
                    if book_info:
                        # 设置来源信息
                        book_info.source_url = (
                            volume_info.get("canonicalVolumeLink", "")
                            or f"https://books.google.com/books?id={item.get('id', '')}"
                        )
                        yield book_info
                        collected += 1

                start_index += len(items)
                if start_index >= total_items:
                    break

        if collected == 0:
            logger.warning(
                "Google Books 未找到 %s 的 %s 年后新书",
                self.PUBLISHER_NAME_EN, min_year,
            )
        else:
            logger.info(
                "Google Books 共获取 %d 本 %s 新书",
                collected, self.PUBLISHER_NAME_EN,
            )

    @staticmethod
    def _get_isbn_key(volume_info: dict) -> str:
        """从卷信息中提取去重键（优先ISBN，其次标题+作者）"""
        identifiers = volume_info.get("industryIdentifiers", [])
        for ident in identifiers:
            if ident.get("type") in ("ISBN_13", "ISBN_10"):
                return ident.get("identifier", "")
        title = volume_info.get("title", "")
        author = (volume_info.get("authors") or [""])[0]
        return f"{title}|{author}".lower()


# ============================================================
# 各出版社具体爬虫类（只需配置属性即可）
# ============================================================

class SimonSchusterGoogleCrawler(GoogleBooksPublisherCrawler):
    """Simon & Schuster - 通过 Google Books 搜索"""

    PUBLISHER_NAME = "西蒙舒斯特"
    PUBLISHER_NAME_EN = "Simon & Schuster"
    PUBLISHER_WEBSITE = "https://www.simonandschuster.com"
    CRAWLER_CLASS_NAME = "SimonSchusterGoogleCrawler"

    SEARCH_QUERIES = [
        "fiction",
        "nonfiction",
        "thriller",
        "mystery",
        "romance",
        "biography",
        "history",
        "science",
        "self-help",
        "business",
    ]


class HachetteGoogleCrawler(GoogleBooksPublisherCrawler):
    """Hachette Book Group - 通过 Google Books 搜索"""

    PUBLISHER_NAME = "阿歇特"
    PUBLISHER_NAME_EN = "Hachette"
    PUBLISHER_WEBSITE = "https://www.hachettebookgroup.com"
    CRAWLER_CLASS_NAME = "HachetteGoogleCrawler"

    # Hachette 旗下有多家子出版社，用多个名称搜索
    SEARCH_QUERIES = [
        "fiction",
        "nonfiction",
        "thriller",
        "mystery",
        "romance",
        "fantasy",
        "science fiction",
        "biography",
        "history",
        "young adult",
    ]

    def get_new_books(self, category=None, max_books=100, year_from=None):
        """搜索 Hachette 及其子出版社的新书"""
        # 临时覆盖搜索，加入子出版社名称
        original_queries = self.SEARCH_QUERIES.copy()
        sub_publishers = [
            "Grand Central Publishing",
            "Little, Brown",
            "Orbit",
            "Mulholland Books",
            "Back Bay Books",
        ]

        # 先搜主出版社
        yield from super().get_new_books(category, max_books // 2, year_from)

        # 再搜子出版社
        self.SEARCH_QUERIES = ["fiction", "nonfiction", "thriller"]
        remaining = max_books - max_books // 2
        for sub_pub in sub_publishers:
            if remaining <= 0:
                break
            old_name = self.PUBLISHER_NAME_EN
            self.PUBLISHER_NAME_EN = sub_pub
            count_before = 0
            for book in super().get_new_books(category, min(10, remaining), year_from):
                yield book
                count_before += 1
                remaining -= 1
            self.PUBLISHER_NAME_EN = old_name

        self.SEARCH_QUERIES = original_queries


class HarperCollinsGoogleCrawler(GoogleBooksPublisherCrawler):
    """HarperCollins - 通过 Google Books 搜索"""

    PUBLISHER_NAME = "哈珀柯林斯"
    PUBLISHER_NAME_EN = "HarperCollins"
    PUBLISHER_WEBSITE = "https://www.harpercollins.com"
    CRAWLER_CLASS_NAME = "HarperCollinsGoogleCrawler"

    SEARCH_QUERIES = [
        "fiction",
        "nonfiction",
        "thriller",
        "mystery",
        "romance",
        "fantasy",
        "science fiction",
        "biography",
        "history",
        "self-help",
    ]


class MacmillanGoogleCrawler(GoogleBooksPublisherCrawler):
    """Macmillan - 通过 Google Books 搜索"""

    PUBLISHER_NAME = "麦克米伦"
    PUBLISHER_NAME_EN = "Macmillan"
    PUBLISHER_WEBSITE = "https://us.macmillan.com"
    CRAWLER_CLASS_NAME = "MacmillanGoogleCrawler"

    SEARCH_QUERIES = [
        "fiction",
        "nonfiction",
        "thriller",
        "mystery",
        "fantasy",
        "science fiction",
        "romance",
        "biography",
        "history",
        "literary fiction",
    ]
