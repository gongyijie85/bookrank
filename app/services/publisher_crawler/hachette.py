"""
Hachette（阿歇特）出版社爬虫

阿歇特是全球第三大出版集团，
总部位于法国，在美国、英国等地有分支机构。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

网站特点：
- 按地区有不同网站
- 提供新书预告和发布信息
- 分类清晰
"""
import logging

from .mixed_crawl4ai_crawler import MixedCrawl4AICrawler

logger = logging.getLogger(__name__)


class HachetteCrawler(MixedCrawl4AICrawler):
    """
    Hachette 出版社爬虫

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

    官方网站：https://www.hachettebookgroup.com/
    新书页面：https://www.hachettebookgroup.com/new-releases/
    """

    PUBLISHER_NAME = "阿歇特"
    PUBLISHER_NAME_EN = "Hachette"
    PUBLISHER_WEBSITE = "https://www.hachettebookgroup.com"
    CRAWLER_CLASS_NAME = "HachetteCrawler"

    # 新书页面URL
    NEW_RELEASES_URL = "https://www.hachettebookgroup.com/category/books/"

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

    # 支持的零售商
    RETAILERS = {
        'Amazon': 'amazon.com',
        'Barnes & Noble': 'bn.com',
        'Books-A-Million': 'booksamillion.com',
        'Bookshop': 'bookshop.org',
        'IndieBound': 'indiebound.org',
        'Target': 'target.com',
        'Walmart': 'walmart.com',
    }

    # Hachette 特定选择器
    BOOK_LIST_SELECTORS: str = (
        '.product, .product-item, .book, .release-item, .new-release, .book-card, '
        '.product-tile, .grid-item, .book-tile, article.product, article.book, '
        'div.product, li.product, .item, .card, .product-card, .book-item, '
        '.masonry-item, .grid-item, .book-grid-item, .product-grid-item'
    )
    BOOK_LINK_SELECTORS: str = (
        'a[href*="/books/"], a[href*="/book/"], a[href*="/product/"], '
        'a[href*="/products/"], a[href*="/title/"], a[href*="/book-details/"], '
        'a.product-link, a.book-link, a[class*="book"], a[class*="product"], '
        'a[href*="/title/"], a[href*="/book/"], a[href*="/product/"]'
    )

    def __init__(self, config=None):
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
