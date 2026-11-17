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
]


def sync_all_publishers():
    """并行同步所有出版社数据（走注册表与新爬虫接口 CrawlRequest/CrawlOutcome）。

    v0.9.47：7 个出版社爬虫改为 ThreadPoolExecutor 并行。
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
            crawler = crawler_cls()
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

    with ThreadPoolExecutor(max_workers=len(_PUBLISHER_EXPORTS), thread_name_prefix='pub-crawl') as executor:
        futures = {executor.submit(_sync_one, item): item for item in _PUBLISHER_EXPORTS}
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
