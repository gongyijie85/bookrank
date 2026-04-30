"""
Macmillan（麦克米伦）出版社爬虫

数据源策略（v1.7.0 修复版）：
1. Google Books API 多印记查询（主要，覆盖 Macmillan 旗下所有子出版社）
2. Macmillan Sitemap ISBN + Google Books ISBN 查询（补充）

Macmillan 官网被 Cloudflare 完全封锁（包括首页和详情页），
因此无法直接爬取官网，采用以上组合策略获取最新书目。
"""

import gzip
import logging
import random
import re
from datetime import date, datetime
from typing import Generator

import requests

from .base_crawler import BookInfo, CrawlerConfig
from .google_books import GoogleBooksCrawler

logger = logging.getLogger(__name__)

# Macmillan 旗下主要印记（子出版社），用于 Google Books 多源查询
MACMILLAN_IMPRINTS = [
    "Macmillan",
    "St. Martin's Press",
    "Farrar Straus and Giroux",
    "Henry Holt",
    "Tor Books",
    "Picador",
    "Flatiron Books",
    "Celadon Books",
]

# Macmillan 产品 sitemap 列表
SITEMAP_BASE = "https://us.macmillan.com/sitemaps/sitemap-products.{n}.xml.gz"
# 检查多个 sitemap 区间（编号越大不一定越新，随机采样）
SITEMAP_RANGE = range(1, 32)
# 每次随机采样的 sitemap 数量
SITEMAP_SAMPLE_SIZE = 6
# ISBN 提取正则
ISBN_PATTERN = re.compile(r"books/(\d{10,13})/")


