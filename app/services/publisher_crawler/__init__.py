"""
出版社爬虫模块

提供多种数据源的爬虫实现：
- Open Library（推荐，稳定可靠）
- Google Books（支持年份筛选）
- Google Books Publisher（按出版社名搜索，推荐用于无API的出版社）
- Publisher RSS（RSS Feed 解析）
- Penguin Random House（企鹅兰登，有结构化API）
- Simon & Schuster（西蒙舒斯特，Google Books API）
- Hachette（阿歇特，官网直接爬取 v1.7.0）
- HarperCollins（哈珀柯林斯，官网首页解析 v1.7.0）
- Macmillan（麦克米伦，Sitemap+Google Books 双路 v1.7.0）

推荐优先级：
1. 出版社自有 API 或官网爬虫（如企鹅兰登、阿歇特）
2. Google Books Publisher（按出版社名搜索，稳定可靠）
3. RSS Feed（如果有配置的话）
"""
import importlib
import logging

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)

__all__ = [
    'BaseCrawler',
    'BookInfo',
    'CrawlerConfig',
    'get_crawler_class',
    'get_all_crawlers',
]

# 爬虫模块映射表（统一注册入口）
_CRAWLER_MODULES = [
    ('OpenLibraryCrawler', '.open_library'),
    ('GoogleBooksCrawler', '.google_books'),
    ('PenguinRandomHouseCrawler', '.penguin_random_house'),
    ('SimonSchusterCrawler', '.simon_schuster'),
    ('HachetteCrawler', '.hachette'),
    ('HarperCollinsCrawler', '.harpercollins'),
    ('MacmillanCrawler', '.macmillan'),
    # Google Books 出版社搜索爬虫（按出版社名搜索，稳定可靠）
    ('SimonSchusterGoogleCrawler', '.google_books_publisher'),
    ('HachetteGoogleCrawler', '.google_books_publisher'),
    ('HarperCollinsGoogleCrawler', '.google_books_publisher'),
    ('MacmillanGoogleCrawler', '.google_books_publisher'),
    # RSS Feed 爬虫
    ('PenguinRandomHouseRSSCrawler', '.rss_crawler'),
    ('HarperCollinsRSSCrawler', '.rss_crawler'),
    ('SimonSchusterRSSCrawler', '.rss_crawler'),
]


def __getattr__(name: str):
    """延迟导入爬虫类"""
    for class_name, module_path in _CRAWLER_MODULES:
        if name == class_name:
            module = importlib.import_module(module_path, package=__name__)
            return getattr(module, class_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


CRAWLER_REGISTRY: dict[str, type[BaseCrawler]] = {}


def register_crawler(crawler_class: type[BaseCrawler]) -> None:
    CRAWLER_REGISTRY[crawler_class.CRAWLER_CLASS_NAME] = crawler_class


def get_crawler_class(name: str) -> type[BaseCrawler] | None:
    _load_all_crawlers()
    return CRAWLER_REGISTRY.get(name)


def get_all_crawlers() -> dict[str, type[BaseCrawler]]:
    _load_all_crawlers()
    return CRAWLER_REGISTRY.copy()


def _load_all_crawlers() -> None:
    """加载所有爬虫到注册表（统一注册入口）"""
    if CRAWLER_REGISTRY:
        return

    for class_name, module_path in _CRAWLER_MODULES:
        try:
            module = importlib.import_module(module_path, package=__name__)
            crawler_class = getattr(module, class_name)
            register_crawler(crawler_class)
        except Exception as e:
            logger.warning(f"无法加载爬虫 {class_name}: {e}")
