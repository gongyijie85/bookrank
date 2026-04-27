"""
Penguin Random House（企鹅兰登）出版社爬虫

企鹅兰登是世界上最大的大众图书出版商之一，
网站提供新书发布信息、作者介绍和书籍详情。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级
（继承自 MixedCrawl4AICrawler 基类）
"""
import logging

from .mixed_crawl4ai_crawler import MixedCrawl4AICrawler

logger = logging.getLogger(__name__)


class PenguinRandomHouseCrawler(MixedCrawl4AICrawler):
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

    NEW_RELEASES_URL = "https://www.penguinrandomhouse.com/books/new-releases/"

    # 企鹅兰登特定选择器（网站使用 .carousel .item 结构）
    BOOK_LIST_SELECTORS: str = (
        '.carousel .item, .book-item, .product-item, [data-book-id], .book-card, '
        '.product, .release-item, .new-release, .product-tile, .grid-item'
    )
    BOOK_LINK_SELECTORS: str = (
        'a[href*="/books/"], .img a, .title a, '
        'a[href*="/book/"], a[href*="/product/"], '
        'a.product-link, a.book-link'
    )
    TITLE_SELECTORS: str = '.title a, .title, .book-title, h1.book-title, h1.product-title, .book-info h1, h1'
    AUTHOR_SELECTORS: str = '.contributor a, .contributor, .author-name, .book-author, .contributor-name, .author a'
    DESCRIPTION_SELECTORS: str = '.book-description, .product-description, .synopsis, .summary, [data-description], .description'
    COVER_SELECTORS: str = '.book-cover img, .product-image img, .cover-image img, img.book-image, img[alt*="cover"]'
    CATEGORY_SELECTORS: str = '.book-category, .genre, .category, [data-category]'
    PRICE_SELECTORS: str = '.price, .book-price, .product-price, [data-price]'
    PAGE_COUNT_SELECTORS: str = '.page-count, .pages, [data-pages]'
    ISBN_SELECTORS: str = '.isbn, .book-isbn, [data-isbn]'
    BUY_SECTION_SELECTORS: str = '.buy-buttons, .purchase-options, .buy-links'

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

    RETAILERS = {
        'Amazon': 'amazon.com',
        'Barnes & Noble': 'bn.com',
        'Books-A-Million': 'booksamillion.com',
        'Bookshop': 'bookshop.org',
        'IndieBound': 'indiebound.org',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.5

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
