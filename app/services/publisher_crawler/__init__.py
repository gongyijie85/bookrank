"""
出版社爬虫模块

生产活跃数据源（2026-08 死适配器清理后）：
- Open Library（默认停用，数据质量实测不可靠）
- Google Books（通用关键词搜索，默认停用）
- Google Books Publisher（按出版社名搜索：Simon & Schuster / Hachette /
  HarperCollins / Macmillan 四个出版社变体）
- PrhApiCrawler（企鹅兰登官方 API，14 天增量 + 30 天回填窗口）
- Macmillan（麦克米伦，Sitemap+Google Books 双路）

推荐优先级：
1. 出版社自有 API（企鹅兰登 PrhApiCrawler）
2. Google Books Publisher（按出版社名搜索，稳定可靠）
3. Macmillan 双路（自有站点补充）
"""

import importlib

from ...utils.error_handler import ErrorCategory, log_error
from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig, CrawlOutcome, CrawlRequest

__all__ = [
    'BaseCrawler',
    'BookInfo',
    'CrawlOutcome',
    'CrawlRequest',
    'CrawlerConfig',
    'get_crawler_class',
]


# 爬虫模块映射表（统一注册入口）
# 仅保留生产活跃类；legacy 站点爬虫 / RSS / MixedCrawl4AI 已随
# docs/superpowers/specs/2026-08-14-retire-dead-adapters.md 删除。
_CRAWLER_MODULES = [
    ('OpenLibraryCrawler', '.open_library'),
    ('GoogleBooksCrawler', '.google_books'),
    ('PrhApiCrawler', '.prh_api'),
    ('MacmillanCrawler', '.macmillan'),
    # Google Books 出版社搜索爬虫（按出版社名搜索，稳定可靠）
    ('SimonSchusterGoogleCrawler', '.google_books_publisher'),
    ('HachetteGoogleCrawler', '.google_books_publisher'),
    ('HarperCollinsGoogleCrawler', '.google_books_publisher'),
    ('MacmillanGoogleCrawler', '.google_books_publisher'),
]


CRAWLER_REGISTRY: dict[str, type[BaseCrawler]] = {}


def register_crawler(crawler_class: type[BaseCrawler]) -> None:
    CRAWLER_REGISTRY[crawler_class.CRAWLER_CLASS_NAME] = crawler_class


def get_crawler_class(name: str) -> type[BaseCrawler] | None:
    _load_all_crawlers()
    return CRAWLER_REGISTRY.get(name)


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
            log_error(ErrorCategory.CRAWLER, f'无法加载爬虫 {class_name}: {e}', level='warning')
