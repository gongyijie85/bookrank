"""
Hachette（阿歇特）出版社爬虫

阿歇特是全球第三大出版集团，
总部位于法国，在美国、英国等地有分支机构。

网站特点：
- 按地区有不同网站
- 提供新书预告和发布信息
- 分类清晰
"""
import logging
from typing import Any, Generator
from urllib.parse import urljoin

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class HachetteCrawler(BaseCrawler):
    """
    Hachette 出版社爬虫

    官方网站：https://www.hachettebookgroup.com/
    新书页面：https://www.hachettebookgroup.com/new-releases/
    """

    PUBLISHER_NAME = "阿歇特"
    PUBLISHER_NAME_EN = "Hachette"
    PUBLISHER_WEBSITE = "https://www.hachettebookgroup.com"
    CRAWLER_CLASS_NAME = "HachetteCrawler"

    # 新书页面URL
    NEW_RELEASES_URL = "https://www.hachettebookgroup.com/new-releases/"

    # 分类映射
    CATEGORY_MAP = {
        'fiction': '小说',
        'non-fiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'science-fiction': '科幻',
        'fantasy': '奇幻',
        'thriller': '惊悚',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young-adult': '青少年',
        'business': '商业',
        'self-help': '自助',
    }

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.3

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'non-fiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'science-fiction', 'name': '科幻'},
            {'id': 'fantasy', 'name': '奇幻'},
            {'id': 'thriller', 'name': '惊悚'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young-adult', 'name': '青少年'},
            {'id': 'business', 'name': '商业'},
            {'id': 'self-help', 'name': '自助'},
        ]

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100
    ) -> Generator[BookInfo, None, None]:
        """获取新书列表"""
        page = 1
        count = 0

        while count < max_books and page <= self.config.max_pages:
            url = self._build_list_url(category, page)
            logger.info(f"📄 正在爬取第 {page} 页: {url}")

            response = self._make_request(url)
            if not response:
                break

            soup = self._parse_html(response.text)
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

        # Hachette 书籍列表选择器
        book_items = soup.select('.book-item, .product-card, [data-book-id], .book-card')

        if not book_items:
            book_items = soup.select('article.book, li.book, div.book')

        for item in book_items:
            try:
                book_data = {}

                # 提取详情链接
                link = item.select_one('a[href*="/book/"], a[href*="/books/"]')
                if link:
                    href = link.get('href', '')
                    book_data['url'] = urljoin(self.PUBLISHER_WEBSITE, href)

                # 提取书名
                title_elem = item.select_one('.title, .book-title, h2, h3')
                if title_elem:
                    book_data['title'] = self._clean_text(title_elem.get_text())

                # 提取作者
                author_elem = item.select_one('.author, .book-author, .contributor')
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
        """获取书籍详情"""
        response = self._make_request(book_url)
        if not response:
            return None

        soup = self._parse_html(response.text)

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
        selectors = ['.book-title', '.product-title', 'h1.title', 'h1.book-name', 'h1']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return "Unknown Title"

    def _extract_author(self, soup) -> str:
        """提取作者"""
        selectors = ['.author-name', '.book-author', '.contributor-name', '.author a']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return "Unknown Author"

    def _extract_description(self, soup) -> str | None:
        """提取简介"""
        selectors = ['.book-description', '.product-description', '.synopsis', '.summary', '.description']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._clean_text(elem.get_text())
        return None

    def _extract_cover_url(self, soup) -> str | None:
        """提取封面URL"""
        img_selectors = ['.book-cover img', '.product-image img', '.cover-image img', 'img.book-image']
        for selector in img_selectors:
            img = soup.select_one(selector)
            if img:
                src = img.get('src') or img.get('data-src')
                if src:
                    return urljoin(self.PUBLISHER_WEBSITE, src)
        return None

    def _extract_category(self, soup) -> str | None:
        """提取分类"""
        selectors = ['.category', '.genre', '.book-category', '.imprint']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                category_en = self._clean_text(elem.get_text()).lower()
                return self.CATEGORY_MAP.get(category_en, category_en)
        return None

    def _extract_publication_date(self, soup) -> Any:
        """提取出版日期"""
        selectors = ['.publication-date', '.release-date', '.publish-date', '.on-sale-date']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                date_text = self._clean_text(elem.get_text())
                return self._parse_date(date_text)

        page_text = soup.get_text()
        import re
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
        selectors = ['.price', '.book-price', '.product-price']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return self._parse_price(elem.get_text())
        return None

    def _extract_page_count(self, soup) -> int | None:
        """提取页数"""
        selectors = ['.page-count', '.pages', '.book-pages']
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
        selectors = ['.isbn', '.book-isbn', '[data-isbn]', '.product-details']
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
            'Bookshop': 'bookshop.org',
            'IndieBound': 'indiebound.org',
            'Target': 'target.com',
            'Walmart': 'walmart.com',
        }

        buy_section = soup.select_one('.buy-buttons, .purchase-options, .buy-links, .retailers')
        if buy_section:
            for link in buy_section.find_all('a', href=True):
                href = link.get('href', '')
                text = self._clean_text(link.get_text())

                for name, domain in retailers.items():
                    if domain in href:
                        links.append({'name': name, 'url': href})
                        break

        return links
