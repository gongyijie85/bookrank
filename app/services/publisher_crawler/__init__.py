"""
出版社爬虫模块

提供多种数据源的爬虫实现：
- Open Library（推荐，稳定可靠）
- Google Books（支持年份筛选）
- Penguin Random House（企鹅兰登）
- Simon & Schuster（西蒙舒斯特）
- Hachette（阿歇特）
- HarperCollins（哈珀柯林斯）
- Macmillan（麦克米伦）

注意：由于出版社网站反爬措施，建议优先使用Open Library或Google Books数据源。
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