class MacmillanCrawler(GoogleBooksCrawler):
    """
    Macmillan 出版社爬虫

    策略：
    1. 通过 Google Books API 查询 Macmillan 旗下多个印记的新书
    2. 通过 Macmillan sitemap 获取 ISBN 列表，用 Google Books 补充查询
    3. 两路结果合并去重，严格过滤出版年份
    """

    PUBLISHER_NAME = "麦克米伦"
    PUBLISHER_NAME_EN = "Macmillan"
    PUBLISHER_WEBSITE = "https://us.macmillan.com"
    CRAWLER_CLASS_NAME = "MacmillanCrawler"

    CATEGORY_MAP = {
        "fiction": "小说",
        "nonfiction": "非虚构",
        "mystery": "悬疑",
        "romance": "言情",
        "thriller": "惊悚",
        "science_fiction": "科幻",
        "fantasy": "奇幻",
        "biography": "传记",
        "history": "历史",
        "children": "儿童读物",
        "young_adult": "青少年",
        "science": "科学",
        "business": "商业",
        "graphic_novels": "图像小说",
    }

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 0.8

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {"id": "fiction", "name": "小说"},
            {"id": "nonfiction", "name": "非虚构"},
            {"id": "mystery", "name": "悬疑"},
            {"id": "romance", "name": "言情"},
            {"id": "thriller", "name": "惊悚"},
            {"id": "science_fiction", "name": "科幻"},
            {"id": "fantasy", "name": "奇幻"},
            {"id": "biography", "name": "传记"},
            {"id": "history", "name": "历史"},
            {"id": "children", "name": "儿童读物"},
            {"id": "young_adult", "name": "青少年"},
            {"id": "science", "name": "科学"},
            {"id": "business", "name": "商业"},
            {"id": "graphic_novels", "name": "图像小说"},
        ]

    # ------------------------------------------------------------------ #
    #  路径一：Google Books 多印记查询
    # ------------------------------------------------------------------ #

    def _query_imprint(
        self,
        imprint: str,
        min_year: int,
        max_results: int,
    ) -> Generator[BookInfo, None, None]:
        """
        用 inpublisher: 查询某个印记的新书

        Args:
            imprint: 印记名称（如 "St. Martin's Press"）
            min_year: 最早出版年份
            max_results: 最大返回数
        """
        self._validate_api_key()
        collected = 0
        start_index = 0
        max_pages = 3

        for _ in range(max_pages):
            if collected >= max_results:
                break

            params = {
                "q": f'inpublisher:"{imprint}"',
                "maxResults": min(max_results - collected, 40),
                "startIndex": start_index,
                "printType": "books",
                "langRestrict": "en",
                "orderBy": "newest",
            }
            if self._key_is_valid and self._api_key:
                params["key"] = self._api_key

            try:
                resp = self._session.get(
                    self.BASE_URL, params=params, timeout=self.config.timeout,
                )

                if resp.status_code == 400 and self._key_is_valid:
                    self._key_is_valid = False
                    params.pop("key", None)
                    resp = self._session.get(
                        self.BASE_URL, params=params, timeout=self.config.timeout,
                    )

                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.debug("印记 %s 查询失败: %s", imprint, exc)
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                if collected >= max_results:
                    break
                volume_info = item.get("volumeInfo", {})
                published_date = volume_info.get("publishedDate", "")

                if not self._is_recent_book(published_date, min_year):
                    continue

                book = self._parse_volume_info(volume_info, "general")
                if book:
                    collected += 1
                    yield book

            total = data.get("totalItems", 0)
            start_index += len(items)
            if start_index >= total:
                break

    # ------------------------------------------------------------------ #
    #  路径二：Sitemap ISBN 补充查询
    # ------------------------------------------------------------------ #

    def _fetch_sitemap_isbns(self) -> list[str]:
        """
        从 Macmillan 产品 sitemap 获取 ISBN 列表

        sitemap 不受 Cloudflare 限制，可正常访问。
        随机采样多个 sitemap 以获得多样化结果。
        """
        # 随机选取 sitemap 编号
        sample_ids = random.sample(
            list(SITEMAP_RANGE),
            min(SITEMAP_SAMPLE_SIZE, len(SITEMAP_RANGE)),
        )
        sample_ids.sort()

        all_isbns: list[str] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        for n in sample_ids:
            url = SITEMAP_BASE.format(n=n)
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    continue
                raw = gzip.decompress(resp.content)
                text = raw.decode("utf-8", errors="replace")
                found = ISBN_PATTERN.findall(text)
                all_isbns.extend(found)
                logger.debug("Sitemap %d: 找到 %d 个 ISBN", n, len(found))
            except Exception as exc:
                logger.warning("Sitemap %d 获取失败: %s", n, exc)

        # 去重后打乱顺序，避免总是查同样的前几条
        seen: set[str] = set()
        unique: list[str] = []
        for isbn in all_isbns:
            if isbn not in seen:
                seen.add(isbn)
                unique.append(isbn)

        random.shuffle(unique)
        logger.info("Sitemap 共获取 %d 个唯一 ISBN", len(unique))
        return unique

    def _lookup_isbn(self, isbn: str) -> BookInfo | None:
        """
        通过 Google Books ISBN 查询获取图书详情

        注意：使用 self._session.get() 直接请求，不经过 _make_request() 的
        robots.txt 检查（因为 Google Books API 的 robots.txt 会阻止通用 User-Agent）。

        Args:
            isbn: ISBN-13 编号

        Returns:
            BookInfo 或 None
        """
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {"q": f"isbn:{isbn}"}
        if self._key_is_valid and self._api_key:
            params["key"] = self._api_key

        try:
            resp = self._session.get(url, params=params, timeout=self.config.timeout)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                return None

            info = items[0].get("volumeInfo", {})
            sale = items[0].get("saleInfo", {})
            identifiers = info.get("industryIdentifiers", [])

            isbn13 = ""
            isbn10 = ""
            for ident in identifiers:
                if ident.get("type") == "ISBN_13":
                    isbn13 = ident.get("identifier", "")
                elif ident.get("type") == "ISBN_10":
                    isbn10 = ident.get("identifier", "")

            buy_links = {}
            if sale.get("buyLink"):
                buy_links["Google Play"] = sale["buyLink"]

            # 将 publishedDate 字符串转为 date 对象（与 BookInfo 类型一致）
            pub_date = self._parse_date_string(info.get("publishedDate", ""))

            return BookInfo(
                title=info.get("title", ""),
                author=", ".join(info.get("authors", [])),
                isbn13=isbn13,
                isbn10=isbn10,
                description=self._truncate_description(info.get("description", "")),
                cover_url=info.get("imageLinks", {}).get("thumbnail", ""),
                category=", ".join(info.get("categories", [])),
                publication_date=pub_date,
                price=None,
                page_count=info.get("pageCount"),
                language=info.get("language", "en"),
                buy_links=buy_links,
                source_url=info.get("infoLink", ""),
            )
        except Exception as exc:
            logger.debug("ISBN %s 查询失败: %s", isbn, exc)
            return None

    @staticmethod
    def _parse_date_string(date_str: str) -> date | None:
        """将 Google Books 返回的日期字符串转为 date 对象"""
        if not date_str:
            return None
        try:
            if len(date_str) >= 10:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            if len(date_str) >= 4:
                return datetime.strptime(date_str[:4], "%Y").date()
        except ValueError:
            pass
        return None

    @staticmethod
    def _is_book_recent(book: BookInfo, min_year: int) -> bool:
        """检查 BookInfo 的出版年份是否 >= min_year"""
        if not book.publication_date:
            return True  # 无日期信息，默认放行
        return book.publication_date.year >= min_year

    # ------------------------------------------------------------------ #
    #  主入口：两路合并
    # ------------------------------------------------------------------ #

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
        year_from: int | None = None,
    ) -> Generator[BookInfo, None, None]:
        """
        获取 Macmillan 新书列表

        两路合并：
        1. Google Books 多印记 inpublisher 查询（主要）
        2. Sitemap ISBN → Google Books ISBN 查询（补充）

        Args:
            category: 分类（未使用，保持接口兼容）
            max_books: 最大返回数量
            year_from: 最早出版年份（默认近2年）
        """
        current_year = datetime.now().year
        min_year = year_from or (current_year - 2)

        logger.info(
            "正在获取 %s 的新书（多印记查询 + Sitemap 补充，年份 >= %d）...",
            self.PUBLISHER_NAME_EN,
            min_year,
        )

        seen_isbns: set[str] = set()
        count = 0

        # ── 第一路：Google Books 多印记查询 ──
        per_imprint_limit = max(max_books // len(MACMILLAN_IMPRINTS), 5)

        for imprint in MACMILLAN_IMPRINTS:
            if count >= max_books:
                break

            for book in self._query_imprint(imprint, min_year, per_imprint_limit):
                if count >= max_books:
                    break
                isbn_key = book.isbn13 or book.isbn10 or book.title
                if isbn_key not in seen_isbns:
                    seen_isbns.add(isbn_key)
                    count += 1
                    yield book

        logger.info(
            "Google Books 多印记查询返回 %d 本，开始 Sitemap 补充...",
            count,
        )

        # ── 第二路：Sitemap ISBN 补充（仅在还有余量时执行） ──
        if count < max_books:
            sitemap_isbns = self._fetch_sitemap_isbns()
            checked = 0
            added = 0
            check_limit = (max_books - count) * 5

            for isbn in sitemap_isbns:
                if count >= max_books or checked >= check_limit:
                    break
                if isbn in seen_isbns:
                    continue

                checked += 1
                book = self._lookup_isbn(isbn)
                if not book:
                    continue

                # 年份过滤（修复：使用 min_year 而非 year_from）
                if not self._is_book_recent(book, min_year):
                    continue

                isbn_key = book.isbn13 or isbn
                if isbn_key not in seen_isbns:
                    seen_isbns.add(isbn_key)
                    count += 1
                    added += 1
                    yield book

                import time
                time.sleep(self.config.request_delay)

            logger.info(
                "Sitemap 补充检查 %d 个 ISBN，新增 %d 本",
                checked,
                added,
            )

        logger.info("Macmillan 共返回 %d 本新书", count)
