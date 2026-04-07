"""
HarperCollins（哈珀柯林斯）出版社爬虫

哈珀柯林斯是全球最大的出版商之一，
总部位于美国，是新闻集团的子公司。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

网站特点：
- 提供新书预告和发布日历
- 按品牌/印记分类
- 丰富的书籍元数据
"""
import logging

from .mixed_crawl4ai_crawler import MixedCrawl4AICrawler

logger = logging.getLogger(__name__)


class HarperCollinsCrawler(MixedCrawl4AICrawler):
    """
    HarperCollins 出版社爬虫

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

    官方网站：https://www.harpercollins.com/
    新书页面：https://www.harpercollins.com/pages/new-releases
    """

    PUBLISHER_NAME = "哈珀柯林斯"
    PUBLISHER_NAME_EN = "HarperCollins"
    PUBLISHER_WEBSITE = "https://www.harpercollins.com"
    CRAWLER_CLASS_NAME = "HarperCollinsCrawler"

    # 新书页面URL
    NEW_RELEASES_URL = "https://www.harpercollins.com/pages/new-releases"

    # 分类映射
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
        'christian': '基督教',
        'business': '商业',
        'cookbook': '烹饪',
    }

    # 支持的零售商
    RETAILERS = {
        'Amazon': 'amazon.com',
        'Barnes & Noble': 'bn.com',
        'Books-A-Million': 'booksamillion.com',
        'Bookshop': 'bookshop.org',
        'Apple Books': 'apple.com',
        'Google Play': 'play.google.com',
        'Audible': 'audible.com',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.2

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
            {'id': 'christian', 'name': '基督教'},
            {'id': 'business', 'name': '商业'},
            {'id': 'cookbook', 'name': '烹饪'},
        ]
