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
import tempfile
from datetime import UTC, datetime
from pathlib import Path

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
        from app.services.publisher_crawler import get_crawler_class
        from app.services.publisher_crawler.base_crawler import CrawlerConfig, CrawlRequest
        from app.services.publisher_data import DEFAULT_PUBLISHERS
    except ImportError as e:
        logger.error(f'导入模块失败: {e}')
        raise RuntimeError('爬虫模块不可用') from e

    class_by_name_en = {p['name_en']: p['crawler_class'] for p in DEFAULT_PUBLISHERS}

    def _sync_one(item: tuple) -> tuple:
        """单个 publisher 同步任务（线程 worker）

        失败隔离：单个 publisher 失败不影响其他。
        """
        name_en, slug = item
        logger.info(f'开始同步 {name_en}...')
        crawler = None
        try:
            crawler_cls = get_crawler_class(class_by_name_en[name_en])
            if crawler_cls is None:
                logger.error(f'爬虫类不可用: {name_en}')
                return slug, None
            key_name = crawler_cls.API_KEY_CONFIG
            api_key = os.environ.get(key_name, '').strip() if key_name else None
            logger.info('%s API Key 配置: %s', name_en, '已配置' if api_key else '未配置或不需要')
            if crawler_cls.api_key_required and not api_key:
                logger.error('%s 缺少必需的 API Key 配置', name_en)
                return slug, None
            crawler_config = CrawlerConfig(api_key=api_key)
            if crawler_cls.REQUEST_DELAY is not None:
                crawler_config.request_delay = crawler_cls.REQUEST_DELAY
            crawler = crawler_cls(crawler_config)
            outcome = crawler.get_new_books(CrawlRequest(max_books=100))
            books = [book.to_dict() for book in outcome.books]
            if outcome.errors:
                logger.error('%s 抓取不完整，保留上次有效快照', name_en)
                return slug, None
            return slug, books
        except Exception as e:
            # requests 异常字符串可能带含凭据的 URL；仅记录类型。
            logger.error('同步 %s 失败: %s', name_en, type(e).__name__)
            return slug, None
        finally:
            if crawler is not None:
                try:
                    crawler.close()
                except Exception as error:
                    logger.error('关闭 %s 爬虫失败: %s', name_en, type(error).__name__)

    all_books: dict = {}

    # v0.9.47：使用线程池并行，max_workers 与 publisher 数量一致
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=len(_PUBLISHER_EXPORTS), thread_name_prefix='pub-crawl') as executor:
        futures = {executor.submit(_sync_one, item): item for item in _PUBLISHER_EXPORTS}
        for future in as_completed(futures):
            slug, books = future.result()
            all_books[slug] = books
            logger.info('%s 同步结果: %s', slug, f'{len(books)} 本' if books is not None else '失败')

    return all_books


def _read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def _atomic_publish(documents):
    """先完整序列化，再逐文件原子替换；异常时恢复本轮已替换文件。"""
    staged = {}
    previous = {}
    replaced = []
    try:
        for path, document in documents.items():
            payload = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            previous[path] = path.read_bytes() if path.exists() else None
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
                staged[path] = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except BaseException:
        for path in reversed(replaced):
            old = previous[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
                    restore = Path(stream.name)
                    stream.write(old)
                try:
                    os.replace(restore, path)
                finally:
                    restore.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def export_to_static_files(books_data):
    """失败源和空结果不得清空有效快照；尝试时间与成功时间分别记录。

    None 表示抓取失败，[] 表示抓取成功但为空。空结果默认不满足替换
    已有非空数据的有效性条件，需要人工核实后才能清空。
    """
    directory = Path(STATIC_DATA_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    attempted_at = datetime.now(UTC).isoformat()
    merged = _read_json(directory / 'all_books.json', {})
    if not isinstance(merged, dict):
        raise ValueError('已有汇总快照格式无效，拒绝覆盖')
    metadata = _read_json(directory / 'update_time.json', {})
    source_success_at = dict(metadata.get('source_success_at', {}))
    documents = {}
    statuses = {}
    for slug, books in books_data.items():
        if not slug or any(character not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for character in slug):
            raise ValueError('无效的来源标识')
        path = directory / f'{slug}_books.json'
        old_books = _read_json(path, merged.get(slug, []))
        if not isinstance(old_books, list):
            raise ValueError('已有来源快照格式无效，拒绝覆盖')
        merged[slug] = old_books
        if books is None:
            status = 'failed'
        elif not isinstance(books, list) or any(
            not isinstance(book, dict)
            or not isinstance(book.get('title'), str)
            or not book['title'].strip()
            or not isinstance(book.get('author'), str)
            or not book['author'].strip()
            for book in books
        ):
            status = 'invalid'
        elif not books:
            status = 'empty_rejected' if old_books else 'success_empty'
            if status == 'success_empty':
                source_success_at[slug] = attempted_at
        else:
            status = 'success'
            merged[slug] = books
            documents[path] = books
            source_success_at[slug] = attempted_at
        successful = status in ('success', 'success_empty')
        statuses[slug] = {
            'status': status,
            'book_count': len(books) if isinstance(books, list) else None,
            'freshness': 'fresh' if successful else ('stale' if old_books else 'unknown'),
            'last_success_at': source_success_at.get(slug),
            'retained_previous': not successful and bool(old_books),
        }

    published = bool(documents)
    complete = bool(statuses) and all(item['status'] in ('success', 'success_empty') for item in statuses.values())
    attempt = {'attempted_at': attempted_at, 'sources': statuses, 'published': published, 'complete': complete}
    if published:
        documents[directory / 'all_books.json'] = merged
        # 成功标记最后替换；历史成功时间未知的来源不从提交时间/mtime伪造。
        documents[directory / 'update_time.json'] = {
            # 旧消费端只识别 timestamp：部分成功不得冒充整批新数据。
            'timestamp': attempted_at if complete else metadata.get('timestamp'),
            'published_at': attempted_at,
            'last_complete_success_at': attempted_at if complete else metadata.get('last_complete_success_at'),
            'status': 'success' if complete else 'partial',
            'publishers': list(merged),
            'total_books': sum(len(rows) for rows in merged.values()),
            'source_success_at': source_success_at,
        }
    elif source_success_at != metadata.get('source_success_at', {}):
        # A confirmed empty source still has a successful crawl time. Keep it
        # without advancing any snapshot publication or global success marker.
        documents[directory / 'update_time.json'] = dict(metadata, source_success_at=source_success_at)
    documents[directory / 'sync_attempt.json'] = attempt
    _atomic_publish(documents)
    logger.info('本轮快照: %s；完整成功: %s', '已更新有效来源' if published else '保留原数据', complete)
    return attempt


if __name__ == '__main__':
    logger.info('开始同步书籍数据...')

    # 同步所有出版社
    books_data = sync_all_publishers()

    # 导出为静态文件
    report = export_to_static_files(books_data)

    logger.info('同步完成，来源状态见 sync_attempt.json')
    raise SystemExit(0 if report['complete'] and report['published'] else 1)
