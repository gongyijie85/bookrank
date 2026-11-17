#!/usr/bin/env python3
"""
书籍数据同步脚本

该脚本用于同步所有出版社的新书数据，并将数据导出为静态 JSON 文件，
以便在 Render 免费版上使用。

使用方法：
    python update_books.py
"""

import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.publisher_crawler.base_crawler import CrawlerConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('update_books.log', encoding='utf-8')],
)
logger = logging.getLogger(__name__)

# 确保静态数据目录存在
STATIC_DATA_DIR = os.path.join('static', 'data')
os.makedirs(STATIC_DATA_DIR, exist_ok=True)


# 活跃爬虫的静态数据导出 slug：与 static/data/*_books.json 的兜底种子
# 文件名（app/services/publisher_data.py 的 STATIC_DATA_FILES）保持一致
_PUBLISHER_EXPORTS = [
    ('Google Books', 'google_books'),
    ('Penguin Random House', 'penguin_random_house'),
    ('Hachette', 'hachette'),
    ('HarperCollins', 'harpercollins'),
    ('Macmillan', 'macmillan'),
    ('Simon & Schuster', 'simon_schuster'),
    ('Open Library', 'open_library'),
    ('Library of Congress', 'library_of_congress'),
]


def _build_crawler_config(crawler_cls) -> 'CrawlerConfig | None':
    """按基类声明的接口事实给爬虫注入配置（API_KEY_CONFIG / REQUEST_DELAY）。

    这里曾经直接调用 crawler_cls()：workflow 明明注入了 GOOGLE_API_KEY，但没人读它，
    于是 Google Books 系全程无 key 匿名请求，被 GitHub Actions 的共享出口 IP 限流成
    429（GCP 配额页显示只用了 1.3%，key 根本没被用过）；PRH 也因为拿不到 key 直接失败。
    Flask 内的 sync_engine 是走 API_KEY_CONFIG 注入的，本脚本是另一条路径，得自己来。

    无可注入项时返回 None，保持各爬虫 __init__ 里 config=None 的默认节奏
    （如 Macmillan 的 0.8 秒），不给没有 key 的源制造行为变化。
    """
    from app.services.publisher_crawler.base_crawler import CrawlerConfig

    api_key_config = getattr(crawler_cls, 'API_KEY_CONFIG', None)
    api_key = os.environ.get(api_key_config) if api_key_config else None
    request_delay = getattr(crawler_cls, 'REQUEST_DELAY', None)
    if not api_key and request_delay is None:
        return None

    config = CrawlerConfig(api_key=api_key)
    if request_delay is not None:
        config.request_delay = request_delay
    return config


def _has_required_env(crawler_cls) -> bool:
    """必填凭据的适配器（如 PRH）缺配置时快速失败，别把协议错误伪装成「0 本」。

    只返回布尔值：日志里不放任何从该属性派生的名字。CodeQL 会把名为
    *_API_KEY* 的配置项当敏感源，哪怕只打印变量名也会判成明文泄漏；而同一行日志
    已经写了出版社名，够定位了。
    """
    env_name = getattr(crawler_cls, 'API_KEY_CONFIG', None)
    if not env_name or not getattr(crawler_cls, 'api_key_required', False):
        return True
    return bool(os.environ.get(env_name))


