"""
出版社 RSS/Atom Feed 爬虫

通过解析出版社的 RSS/Atom Feed 获取新书信息。
RSS Feed 是结构化数据，比 HTML 爬取更稳定可靠。

支持的 Feed 格式:
- RSS 2.0
- Atom 1.0

用法:
    为每个出版社创建子类，配置 FEED_URLS 即可。
"""
import logging
import re
from datetime import datetime, date
from typing import Any, Generator
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class PublisherRSSCrawler(BaseCrawler):
    """
    出版社 RSS Feed 爬虫基类

    通过解析 RSS/Atom Feed 获取新书信息。
    子类需要配置:
    - PUBLISHER_NAME: 出版社中文名
    - PUBLISHER_NAME_EN: 出版社英文名
    - PUBLISHER_WEBSITE: 出版社官网
    - CRAWLER_CLASS_NAME: 爬虫类名
    - FEED_URLS: RSS Feed URL 列表
    """

    FEED_URLS: list[str] = []

    # 子类可覆盖：从 Feed 项中提取 ISBN 的正则
    ISBN_PATTERN = re.compile(r'(97[89]\d{10}|\d{9}[\dXx])')

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
    ) -> Generator[BookInfo, None, None]:
        """
        从 RSS Feed 获取新书

        Args:
            category: 未使用（保持接口兼容）
            max_books: 最大获取数量

        Yields:
            BookInfo 对象
        """
        if not self.FEED_URLS:
            logger.warning("%s: 未配置 RSS Feed URL", self.PUBLISHER_NAME_EN)
            return

        collected = 0
        seen_titles: set[str] = set()

        for feed_url in self.FEED_URLS:
            if collected >= max_books:
                break

            logger.info("正在解析 RSS Feed: %s", feed_url)

            try:
                response = self._make_request(feed_url)
                if not response:
                    logger.warning("无法获取 RSS Feed: %s", feed_url)
                    continue

                items = self._parse_feed(response.text)

                for item in items:
                    if collected >= max_books:
                        break

                    title = item.get("title", "").strip()
                    if not title or title.lower() in seen_titles:
                        continue
                    seen_titles.add(title.lower())

                    book_info = self._item_to_book_info(item)
                    if book_info:
                        yield book_info
                        collected += 1

            except Exception as e:
                logger.error("解析 RSS Feed 失败 %s: %s", feed_url, e)
                continue

        if collected == 0:
            logger.warning("%s: RSS Feed 未获取到新书", self.PUBLISHER_NAME_EN)
        else:
            logger.info("%s: 从 RSS Feed 获取 %d 本新书", self.PUBLISHER_NAME_EN, collected)

    def _parse_feed(self, xml_text: str) -> list[dict[str, Any]]:
        """解析 RSS/Atom Feed XML"""
        items = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("XML 解析失败: %s", e)
            return items

        # 检测 Feed 类型并解析
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'content': 'http://purl.org/rss/1.0/modules/content/',
        }

        # RSS 2.0 格式
        channel = root.find('channel')
        if channel is not None:
            for item_elem in channel.findall('item'):
                item = self._parse_rss_item(item_elem, ns)
                if item:
                    items.append(item)
            return items

        # Atom 格式
        if root.tag == '{http://www.w3.org/2005/Atom}feed' or root.tag == 'feed':
            for entry in root.findall('atom:entry', ns) or root.findall('entry'):
                item = self._parse_atom_entry(entry, ns)
                if item:
                    items.append(item)
            return items

        # 尝试通用解析
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag in ('item', 'entry'):
                item = self._parse_generic_item(elem, ns)
                if item:
                    items.append(item)

        return items

    def _parse_rss_item(self, elem, ns: dict) -> dict[str, Any] | None:
        """解析 RSS 2.0 item 元素"""
        title = self._get_text(elem, 'title')
        if not title:
            return None

        return {
            'title': title,
            'link': self._get_text(elem, 'link') or '',
            'description': self._get_text(elem, 'description') or
                          self._get_text(elem, 'content:encoded', ns) or '',
            'pub_date': self._get_text(elem, 'pubDate') or
                       self._get_text(elem, 'dc:date', ns) or '',
            'author': self._get_text(elem, 'dc:creator', ns) or
                     self._get_text(elem, 'author') or '',
            'category': self._get_text(elem, 'category') or '',
            'guid': self._get_text(elem, 'guid') or '',
        }

    def _parse_atom_entry(self, elem, ns: dict) -> dict[str, Any] | None:
        """解析 Atom entry 元素"""
        title = self._get_text(elem, 'atom:title', ns) or self._get_text(elem, 'title')
        if not title:
            return None

        # Atom 的 link 是属性
        link = ''
        link_elem = elem.find('atom:link', ns) or elem.find('link')
        if link_elem is not None:
            link = link_elem.get('href', '')

        content = (self._get_text(elem, 'atom:content', ns) or
                   self._get_text(elem, 'atom:summary', ns) or
                   self._get_text(elem, 'content') or
                   self._get_text(elem, 'summary') or '')

        pub_date = (self._get_text(elem, 'atom:published', ns) or
                   self._get_text(elem, 'atom:updated', ns) or
                   self._get_text(elem, 'published') or
                   self._get_text(elem, 'updated') or '')

        author = ''
        author_elem = elem.find('atom:author', ns) or elem.find('author')
        if author_elem is not None:
            author = (self._get_text(author_elem, 'atom:name', ns) or
                     self._get_text(author_elem, 'name') or '')

        category = ''
        cat_elem = elem.find('atom:category', ns) or elem.find('category')
        if cat_elem is not None:
            category = cat_elem.get('term', '') or cat_elem.text or ''

        return {
            'title': title,
            'link': link,
            'description': content,
            'pub_date': pub_date,
            'author': author,
            'category': category,
            'guid': '',
        }

    def _parse_generic_item(self, elem, ns: dict) -> dict[str, Any] | None:
        """通用 XML 元素解析"""
        title = ''
        description = ''
        link = ''
        pub_date = ''
        author = ''
        category = ''

        for child in elem:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            text = (child.text or '').strip()

            if tag == 'title' and not title:
                title = text
            elif tag in ('description', 'summary', 'content'):
                description = text
            elif tag == 'link' and not link:
                link = child.get('href', '') or text
            elif tag in ('pubDate', 'published', 'updated', 'date'):
                pub_date = text
            elif tag in ('creator', 'author'):
                author = text
            elif tag == 'category':
                category = text

        if not title:
            return None

        return {
            'title': title,
            'link': link,
            'description': description,
            'pub_date': pub_date,
            'author': author,
            'category': category,
            'guid': '',
        }

    @staticmethod
    def _get_text(parent, tag: str, ns: dict | None = None) -> str | None:
        """安全获取 XML 元素文本"""
        elem = parent.find(tag, ns) if ns else parent.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    def _item_to_book_info(self, item: dict[str, Any]) -> BookInfo | None:
        """将 RSS item 转换为 BookInfo"""
        title = item.get("title", "").strip()
        if not title:
            return None

        # 清理 HTML 标签
        description = self._strip_html(item.get("description", ""))
        description = self._truncate_description(description)

        # 提取作者
        author = item.get("author", "").strip()
        if not author:
            author = self._extract_author_from_text(title, description)
        if not author:
            author = "Unknown Author"

        # 提取 ISBN
        isbn13, isbn10 = None, None
        full_text = f"{title} {description} {item.get('link', '')}"
        match = self.ISBN_PATTERN.search(full_text)
        if match:
            isbn_str = match.group(1)
            if len(isbn_str) == 13:
                isbn13 = isbn_str
            elif len(isbn_str) == 10:
                isbn10 = isbn_str

        # 解析日期
        publication_date = self._parse_rss_date(item.get("pub_date", ""))

        # 分类
        category = item.get("category", "")
        if category:
            category = self.CATEGORY_MAP.get(category.lower(), category)

        # 来源链接
        source_url = item.get("link", "") or item.get("guid", "")

        # 购买链接
        buy_links = []
        if source_url:
            buy_links.append({"name": self.PUBLISHER_NAME, "url": source_url})

        return BookInfo(
            title=title,
            author=author,
            isbn13=isbn13,
            isbn10=isbn10,
            description=description,
            cover_url=None,
            category=category,
            publication_date=publication_date,
            price=None,
            page_count=None,
            language="English",
            buy_links=buy_links,
            source_url=source_url,
        )

    @staticmethod
    def _strip_html(text: str) -> str:
        """移除 HTML 标签"""
        if not text:
            return ""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    @staticmethod
    def _extract_author_from_text(title: str, description: str) -> str:
        """从文本中提取作者名"""
        patterns = [
            r'(?:by|By|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            r'(?:author|Author)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            r'(?:written by|Written by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        ]
        text = f"{title} {description}"
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _parse_rss_date(date_str: str) -> date | None:
        """解析 RSS/Atom 日期格式"""
        if not date_str:
            return None

        formats = [
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S %Z',
            '%Y-%m-%d',
            '%d %b %Y',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.date()
            except ValueError:
                continue

        # 尝试提取年月日
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        return None

    def get_book_details(self, book_url: str) -> BookInfo | None:
        """获取书籍详情（RSS 爬虫不支持详情页爬取）"""
        return None


# ============================================================
# 各出版社 RSS 爬虫子类
# ============================================================

class PenguinRandomHouseRSSCrawler(PublisherRSSCrawler):
    """企鹅兰登书屋 RSS 爬虫"""

    PUBLISHER_NAME = "企鹅兰登"
    PUBLISHER_NAME_EN = "Penguin Random House"
    PUBLISHER_WEBSITE = "https://www.penguinrandomhouse.com"
    CRAWLER_CLASS_NAME = "PenguinRandomHouseRSSCrawler"

    # 企鹅兰登的部分子品牌有 RSS
    FEED_URLS = [
        "https://www.penguinrandomhouse.com/feeds/new-releases.rss",
        "https://www.penguin.co.uk/feeds/new-releases.xml",
    ]


class HarperCollinsRSSCrawler(PublisherRSSCrawler):
    """HarperCollins RSS 爬虫"""

    PUBLISHER_NAME = "哈珀柯林斯"
    PUBLISHER_NAME_EN = "HarperCollins"
    PUBLISHER_WEBSITE = "https://www.harpercollins.com"
    CRAWLER_CLASS_NAME = "HarperCollinsRSSCrawler"

    FEED_URLS = [
        "https://www.harpercollins.com/feeds/new-releases.rss",
    ]


class SimonSchusterRSSCrawler(PublisherRSSCrawler):
    """Simon & Schuster RSS 爬虫"""

    PUBLISHER_NAME = "西蒙舒斯特"
    PUBLISHER_NAME_EN = "Simon & Schuster"
    PUBLISHER_WEBSITE = "https://www.simonandschuster.com"
    CRAWLER_CLASS_NAME = "SimonSchusterRSSCrawler"

    FEED_URLS = [
        "https://www.simonandschuster.com/feeds/new-releases.rss",
    ]
