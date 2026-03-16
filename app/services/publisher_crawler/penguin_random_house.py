"""
Penguin Random House（企鹅兰登）出版社爬虫

企鹅兰登是世界上最大的大众图书出版商之一，
网站提供新书发布信息、作者介绍和书籍详情。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

网站特点：
- 新书页面结构清晰
- 提供丰富的书籍元数据
- 支持分类浏览
"""
import asyncio
import logging
from typing import Any, Generator, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class PenguinRandomHouseCrawler(BaseCrawler):
    """
    Penguin Random House 出版社爬虫

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

    官方网站：https://www.penguinrandomhouse.com/
    新书页面：https://www.penguinrandomhouse.com/books/new-releases/
    """

    PUBLISHER_NAME = "企鹅兰登"
    PUBLISHER_NAME_EN = "Penguin Random House"
    PUBLISHER_WEBSITE = "https://www.penguinrandomhouse.com"
    CRAWLER_CLASS_NAME = "PenguinRandomHouseCrawler"

    # 新书页面URL模板
    NEW_RELEASES_URL = "https://www.penguinrandomhouse.com/books/new-releases/"
    BOOK_DETAIL_URL = "https://www.penguinrandomhouse.com/books/{book_id}/"

    # 分类映射
    CATEGORY_MAP = {
        'fiction': '小说',
        'non-fiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'science-fiction': '科幻',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young-adult': '青少年',
        'graphic-novels': '图像小说',
    }

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        # Penguin Random House 请求间隔稍长，避免被限流
        if config is None:
            self.config.request_delay = 1.5
        self._crawl4ai_available = self._check_crawl4ai()

    def _check_crawl4ai(self) -> bool:
        """检查 Crawl4AI 是否可用"""
        try:
            import crawl4ai
            logger.info(f"✅ PenguinRandomHouse: Crawl4AI 可用")
            return True
        except ImportError:
            logger.info(f"ℹ️ PenguinRandomHouse: Crawl4AI 未安装，仅使用传统 requests")
            return False

    async def _crawl_with_crawl4ai_async(self, url: str) -> Optional[str]:
        """使用 Crawl4AI 异步爬取网页"""
        if not self._crawl4ai_available:
            return None

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

            logger.info(f"🕸️ PenguinRandomHouse: 使用 Crawl4AI 爬取: {url}")

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
                    logger.info(f"✅ PenguinRandomHouse: Crawl4AI 爬取成功")
                    return result.html
            return None
        except Exception as e:
            logger.warning(f"⚠️ PenguinRandomHouse: Crawl4AI 出错: {e}")
            return None

    def _crawl_with_crawl4ai(self, url: str) -> Optional[str]:
        """同步使用 Crawl4AI 爬取"""
        try:
            return asyncio.run(self._crawl_with_crawl4ai_async(url))
        except Exception as e:
            logger.warning(f"⚠️ PenguinRandomHouse: Crawl4AI 同步调用失败: {e}")
            return None

    def _make_request_with_fallback(self, url: str) -> tuple[Optional[BeautifulSoup], Optional[str]]:
        """
        带降级的请求方法

        先尝试传统 requests，失败后用 Crawl4AI
        返回 (soup, source)，source 是 'requests' 或 'crawl4ai'
        """
        # 先尝试传统 requests
        logger.info(f"🔄 PenguinRandomHouse: 尝试传统 requests: {url}")
        response = self._make_request(url)

        if response:
            logger.info(f"✅ PenguinRandomHouse: 传统 requests 成功")
            return self._parse_html(response.text), 'requests'

        # 失败后尝试 Crawl4AI
        if self._crawl4ai_available:
            logger.info(f"🔄 PenguinRandomHouse: 降级到 Crawl4AI")
            html = self._crawl_with_crawl4ai(url)

            if html:
                logger.info(f"✅ PenguinRandomHouse: Crawl4AI 成功")
                return BeautifulSoup(html, 'html.parser'), 'crawl4ai'

        logger.warning(f"❌ PenguinRandomHouse: 所有方法都失败: {url}")
        return None, None

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'non-fiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'science-fiction', 'name': '科幻'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young-adult', 'name': '青少年'},
            {'id': 'graphic-novels', 'name': '图像小说'},
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
            # 构建URL
            url = self._build_list_url(category, page)

            logger.info(f"📄 正在爬取第 {page} 页: {url}")

            soup, source = self._make_request_with_fallback(url)
            if not soup:
                logger.warning(f"⚠️ 无法获取页面内容，停止爬取")
                break

            logger.info(f"✅ 使用 {source} 获取页面成功")

            # 解析书籍列表
            books_on_page = self._parse_book_list(soup)

            if not books_on_page:
                logger.info(f"📖 第 {page} 页没有更多书籍")
                break

            for book_data in books_on_page:
                if count >= max_books:
                    break

                # 获取详细信息
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
        """
        解析书籍列表页

        Penguin Random House 的书籍列表通常包含：
        - 书名和作者
        - 封面图片
        - 详情链接

        Args:
            soup: BeautifulSoup 对象

        Returns:
            书籍数据列表
        """
        books = []

        # 查找书籍容器（根据实际网站结构调整选择器）
        # Penguin Random House 使用 .item 类
        book_items = soup.select('.carousel .item')

        if not book_items:
            # 备用选择器
            book_items = soup.select('.book-item, .product-item, [data-book-id], .book-card')

        if not book_items:
            book_items = soup.select('article.book, li.book, div.book')

        for item in book_items:
            try:
                book_data = {}

                # 提取详情链接 - Penguin Random House 使用 .img a 或 .title a
                link = item.select_one('.img a, .title a, a[href*="/books/"]')
                if link:
                    href = link.get('href', '')
                    book_data['url'] = urljoin(self.PUBLISHER_WEBSITE, href)

                # 提取书名
                title_elem = item.select_one('.title a, .title, .book-title, .title, h2, h3')
                if title_elem:
                    book_data['title'] = self._clean_text(title_elem.get_text())

                # 提取作者
                author_elem = item.select_one('.contributor a, .contributor, .author, .book-author')
                if author_elem:
                    book_data['author'] = self._clean_text(author_elem.get_text())

                # 提取封面URL
                img_elem = item.select_one('img')
                if img_elem:
                    src = img_elem.get('src') or img_elem.get('data-src')
                    if src:
                        book_data['cover_url'] = src

                if book_data.get('url') and book_data.get('title'):
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
            # 提取书籍信息
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

            # 提取 ISBN
            isbn_text = self._extract_isbn_text(soup)
            if isbn_text:
                book_info.isbn13, book_info.isbn10 = self._extract_isbn(isbn_text)

            # 截断简介
            book_info.description = self._truncate_description(book_info.description)

            return book_info

        except Exception as e:
            logger.error(f"❌ 解析书籍详情失败 {book_url}: {e}")
            return None

    def _extract_title(self, soup) -> str:
        """提取书名"""
        selectors = [
            'h1.book-title',
            'h1.product-title',
            '.book-info h1',
            'h1',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = self._clean_text(elem.get_text())
                if text and len(text) < 200:
                    return text
        return "Unknown Title"

    def _extract_author(self, soup) -> str:
        """提取作者"""
        selectors = [
            '.book-info .contributor a',
            '.contributor a[href*="/authors/"]',
            '.author-name',
            '.book-author',
            '.contributor-name',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = self._clean_text(elem.get_text())
                if text and len(text) < 100:
                    return text
        return "Unknown Author"

    def _extract_description(self, soup) -> str | None:
        """提取简介"""
        selectors = [
            '.book-description',
            '.product-description',
            '.synopsis',
            '.summary',
            '[data-description]',
            '.description',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return None

    def _extract_cover_url(self, soup) -> str | None:
        """提取封面URL"""
        # 查找封面图片
        img_selectors = [
            '.book-cover img',
            '.product-image img',
            '.cover-image img',
            'img.book-image',
            'img[alt*="cover"]',
        ]
        for selector in img_selectors:
            img = soup.select_one(selector)
            if img:
                src = img.get('src') or img.get('data-src')
                if src:
                    return urljoin(self.PUBLISHER_WEBSITE, src)
        return None

    def _extract_category(self, soup) -> str | None:
        """提取分类"""
        selectors = [
            '.book-category',
            '.genre',
            '.category',
            '[data-category]',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                category_en = self._clean_text(elem.get_text()).lower()
                return self.CATEGORY_MAP.get(category_en, category_en)
        return None

    def _extract_publication_date(self, soup) -> Any:
        """提取出版日期"""
        selectors = [
            '.publication-date',
            '.release-date',
            '.publish-date',
            '[data-publish-date]',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                date_text = self._clean_text(elem.get_text())
                return self._parse_date(date_text)

        # 尝试从页面文本中查找
        page_text = soup.get_text()
        date_match = None
        import re
        # 查找 "On Sale: [Date]" 或 "Publication Date: [Date]" 模式
        patterns = [
            r'(?:On Sale|Publication Date|Publish Date|Release Date)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:On Sale|Publication Date|Publish Date|Release Date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return self._parse_date(match.group(1))

        return None

    def _extract_price(self, soup) -> str | None:
        """提取价格"""
        selectors = [
            '.price',
            '.book-price',
            '.product-price',
            '[data-price]',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._parse_price(elem.get_text())
        return None

    def _extract_page_count(self, soup) -> int | None:
        """提取页数"""
        selectors = [
            '.page-count',
            '.pages',
            '[data-pages]',
        ]
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
        # 查找ISBN标签
        selectors = [
            '.isbn',
            '.book-isbn',
            '[data-isbn]',
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text()

        # 从页面文本中查找
        page_text = soup.get_text()
        import re
        match = re.search(r'ISBN[-:\s]*(97[89]\d{10}|\d{9}[\dXx])', page_text, re.IGNORECASE)
        if match:
            return match.group(0)

        return None

    def _extract_buy_links(self, soup) -> list[dict[str, str]]:
        """提取购买链接"""
        links = []

        # 常见零售商
        retailers = {
            'Amazon': 'amazon.com',
            'Barnes & Noble': 'bn.com',
            'Books-A-Million': 'booksamillion.com',
            'Bookshop': 'bookshop.org',
            'IndieBound': 'indiebound.org',
        }

        # 查找购买按钮/链接
        buy_section = soup.select_one('.buy-buttons, .purchase-options, .buy-links')
        if buy_section:
            for link in buy_section.find_all('a', href=True):
                href = link.get('href', '')
                text = self._clean_text(link.get_text())

                # 匹配零售商
                for name, domain in retailers.items():
                    if domain in href:
                        links.append({
                            'name': name,
                            'url': href
                        })
                        break

        return links
