"""
Simon & Schuster（西蒙舒斯特）出版社爬虫

西蒙舒斯特是美国主要出版商之一，
以出版畅销小说、非虚构作品和儿童读物闻名。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

网站特点：
- 新书页面按月份组织
- 提供详细的书籍信息
- 支持多种分类浏览
"""
import asyncio
import logging
from typing import Any, Generator, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class SimonSchusterCrawler(BaseCrawler):
    """
    Simon & Schuster 出版社爬虫

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

    官方网站：https://www.simonandschuster.com/
    新书页面：https://www.simonandschuster.com/books/new-releases
    """

    PUBLISHER_NAME = "西蒙舒斯特"
    PUBLISHER_NAME_EN = "Simon & Schuster"
    PUBLISHER_WEBSITE = "https://www.simonandschuster.com"
    CRAWLER_CLASS_NAME = "SimonSchusterCrawler"

    # 新书页面URL
    NEW_RELEASES_URL = "https://www.simonandschuster.com/books/new-releases"

    # 分类映射
    CATEGORY_MAP = {
        'fiction': '小说',
        'nonfiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'thriller': '惊悚',
        'biography': '传记',
        'history': '历史',
        'self-help': '自助',
        'children': '儿童读物',
        'young-adult': '青少年',
    }

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.2
        self._crawl4ai_available = self._check_crawl4ai()

    def _check_crawl4ai(self) -> bool:
        """检查 Crawl4AI 是否可用"""
        try:
            import crawl4ai
            logger.info(f"✅ SimonSchuster: Crawl4AI 可用")
            return True
        except ImportError:
            logger.info(f"ℹ️ SimonSchuster: Crawl4AI 未安装，仅使用传统 requests")
            return False

    async def _crawl_with_crawl4ai_async(self, url: str) -> Optional[str]:
        """使用 Crawl4AI 异步爬取网页"""
        if not self._crawl4ai_available:
            return None

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

            logger.info(f"🕸️ SimonSchuster: 使用 Crawl4AI 爬取: {url}")

            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
            )

            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                timeout=30000,
                word_count_threshold=1,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                if result and result.success and result.html:
                    logger.info(f"✅ SimonSchuster: Crawl4AI 爬取成功")
                    return result.html
            return None
        except Exception as e:
            logger.warning(f"⚠️ SimonSchuster: Crawl4AI 出错: {e}")
            return None

    def _crawl_with_crawl4ai(self, url: str) -> Optional[str]:
        """同步使用 Crawl4AI 爬取"""
        try:
            return asyncio.run(self._crawl_with_crawl4ai_async(url))
        except Exception as e:
            logger.warning(f"⚠️ SimonSchuster: Crawl4AI 同步调用失败: {e}")
            return None

    def _make_request_with_fallback(self, url: str) -> tuple[Optional[BeautifulSoup], Optional[str]]:
        """
        带降级的请求方法

        先尝试传统 requests，失败后用 Crawl4AI
        返回 (soup, source)，source 是 'requests' 或 'crawl4ai'
        """
        logger.info(f"🔄 SimonSchuster: 尝试传统 requests: {url}")
        response = self._make_request(url)

        if response:
            logger.info(f"✅ SimonSchuster: 传统 requests 成功")
            return self._parse_html(response.text), 'requests'

        if self._crawl4ai_available:
            logger.info(f"🔄 SimonSchuster: 降级到 Crawl4AI")
            html = self._crawl_with_crawl4ai(url)

            if html:
                logger.info(f"✅ SimonSchuster: Crawl4AI 成功")
                return BeautifulSoup(html, 'html.parser'), 'crawl4ai'

        logger.warning(f"❌ SimonSchuster: 所有方法都失败: {url}")
        return None, None

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'nonfiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'thriller', 'name': '惊悚'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'self-help', 'name': '自助'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young-adult', 'name': '青少年'},
        ]

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100
    ) -> Generator[BookInfo, None, None]:
        """
        获取新书列表（混合架构）

        先尝试传统 requests，失败后用 Crawl4AI 降级

        Args:
            category: 分类ID
            max_books: 最大获取数量

        Yields:
            BookInfo 对象
        """
        page = 1
        count = 0

        while count < max_books and page <= self.config.max_pages:
            url = self._build_list_url(category, page)
            logger.info(f"📄 正在爬取第 {page} 页: {url}")

            soup, source = self._make_request_with_fallback(url)
            if not soup:
                logger.warning(f"⚠️ 无法获取页面内容，停止爬取")
                break

            logger.info(f"✅ 使用 {source} 获取页面成功")

            books_on_page = self._parse_book_list(soup)

            if not books_on_page:
                logger.info(f"📖 第 {page} 页没有更多书籍")
                break

            for book_data in books_on_page:
                if count >= max_books:
                    break

                book_info = self.get_book_details(book_data['url'])
                if book_info:
                    yield book_info
                    count += 1

            page += 1

    def _build_list_url(self, category: str | None, page: int) -> str:
        """构建列表页URL"""
        params = []

        if category:
            params.append(f"category={category}")

        if page > 1:
            params.append(f"page={page}")

        if params:
            return f"{self.NEW_RELEASES_URL}?{'&'.join(params)}"
        return self.NEW_RELEASES_URL

    def _parse_book_list(self, soup) -> list[dict[str, str]]:
        """解析书籍列表页"""
        books = []

        # Simon & Schuster 书籍列表选择器
        book_items = soup.select('.book-item, .product-tile, [data-product-id], .book-card')

        if not book_items:
            book_items = soup.select('article, li.book, div.book')

        for item in book_items:
            try:
                book_data = {}

                # 提取详情链接
                link = item.select_one('a[href*="/books/"]')
                if link:
                    href = link.get('href', '')
                    book_data['url'] = urljoin(self.PUBLISHER_WEBSITE, href)

                # 提取书名
                title_elem = item.select_one('.title, .book-title, h2, h3')
                if title_elem:
                    book_data['title'] = self._clean_text(title_elem.get_text())

                # 提取作者
                author_elem = item.select_one('.author, .book-author')
                if author_elem:
                    book_data['author'] = self._clean_text(author_elem.get_text())

                if book_data.get('url'):
                    books.append(book_data)

            except Exception as e:
                logger.warning(f"⚠️ 解析书籍项失败: {e}")
                continue

        logger.info(f"📖 在当前页面找到 {len(books)} 本书籍")
        return books

    def get_book_details(self, book_url: str) -> BookInfo | None:
        """
        获取书籍详情（混合架构）

        先尝试传统 requests，失败后用 Crawl4AI 降级

        Args:
            book_url: 书籍详情页URL

        Returns:
            BookInfo 对象或 None
        """
        soup, source = self._make_request_with_fallback(book_url)
        if not soup:
            return None

        logger.info(f"✅ 使用 {source} 获取书籍详情成功")

        try:
            book_info = BookInfo(
                title=self._extract_title(soup),
                author=self._extract_author(soup),
                isbn13=None,
                isbn10=None,
                description=self._extract_description(soup),
                cover_url=self._extract_cover_url(soup),
                category=self._extract_category(soup),
                publication_date=self._extract_publication_date(soup),
                price=self._extract_price(soup),
                page_count=self._extract_page_count(soup),
                language='English',
                buy_links=self._extract_buy_links(soup),
                source_url=book_url,
            )

            isbn_text = self._extract_isbn_text(soup)
            if isbn_text:
                book_info.isbn13, book_info.isbn10 = self._extract_isbn(isbn_text)

            book_info.description = self._truncate_description(book_info.description)

            return book_info

        except Exception as e:
            logger.error(f"❌ 解析书籍详情失败 {book_url}: {e}")
            return None

    def _extract_title(self, soup) -> str:
        """提取书名"""
        selectors = ['.book-title', '.product-title', 'h1.title', 'h1']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return "Unknown Title"

    def _extract_author(self, soup) -> str:
        """提取作者"""
        selectors = ['.author-name', '.book-author', '.contributor', '.author a']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return "Unknown Author"

    def _extract_description(self, soup) -> str | None:
        """提取简介"""
        selectors = ['.book-description', '.product-description', '.synopsis', '.description']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return None

    def _extract_cover_url(self, soup) -> str | None:
        """提取封面URL"""
        img_selectors = ['.book-cover img', '.product-image img', '.cover img', 'img.book-image']
        for selector in img_selectors:
            img = soup.select_one(selector)
            if img:
                src = img.get('src') or img.get('data-src')
                if src:
                    return urljoin(self.PUBLISHER_WEBSITE, src)
        return None

    def _extract_category(self, soup) -> str | None:
        """提取分类"""
        selectors = ['.category', '.genre', '.book-category']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                category_en = self._clean_text(elem.get_text()).lower()
                return self.CATEGORY_MAP.get(category_en, category_en)
        return None

    def _extract_publication_date(self, soup) -> Any:
        """提取出版日期"""
        selectors = ['.publication-date', '.release-date', '.publish-date']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                date_text = self._clean_text(elem.get_text())
                return self._parse_date(date_text)

        # 从页面文本查找
        page_text = soup.get_text()
        import re
        patterns = [
            r'(?:On Sale|Publication Date|Release Date)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:On Sale|Publication Date|Release Date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return self._parse_date(match.group(1))

        return None

    def _extract_price(self, soup) -> str | None:
        """提取价格"""
        selectors = ['.price', '.book-price', '.product-price']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._parse_price(elem.get_text())
        return None

    def _extract_page_count(self, soup) -> int | None:
        """提取页数"""
        selectors = ['.page-count', '.pages']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text()
                import re
                match = re.search(r'(\d+)', text)
                if match:
                    return int(match.group(1))
        return None

    def _extract_isbn_text(self, soup) -> str | None:
        """提取包含ISBN的文本"""
        selectors = ['.isbn', '.book-isbn', '[data-isbn]']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text()

        page_text = soup.get_text()
        import re
        match = re.search(r'ISBN[-:\s]*(97[89]\d{10}|\d{9}[\dXx])', page_text, re.IGNORECASE)
        if match:
            return match.group(0)

        return None

    def _extract_buy_links(self, soup) -> list[dict[str, str]]:
        """提取购买链接"""
        links = []

        retailers = {
            'Amazon': 'amazon.com',
            'Barnes & Noble': 'bn.com',
            'Books-A-Million': 'booksamillion.com',
            'Apple Books': 'apple.com',
            'Google Play': 'play.google.com',
        }

        buy_section = soup.select_one('.buy-buttons, .purchase-options, .retailers')
        if buy_section:
            for link in buy_section.find_all('a', href=True):
                href = link.get('href', '')
                text = self._clean_text(link.get_text())

                for name, domain in retailers.items():
                    if domain in href:
                        links.append({'name': name, 'url': href})
                        break

        return links
