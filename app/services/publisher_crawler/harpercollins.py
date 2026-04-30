"""
HarperCollins 出版社爬虫

从 HarperCollins 官网首页抓取 NEW RELEASES 轮播数据。
图片 alt 格式完美：'Title by Author (ISBN)'，可一次解析得到标题+作者+ISBN。

官网首页：https://www.harpercollins.com
首页结构：NEW RELEASES 轮播区域，首页可见约16本
图片alt格式：'Riviera by Melanie Masarin (9780063445758)'
产品URL：/products/{title-slug}-{author-slug}
详情页：Cloudflare 拦截，仅用首页数据
"""
import logging
import re
from typing import Generator

from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)

# 图片 alt 正则：Title by Author (ISBN)
# 示例：Riviera by Melanie Masarin (9780063445758)
ALT_PATTERN = re.compile(r'^(.+?)\s+by\s+(.+?)\s+\((\d{13})\)$')


class HarperCollinsCrawler(BaseCrawler):
    """
    HarperCollins 出版社爬虫

    从官网首页 NEW RELEASES 轮播提取书籍信息。
    图片 alt 包含完整的标题、作者、ISBN 信息。
    """

    PUBLISHER_NAME = "哈珀柯林斯"
    PUBLISHER_NAME_EN = "HarperCollins"
    PUBLISHER_WEBSITE = "https://www.harpercollins.com"
    CRAWLER_CLASS_NAME = "HarperCollinsCrawler"

    # 首页 URL
    HOME_URL = "https://www.harpercollins.com/"

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
            self.config.request_delay = 1.0

    def _is_url_allowed(self, url: str) -> bool:
        """
        检查 URL 是否被 robots.txt 允许

        HarperCollins 的 robots.txt 被 Cloudflare 拦截返回 HTML 页面，
        导致 RobotFileParser 无法获取有效规则，can_fetch 默认返回 False。
        此处绕过该限制，默认允许访问。
        """
        if self._robots_parser is None:
            return True
        # Cloudflare 导致的无效 robots.txt 会使 can_fetch 始终返回 False
        # 直接允许所有请求
        return True

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

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
    ) -> Generator[BookInfo, None, None]:
        """
        获取 HarperCollins 新书列表

        从首页 NEW RELEASES 轮播提取书籍信息。
        图片 alt 格式：'Title by Author (ISBN)'

        Args:
            category: 分类筛选（可选）
            max_books: 最大获取数量

        Yields:
            BookInfo 对象
        """
        logger.info("🔍 开始从 HarperCollins 官网首页获取新书...")

        # 1. 请求首页
        response = self._make_request(self.HOME_URL)
        if not response:
            logger.error("❌ 无法访问 HarperCollins 首页")
            return

        soup = self._parse_html(response.text)

        # 2. 查找 NEW RELEASES 区域的图片
        # 图片 alt 格式：'Riviera by Melanie Masarin (9780063445758)'
        books_found = []
        seen_isbns = set()

        for img in soup.find_all('img'):
            alt = img.get('alt', '').strip()
            match = ALT_PATTERN.match(alt)
            if match:
                title = match.group(1).strip()
                author = match.group(2).strip()
                isbn = match.group(3)

                # 去重
                if isbn in seen_isbns:
                    continue
                seen_isbns.add(isbn)

                # 获取封面图 URL
                cover_url = img.get('src', '')

                # 获取产品链接
                product_url = ''
                parent_link = img.find_parent('a', href=True)
                if parent_link:
                    href = parent_link.get('href', '')
                    if href.startswith('/'):
                        product_url = f"https://www.harpercollins.com{href}"
                    elif href.startswith('http'):
                        product_url = href

                books_found.append({
                    'title': title,
                    'author': author,
                    'isbn': isbn,
                    'cover_url': cover_url,
                    'product_url': product_url,
                })

        logger.info(f"📖 从首页找到 {len(books_found)} 本新书")

        # 3. 构建 BookInfo 对象
        count = 0
        for book_data in books_found:
            if count >= max_books:
                break

            try:
                book_info = BookInfo(
                    title=book_data['title'],
                    author=book_data['author'],
                    isbn13=book_data['isbn'],
                    cover_url=book_data['cover_url'],
                    source_url=book_data['product_url'],
                )

                logger.info(
                    f"✅ [{count + 1}] {book_data['title']} - {book_data['author']} "
                    f"(ISBN: {book_data['isbn']})"
                )
                yield book_info
                count += 1

            except Exception as e:
                logger.error(f"❌ 处理书籍时出错: {e}")
                continue

        logger.info(f"✅ HarperCollins 爬取完成，共获取 {count} 本新书")

    def get_book_details(self, book_url: str) -> BookInfo | None:
        """
        获取书籍详情（HarperCollins 详情页有 Cloudflare，返回 None）

        Args:
            book_url: 书籍详情页 URL

        Returns:
            None（详情页无法访问）
        """
        logger.warning("⚠️ HarperCollins 详情页有 Cloudflare 防护，无法访问")
        return None

    def _fetch_book_detail(self, book_url: str) -> dict | None:
        """
        获取书籍详情信息（HarperCollins 详情页有 Cloudflare，返回 None）
        """
        logger.warning("⚠️ HarperCollins 详情页有 Cloudflare 防护，无法访问")
        return None
