"""
Macmillan（麦克米伦）出版社爬虫

麦克米伦是英国主要出版商，在美国也有重要业务，
以出版学术、教育和大众图书闻名。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

网站特点：
- 按印记(Imprint)组织书籍
- 提供新书预告
- 支持多种分类浏览
"""
import logging

from .mixed_crawl4ai_crawler import MixedCrawl4AICrawler

logger = logging.getLogger(__name__)


class MacmillanCrawler(MixedCrawl4AICrawler):
    """
    Macmillan 出版社爬虫

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

    官方网站：https://us.macmillan.com/
    新书页面：https://us.macmillan.com/new-releases
    """

    PUBLISHER_NAME = "麦克米伦"
    PUBLISHER_NAME_EN = "Macmillan"
    PUBLISHER_WEBSITE = "https://us.macmillan.com"
    CRAWLER_CLASS_NAME = "MacmillanCrawler"

    # 新书页面URL
    NEW_RELEASES_URL = "https://us.macmillan.com/new-releases"

    CATEGORY_MAP = {
        'fiction': '小说',
        'non-fiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'thriller': '惊悚',
        'science-fiction': '科幻',
        'fantasy': '奇幻',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young-adult': '青少年',
        'science': '科学',
        'business': '商业',
        'graphic-novels': '图像小说',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.3
            self.config.respect_robots_txt = False

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'non-fiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'thriller', 'name': '惊悚'},
            {'id': 'science-fiction', 'name': '科幻'},
            {'id': 'fantasy', 'name': '奇幻'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young-adult', 'name': '青少年'},
            {'id': 'science', 'name': '科学'},
            {'id': 'business', 'name': '商业'},
            {'id': 'graphic-novels', 'name': '图像小说'},
        ]
