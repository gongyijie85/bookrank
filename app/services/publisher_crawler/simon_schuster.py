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
import logging

from .mixed_crawl4ai_crawler import MixedCrawl4AICrawler

logger = logging.getLogger(__name__)


class SimonSchusterCrawler(MixedCrawl4AICrawler):
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

    RETAILERS = {
        'Amazon': 'amazon.com',
        'Barnes & Noble': 'bn.com',
        'Books-A-Million': 'booksamillion.com',
        'Apple Books': 'apple.com',
        'Google Play': 'play.google.com',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.2
            self.config.respect_robots_txt = False

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
