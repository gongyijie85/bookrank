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
from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

__all__ = [
    'BaseCrawler',
    'BookInfo',
    'CrawlerConfig',
    'OpenLibraryCrawler',
    'GoogleBooksCrawler',
    'PenguinRandomHouseCrawler',
    'SimonSchusterCrawler',
    'HachetteCrawler',
    'HarperCollinsCrawler',
    'MacmillanCrawler',
]


def __getattr__(name: str):
    """延迟导入爬虫类"""
    if name == 'OpenLibraryCrawler':
        from .open_library import OpenLibraryCrawler
        return OpenLibraryCrawler
    elif name == 'GoogleBooksCrawler':
        from .google_books import GoogleBooksCrawler
        return GoogleBooksCrawler
    elif name == 'PenguinRandomHouseCrawler':
        from .penguin_random_house import PenguinRandomHouseCrawler
        return PenguinRandomHouseCrawler
    elif name == 'SimonSchusterCrawler':
        from .simon_schuster import SimonSchusterCrawler
        return SimonSchusterCrawler
    elif name == 'HachetteCrawler':
        from .hachette import HachetteCrawler
        return HachetteCrawler
    elif name == 'HarperCollinsCrawler':
        from .harpercollins import HarperCollinsCrawler
        return HarperCollinsCrawler
    elif name == 'MacmillanCrawler':
        from .macmillan import MacmillanCrawler
        return MacmillanCrawler
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
    if CRAWLER_REGISTRY:
        return

    try:
        from .open_library import OpenLibraryCrawler
        register_crawler(OpenLibraryCrawler)
    except ImportError:
        pass

    try:
        from .google_books import GoogleBooksCrawler
        register_crawler(GoogleBooksCrawler)
    except ImportError:
        pass

    try:
        from .penguin_random_house import PenguinRandomHouseCrawler
        register_crawler(PenguinRandomHouseCrawler)
    except ImportError:
        pass

    try:
        from .simon_schuster import SimonSchusterCrawler
        register_crawler(SimonSchusterCrawler)
    except ImportError:
        pass

    try:
        from .hachette import HachetteCrawler
        register_crawler(HachetteCrawler)
    except ImportError:
        pass

    try:
        from .harpercollins import HarperCollinsCrawler
        register_crawler(HarperCollinsCrawler)
    except ImportError:
        pass

    try:
        from .macmillan import MacmillanCrawler
        register_crawler(MacmillanCrawler)
    except ImportError:
        pass