def sync_all_publishers():
    """并行同步所有出版社数据（走注册表与新爬虫接口 CrawlRequest/CrawlOutcome）。

    只跑 DEFAULT_PUBLISHERS 里 is_active 的源（Google Books / Open Library 已停用）。
    爬虫是 IO 密集型（HTTP 请求），线程足够，无需 multiprocessing。
    """
    try:
        from app.services.publisher_crawler import get_crawler_class, load_all_crawlers
        from app.services.publisher_crawler.base_crawler import CrawlRequest
        from app.services.publisher_data import DEFAULT_PUBLISHERS
    except ImportError as e:
        logger.error(f'导入模块失败: {e}')
        return {}

    class_by_name_en = {p['name_en']: p['crawler_class'] for p in DEFAULT_PUBLISHERS}
    # 配置里显式标记 is_active=False 的源不该再跑：Google Books 和 Open Library
    # 早就是停用状态，但同步列表一直是硬编码的，于是每周都白跑两条、日志里还各留
    # 一行「获取到 0 本书籍」，把真正的失败原因埋掉了。
    active_by_name_en = {p['name_en']: p.get('is_active', True) for p in DEFAULT_PUBLISHERS}
    exports = [item for item in _PUBLISHER_EXPORTS if active_by_name_en.get(item[0], True)]
    skipped_sources = [name for name, _ in _PUBLISHER_EXPORTS if not active_by_name_en.get(name, True)]
    if skipped_sources:
        logger.info(f'按 is_active=false 跳过数据源：{", ".join(skipped_sources)}')

    def _sync_one(item: tuple) -> tuple:
        """单个 publisher 同步任务（线程 worker）

        失败隔离：单个 publisher 失败不影响其他。
        """
        name_en, slug = item
        logger.info(f'开始同步 {name_en}...')
        try:
            crawler_cls = get_crawler_class(class_by_name_en[name_en])
            if crawler_cls is None:
                logger.error(f'爬虫类不可用: {name_en}')
                return slug, [], '爬虫类不可用'
            if not _has_required_env(crawler_cls):
                logger.error(f'{name_en} 缺少必需的凭据配置，跳过该源')
                return slug, [], '缺少必需的凭据配置'
            crawler = crawler_cls(_build_crawler_config(crawler_cls))
            outcome = crawler.get_new_books(CrawlRequest(max_books=100))
            books = [book.to_dict() for book in outcome.books]
            return slug, books, '' if books else '上游返回 0 本'
        except Exception as e:
            logger.error(f'同步 {name_en} 失败: {e}')
            return slug, [], f'同步异常: {e}'

    all_books: dict = {}
    empty_sources: dict[str, str] = {}

    # 先一次性把注册表加载完，再进线程池：多个线程同时首次加载会看到半填的
    # 注册表，随机某个出版社拿不到自己的爬虫类（见 publisher_crawler.load_all_crawlers）。
    load_all_crawlers()

    # v0.9.47：使用线程池并行，max_workers 与 publisher 数量一致
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=len(exports), thread_name_prefix='pub-crawl') as executor:
        futures = {executor.submit(_sync_one, item): item for item in exports}
        for future in as_completed(futures):
            slug, books, reason = future.result()
            all_books[slug] = books
            logger.info(f'{slug} 同步完成，获取到 {len(books)} 本书籍')
            if not books:
                empty_sources[slug] = reason

    _report_sync_summary(all_books, empty_sources)
    return all_books


def _report_sync_summary(all_books: dict, empty_sources: dict[str, str]) -> None:
    """把「绿着但空转」写成一条可 grep 的结论，并同步进 Actions 的 step summary。

    #346 之后每周都跑绿却一本没抓到，日志里只有 7 条「获取到 0 本书籍」散落其中，
    看不出整体结论。这里聚合一次，配额/缺 key/上游改协议的锅一眼能分清。
    """
    total_books = sum(len(books) for books in all_books.values())
    if not empty_sources:
        logger.info(f'数据源同步汇总：{len(all_books)} 源共 {total_books} 本，全部有数据')
        return

    logger.warning(
        f'数据源同步汇总：{len(all_books)} 源共 {total_books} 本，'
        f'{len(empty_sources)} 源为空 —— '
        + '；'.join(f'{slug}({reason})' for slug, reason in sorted(empty_sources.items()))
    )

    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not summary_path:
        return
    try:
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write('### 数据源同步结果\n\n')
            f.write('| 数据源 | 本数 | 说明 |\n| --- | --- | --- |\n')
            for slug, books in all_books.items():
                note = empty_sources.get(slug) or ''
                f.write(f'| {slug} | {len(books)} | {note} |\n')
            f.write(f'\n合计 {total_books} 本。\n')
    except OSError as e:
        logger.warning(f'写入 step summary 失败: {e}')


def export_to_static_files(books_data):
    """将书籍数据导出为静态 JSON 文件"""
    # 导出所有出版社数据
    all_data_path = os.path.join(STATIC_DATA_DIR, 'all_books.json')
    with open(all_data_path, 'w', encoding='utf-8') as f:
        json.dump(books_data, f, ensure_ascii=False, indent=2)
    logger.info(f'已导出所有数据到 {all_data_path}')

    # 为每个出版社单独导出数据
    for publisher_name, books in books_data.items():
        publisher_path = os.path.join(STATIC_DATA_DIR, f'{publisher_name}_books.json')
        with open(publisher_path, 'w', encoding='utf-8') as f:
            json.dump(books, f, ensure_ascii=False, indent=2)
        logger.info(f'已导出 {publisher_name} 数据到 {publisher_path}')

    # 创建更新时间文件
    update_time = {
        'timestamp': datetime.now().isoformat(),
        'publishers': list(books_data.keys()),
        'total_books': sum(len(books) for books in books_data.values()),
    }
    update_time_path = os.path.join(STATIC_DATA_DIR, 'update_time.json')
    with open(update_time_path, 'w', encoding='utf-8') as f:
        json.dump(update_time, f, ensure_ascii=False, indent=2)
    logger.info(f'已更新时间戳到 {update_time_path}')


if __name__ == '__main__':
    logger.info('开始同步书籍数据...')

    # 同步所有出版社
    books_data = sync_all_publishers()

    # 导出为静态文件
    export_to_static_files(books_data)

    logger.info('同步完成！')
