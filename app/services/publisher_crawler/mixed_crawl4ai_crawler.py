"""
混合架构爬虫基类（带Crawl4AI降级支持）

提供通用的Crawl4AI集成方法、数据提取方法和业务流程方法。
子类只需配置出版社特定的URL、分类映射和选择器。
"""
import asyncio
import logging
import re
from typing import Any, Generator, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class MixedCrawl4AICrawler(BaseCrawler):
    """
    混合架构爬虫基类（带Crawl4AI降级支持）
    
    提供通用的Crawl4AI集成方法、数据提取方法和业务流程方法。
    子类只需配置出版社特定的URL、分类映射和选择器。
    """

    # 子类需要覆盖这些属性
    NEW_RELEASES_URL: str = ""
    CATEGORY_MAP: dict[str, str] = {}

    # 通用选择器（子类可以覆盖）
    BOOK_LIST_SELECTORS: str = (
        '.product, .product-item, .book, .release-item, .new-release, .book-card, '
        '.product-tile, .grid-item, .book-tile, article.product, article.book, '
        'div.product, li.product, .item, .card, .product-card, .book-item'
    )
    BOOK_LINK_SELECTORS: str = (
        'a[href*="/books/"], a[href*="/book/"], a[href*="/product/"], '
        'a[href*="/products/"], a[href*="/title/"], a[href*="/book-details/"], '
        'a.product-link, a.book-link, a[class*="book"], a[class*="product"]'
    )
    TITLE_SELECTORS: str = '.book-title, .product-title, h1.title, h1.book-name, h1'
    AUTHOR_SELECTORS: str = '.author-name, .book-author, .contributor-name, .author a'
    DESCRIPTION_SELECTORS: str = '.book-description, .product-description, .synopsis, .summary, .description'
    COVER_SELECTORS: str = '.book-cover img, .product-image img, .cover-image img, img.book-image'
    CATEGORY_SELECTORS: str = '.category, .genre, .book-category, .imprint'
    PRICE_SELECTORS: str = '.price, .book-price, .product-price'
    PAGE_COUNT_SELECTORS: str = '.page-count, .pages, .book-pages'
    ISBN_SELECTORS: str = '.isbn, .book-isbn, [data-isbn], .product-details'
    BUY_SECTION_SELECTORS: str = '.buy-buttons, .purchase-options, .buy-links, .retailers'

    # 默认支持的零售商（子类可以覆盖）
    RETAILERS: dict[str, str] = {
        'Amazon': 'amazon.com',
        'Barnes & Noble': 'bn.com',
        'Books-A-Million': 'booksamillion.com',
        'Bookshop': 'bookshop.org',
        'IndieBound': 'indiebound.org',
        'Target': 'target.com',
        'Audible': 'audible.com',
    }

    def __init__(self, config: CrawlerConfig | None = None):
        """
        初始化爬虫

        Args:
            config: 爬虫配置，为 None 时使用默认配置
        """
        super().__init__(config)
        self._crawl4ai_available = self._check_crawl4ai()

    def _check_crawl4ai(self) -> bool:
        """检查 Crawl4AI 是否可用"""
        try:
            import crawl4ai
            logger.info(f"✅ {self.PUBLISHER_NAME_EN}: Crawl4AI 可用")
            return True
        except ImportError:
            logger.info(f"ℹ️ {self.PUBLISHER_NAME_EN}: Crawl4AI 未安装，仅使用传统 requests")
            return False

    async def _crawl_with_crawl4ai_async(self, url: str) -> Optional[str]:
        """使用 Crawl4AI 异步爬取网页"""
        if not self._crawl4ai_available:
            return None

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

            logger.info(f"🕸️ {self.PUBLISHER_NAME_EN}: 使用 Crawl4AI 爬取: {url}")

            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
            )

            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                word_count_threshold=1,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                if result and result.success and result.html:
                    logger.info(f"✅ {self.PUBLISHER_NAME_EN}: Crawl4AI 爬取成功")
                    return result.html
            return None
        except Exception as e:
            logger.warning(f"⚠️ {self.PUBLISHER_NAME_EN}: Crawl4AI 出错: {e}")
            return None

    def _crawl_with_crawl4ai(self, url: str) -> Optional[str]:
        """同步使用 Crawl4AI 爬取"""
        try:
            return asyncio.run(self._crawl_with_crawl4ai_async(url))
        except Exception as e:
            logger.warning(f"⚠️ {self.PUBLISHER_NAME_EN}: Crawl4AI 同步调用失败: {e}")
            return None

    def _make_request_with_fallback(self, url: str) -> tuple[Optional[BeautifulSoup], Optional[str]]:
        """
        带降级的请求方法

        先尝试传统 requests，失败后用 Crawl4AI
        返回 (soup, source)，source 是 'requests' 或 'crawl4ai'
        """
        logger.info(f"🔄 {self.PUBLISHER_NAME_EN}: 尝试传统 requests: {url}")
        response = self._make_request(url)

        if response:
            logger.info(f"✅ {self.PUBLISHER_NAME_EN}: 传统 requests 成功")
            return self._parse_html(response.text), 'requests'

        if self._crawl4ai_available:
            logger.info(f"🔄 {self.PUBLISHER_NAME_EN}: 降级到 Crawl4AI")
            html = self._crawl_with_crawl4ai(url)

            if html:
                logger.info(f"✅ {self.PUBLISHER_NAME_EN}: Crawl4AI 成功")
                return BeautifulSoup(html, 'html.parser'), 'crawl4ai'

        logger.warning(f"❌ {self.PUBLISHER_NAME_EN}: 所有方法都失败: {url}")
        return None, None

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

        # 尝试多种方式查找书籍项
        # 1. 使用配置的选择器
        book_items = soup.select(self.BOOK_LIST_SELECTORS)
        logger.info(f"🔍 找到 {len(book_items)} 个潜在书籍项")

        # 2. 如果没有找到，尝试更通用的选择器
        if not book_items:
            logger.info("🔍 尝试使用更通用的选择器")
            # 查找所有包含链接的元素
            all_links = soup.find_all('a', href=True)
            # 过滤出可能是书籍链接的元素
            potential_items = []
            for link in all_links:
                href = link.get('href', '')
                # 检查链接是否包含书籍相关的路径
                if any(keyword in href.lower() for keyword in ['/book/', '/books/', '/title/', '/product/']):
                    # 获取链接的父元素作为书籍项
                    parent = link.parent
                    while parent and parent.name not in ['div', 'article', 'li', 'section']:
                        parent = parent.parent
                    if parent and parent not in potential_items:
                        potential_items.append(parent)
            
            book_items = potential_items
            logger.info(f"🔍 使用通用选择器找到 {len(book_items)} 个潜在书籍项")

        # 3. 如果还是没有找到，尝试查找所有包含标题的元素
        if not book_items:
            logger.info("🔍 尝试查找包含标题的元素")
            title_elements = soup.find_all(['h2', 'h3', 'h4'])
            potential_items = []
            for title in title_elements:
                # 获取标题的父元素作为书籍项
                parent = title.parent
                while parent and parent.name not in ['div', 'article', 'li', 'section']:
                    parent = parent.parent
                if parent and parent not in potential_items:
                    potential_items.append(parent)
            
            book_items = potential_items
            logger.info(f"🔍 使用标题查找找到 {len(book_items)} 个潜在书籍项")

        # 去重
        seen_urls = set()
        unique_items = []
        for item in book_items:
            # 尝试多种方式查找链接
            link = item.select_one(self.BOOK_LINK_SELECTORS)
            if not link:
                # 尝试更通用的链接查找
                link = item.find('a', href=True)
            
            if link:
                href = link.get('href', '')
                if href not in seen_urls:
                    seen_urls.add(href)
                    unique_items.append(item)

        logger.info(f"📖 去重后剩余 {len(unique_items)} 个书籍项")

        for item in unique_items:
            try:
                book_data = {}

                # 提取详情链接
                link = item.select_one(self.BOOK_LINK_SELECTORS)
                if not link:
                    # 尝试更通用的链接查找
                    link = item.find('a', href=True)
                
                if link:
                    href = link.get('href', '')
                    if href:
                        book_data['url'] = urljoin(self.PUBLISHER_WEBSITE, href)

                # 提取书名
                title_elem = item.select_one(self.TITLE_SELECTORS)
                if not title_elem:
                    # 尝试更通用的标题查找
                    title_elem = item.find(['h2', 'h3', 'h4'])
                
                if title_elem:
                    book_data['title'] = self._clean_text(title_elem.get_text())

                # 提取作者
                author_elem = item.select_one(self.AUTHOR_SELECTORS)
                if not author_elem:
                    # 尝试查找包含 "by" 的元素
                    text = item.get_text().lower()
                    if 'by ' in text:
                        # 查找包含 "by" 的段落或span
                        for elem in item.find_all(['p', 'span']):
                            if 'by ' in elem.get_text().lower():
                                author_elem = elem
                                break
                
                if author_elem:
                    book_data['author'] = self._clean_text(author_elem.get_text())
                else:
                    # 尝试从文本中提取作者信息
                    text = item.get_text()
                    import re
                    match = re.search(r'by\s+([^\n]+)', text, re.IGNORECASE)
                    if match:
                        book_data['author'] = self._clean_text(match.group(1))

                # 确保有URL和标题
                if book_data.get('url') and book_data.get('title'):
                    books.append(book_data)
                    logger.debug(f"📖 解析到书籍: {book_data['title']} - {book_data['url']}")

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
        for selector in self.TITLE_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                return self._clean_text(elem.get_text())
        return "Unknown Title"

    def _extract_author(self, soup) -> str:
        """提取作者"""
        for selector in self.AUTHOR_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                return self._clean_text(elem.get_text())
        return "Unknown Author"

    def _extract_description(self, soup) -> str | None:
        """提取简介"""
        for selector in self.DESCRIPTION_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                return self._clean_text(elem.get_text())
        return None

    def _extract_cover_url(self, soup) -> str | None:
        """提取封面URL"""
        for selector in self.COVER_SELECTORS.split(', '):
            img = soup.select_one(selector.strip())
            if img:
                src = img.get('src') or img.get('data-src')
                if src:
                    return urljoin(self.PUBLISHER_WEBSITE, src)
        return None

    def _extract_category(self, soup) -> str | None:
        """提取分类"""
        for selector in self.CATEGORY_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                category_en = self._clean_text(elem.get_text()).lower()
                return self.CATEGORY_MAP.get(category_en, category_en)
        return None

    def _extract_publication_date(self, soup) -> Any:
        """提取出版日期"""
        
        # 先尝试从特定元素提取
        for selector in ['.publication-date', '.release-date', '.publish-date', '.on-sale-date']:
            elem = soup.select_one(selector)
            if elem:
                date_text = self._clean_text(elem.get_text())
                return self._parse_date(date_text)

        # 从页面文本查找
        page_text = soup.get_text()
        patterns = [
            r'(?:On Sale|Publication Date|Release Date|Pub Date)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:On Sale|Publication Date|Release Date|Pub Date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return self._parse_date(match.group(1))

        return None

    def _extract_price(self, soup) -> str | None:
        """提取价格"""
        for selector in self.PRICE_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                return self._parse_price(elem.get_text())
        return None

    def _extract_page_count(self, soup) -> int | None:
        """提取页数"""
        for selector in self.PAGE_COUNT_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                text = elem.get_text()
                match = re.search(r'(\d+)', text)
                if match:
                    return int(match.group(1))
        return None

    def _extract_isbn_text(self, soup) -> str | None:
        """提取包含ISBN的文本"""
        
        # 先尝试从特定元素提取
        for selector in self.ISBN_SELECTORS.split(', '):
            elem = soup.select_one(selector.strip())
            if elem:
                return elem.get_text()

        # 从页面文本查找
        page_text = soup.get_text()
        match = re.search(r'ISBN[-:\s]*(97[89]\d{10}|\d{9}[\dXx])', page_text, re.IGNORECASE)
        if match:
            return match.group(0)

        return None

    def _extract_buy_links(self, soup) -> list[dict[str, str]]:
        """提取购买链接"""
        links = []

        buy_section = soup.select_one(self.BUY_SECTION_SELECTORS)
        if buy_section:
            for link in buy_section.find_all('a', href=True):
                href = link.get('href', '')
                text = self._clean_text(link.get_text())

                for name, domain in self.RETAILERS.items():
                    if domain in href:
                        links.append({'name': name, 'url': href})
                        break

        return links