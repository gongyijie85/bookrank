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
import threading

from ...utils.error_handler import ErrorCategory, log_error
from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig, CrawlOutcome, CrawlRequest

__all__ = [
    'BaseCrawler',
    'BookInfo',
    'CrawlOutcome',
    'CrawlRequest',
    'CrawlerConfig',
    'get_crawler_class',
    'load_all_crawlers',
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
    ('LibraryOfCongressCrawler', '.library_of_congress'),
]


CRAWLER_REGISTRY: dict[str, type[BaseCrawler]] = {}


def register_crawler(crawler_class: type[BaseCrawler]) -> None:
    CRAWLER_REGISTRY[crawler_class.CRAWLER_CLASS_NAME] = crawler_class


def get_crawler_class(name: str) -> type[BaseCrawler] | None:
    load_all_crawlers()
    return CRAWLER_REGISTRY.get(name)


_LOAD_LOCK = threading.Lock()
_LOADED = False


def load_all_crawlers() -> None:
    """加载所有爬虫到注册表（统一注册入口，线程安全）。

    并发调用方（update_books 的线程池）在首次加载时会撞上「注册表非空就直接
    返回」的旧语义：先到的线程导入到一半，其余线程看到半填的注册表就返回，
    拿不到自己那一类 —— 表现为随机某个出版社「爬虫类不可用」。

    这里加锁，并在局部 dict 里攒齐后一次性发布：任何人观察到的注册表要么是空的，
    要么是完整的。用 _LOADED 而不是「注册表非空」当加载完成标志，避免半填状态
    把后续调用锁死。
    """
    global _LOADED

    if _LOADED:
        return

    with _LOAD_LOCK:
        if _LOADED:
            return

        loaded: dict[str, type[BaseCrawler]] = {}
        for class_name, module_path in _CRAWLER_MODULES:
            try:
                module = importlib.import_module(module_path, package=__name__)
                crawler_class = getattr(module, class_name)
                loaded[crawler_class.CRAWLER_CLASS_NAME] = crawler_class
            except Exception as e:
                log_error(ErrorCategory.CRAWLER, f'无法加载爬虫 {class_name}: {e}', level='warning')

        CRAWLER_REGISTRY.update(loaded)
        _LOADED = True


# 兼容旧调用点（历史上是私有函数）
_load_all_crawlers = load_all_crawlers
