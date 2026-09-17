"""清空被「图书上下文注水」的中文简介 / 详情（一次性回填工具）。

背景
----
2026-09-17 生产取证：部分书的 ``description_zh`` 不是译文，而是模型拿 ``book_context``
里的书名 / 作者 / 榜单名 / 出版社重新写的一段图书介绍（例：AWESOME FRIENDLY KID
英文 73 字符 → 中文 311 字符，4.26 倍）。上游防线 ``is_inflated_translation``
（app/utils/api_helpers.py:566）只保证**今后**不再产生这类译文，历史坏值仍在库里。

为什么不能只清 ``book_metadata``
--------------------------------
``book_metadata`` 只是三层回填里的第一层。``BookLanguagePack.hydrate_books``
（app/services/book_language_pack.py:38）的填充顺序是：

1. ``book_metadata.description_zh`` / ``details_zh``（``_apply_isbn_translations``）；
2. 静态语言包 ``static/data/book_language_pack.zh.json``（``_load_static_pack``）；
3. ``translation_cache`` 按英文原文哈希精确匹配（``_apply_exact_text_cache``）。

``_fill_missing``（同文件 :343）只在目标字段为空时才填，所以：只把 DB 置成 NULL，
线上会立刻从**语言包**读回同一个坏值；语言包也清了、缓存还在，同样会读回。
2026-09-11 那次同步把注水译文同时写进了这三处，故 ``--apply`` 默认三层一起清。

``--only-db`` 只清 DB，用于对照「只清数据库会怎样」，线上不要这么用。

用法::

    python scripts/backfill_inflated_translations.py                  # dry-run（默认，不写任何东西）
    python scripts/backfill_inflated_translations.py --apply          # 清 DB + 语言包 + 翻译缓存
    python scripts/backfill_inflated_translations.py --apply --only-db

退出码：0 = 无需处理 / 全部清空成功；2 = --dry-run 且存在命中；1 = 有清理失败。
诊断详情同时写入 ``.scratch/backfill_inflated.log``（该目录已被 git 忽略）。

英文原文从哪来
--------------
``book_metadata`` 表里**没有** ``description`` 列（只有 ``details``），所以
``description_zh`` 的英文原文需要另找。本脚本按序取三个来源（全部只读）：

1. ``api_cache`` 表里 ``api_source='nyt'`` 的原始榜单响应（线上即此来源）；
2. ``--cache-dir``（默认 ``cache/``）下的 API 快照 JSON；
3. ``new_books`` 表的 ``description``。

三处都找不到英文原文的行会被计入 ``unresolved`` 并**跳过**（不猜、不清）。

被清的是 ``description_zh`` 与 ``details_zh`` 两个字段（``title_zh`` 不启用注水判定，
理由见 ``api_helpers.INFLATION_GUARDED_FIELDS``）。清空写的是 NULL，不是空字符串。

运维提示
--------
- ``development`` 配置把 ``SQLALCHEMY_ECHO`` 写死为 True（``app/config.py:240``），
  启动期会有约 2000 行 SQL INFO；命中清单在**最后**，``| tail -40`` 即可看清。
- 脚本会自己禁掉 APScheduler，不会在清理期间跑后台任务。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在 import app 之前：``app/__init__.py:684`` 在**包导入时**就会执行
# ``create_app(os.environ.get('FLASK_ENV', 'development'))``，那一次会真的把
# APScheduler 启起来（12 个任务，含写库的延迟初始化与封面预取），于是「只读的
# dry-run」并不只读。只在被当作脚本执行时设置 —— 被 import（单测）时不许污染
# 调用方进程环境（回归：见 _quiet_process 的 docstring）。
if __name__ == '__main__':
    os.environ['DISABLE_BACKGROUND_THREADS'] = 'true'

from app.utils.api_helpers import is_inflated_translation
from app.utils.error_handler import ErrorCategory, log_error

#: 权威语言包（部署态直接生效，必须与 DB 一起清，理由见模块 docstring）
PACK_DEFAULT = 'static/data/book_language_pack.zh.json'
#: 上游 API 快照目录（sync_book_language_pack.py 用的同一批文件）
CACHE_DIR_DEFAULT = 'cache'
STATIC_DATA_DIR_DEFAULT = 'static/data'
#: 书的「英文简介」所在键名；只认英文，不认 description_zh
_DESCRIPTION_KEY = 'description'
_ISBN_KEYS = ('primary_isbn13', 'isbn13', 'isbn10', 'primary_isbn10')
#: 翻译时会被当作「图书上下文」喂给模型、因而不该出现在译文里的元信息
_CONTEXT_KEYS = ('publisher', 'list_name', 'category_name', 'series')

LOG_PATH = ROOT / '.scratch' / 'backfill_inflated.log'
_log_lines: list[str] = []


def emit(message: str = '') -> None:
    """同时写终端与日志文件；终端编码异常时降级为 ASCII，不影响退出码。"""
    _log_lines.append(message)
    try:
        print(message)
    except UnicodeEncodeError:
        try:
            print(message.encode('ascii', 'replace').decode('ascii'))
        except Exception:
            pass


def flush_log() -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text('\n'.join(_log_lines) + '\n', encoding='utf-8')
    except OSError:
        pass


@contextmanager
def _quiet_process() -> Iterator[None]:
    """让这一趟进程安静地干活：禁掉后台调度器，退出时**复原**环境。

    ``app/setup.py:240`` 依 ``DISABLE_BACKGROUND_THREADS`` 决定要不要建 APScheduler。
    脚本是一次性进程，本就该关掉后台任务；但必须复原 —— 否则同进程内复用（单测里
    直接调 ``main()``）会把 ``DISABLE_BACKGROUND_THREADS=true`` 永久留在环境里，
    让后续 ``_start_background_tasks`` 静默不建调度器（回归：test_setup_extended
    的 5 个调度器用例全红）。
    """
    previous_threads = os.environ.get('DISABLE_BACKGROUND_THREADS')
    os.environ['DISABLE_BACKGROUND_THREADS'] = 'true'
    try:
        yield
    finally:
        if previous_threads is None:
            os.environ.pop('DISABLE_BACKGROUND_THREADS', None)
        else:
            os.environ['DISABLE_BACKGROUND_THREADS'] = previous_threads


def _silence_sql_echo() -> None:
    """关掉 SQL echo 噪音：development 配置把它写死为 True（``app/config.py:240``）。

    不关的话命中清单会被 SQL INFO 冲没（实测 dry-run 输出 0.4MB / 2000+ 行）。

    注意只能改**引擎**上的开关，改 ``sqlalchemy.engine.Engine`` 的 logger 等级无效：
    引擎是懒创建的，创建时的 ``set_echo`` 会把那个 logger 的等级重新设成 INFO。
    """
    from app.models.database import db

    db.engine.echo = False


@dataclass(frozen=True)
class EnglishSource:
    """一本书的英文简介，以及翻译时会用到「图书上下文」的元信息。"""

    description: str
    context: dict[str, str] = field(default_factory=dict)

    def as_context(self) -> dict[str, str] | None:
        """元信息为空时返回 None —— ``is_inflated_translation`` 只在有值时才走泄漏判定。"""
        return self.context or None


@dataclass(frozen=True)
class Hit:
    """一条待清理的记录。``translated`` 是 DB 里的原始译文，用于比对语言包是否同值。"""

    isbn: str
    title: str
    field_name: str
    source_text: str
    translated: str
    origin: str

    @property
    def ratio(self) -> float:
        return len(self.translated) / max(len(self.source_text), 1)


@dataclass
class Stats:
    scanned: int = 0
    hits: int = 0
    unresolved: int = 0
    cleared_db: int = 0
    cleared_pack: int = 0
    pack_mismatch: int = 0
    cleared_cache: int = 0
    failures: int = 0


def _first_isbn(payload: dict[str, Any]) -> str:
    for key in _ISBN_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def iter_book_entries(payload: Any, list_name: str = '') -> list[tuple[str, str, dict[str, str]]]:
    """递归遍历任意 API 响应 / 缓存 JSON，产出 ``(isbn, 英文简介, 元信息)``。

    NYT 榜单响应是 ``{"results": {"list_name": ..., "books": [...]}}``，
    仓库里的 API 快照是 ``{"value": [...]}``，两种形状都由同一次递归覆盖。
    ``list_name`` 由最近的祖先节点继承（NYT 把它放在 ``results`` 上，不在书里）。
    """
    found: list[tuple[str, str, dict[str, str]]] = []
    if isinstance(payload, dict):
        current_list = list_name
        raw_list = payload.get('list_name')
        if isinstance(raw_list, str) and raw_list.strip():
            current_list = raw_list.strip()

        description = payload.get(_DESCRIPTION_KEY)
        isbn = _first_isbn(payload)
        if isbn and isinstance(description, str) and description.strip():
            metadata = {
                key: payload[key].strip()
                for key in _CONTEXT_KEYS
                if isinstance(payload.get(key), str) and payload[key].strip()
            }
            if current_list and 'list_name' not in metadata:
                metadata['list_name'] = current_list
            found.append((isbn, description.strip(), metadata))

        for value in payload.values():
            found.extend(iter_book_entries(value, current_list))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(iter_book_entries(item, list_name))
    return found


def _merge_sources(target: dict[str, EnglishSource], entries: list[tuple[str, str, dict[str, str]]]) -> None:
    for isbn, description, metadata in entries:
        target.setdefault(isbn, EnglishSource(description=description, context=metadata))


def collect_english_sources(
    session: Any, cache_dir: Path | None = None, static_data_dir: Path | None = None
) -> dict[str, EnglishSource]:
    """汇总 ISBN → 英文简介。来源见模块 docstring；先到者优先。"""
    from app.models.new_book import NewBook
    from app.models.schemas import APICache

    sources: dict[str, EnglishSource] = {}

    # 1) NYT 原始榜单响应（线上把英文 description 存在这里）
    try:
        rows = session.query(APICache).filter(APICache.api_source == 'nyt').all()
    except Exception as exc:
        log_error(ErrorCategory.DB_QUERY, f'读取 APICache 失败，跳过该来源: {exc}', level='warning')
        rows = []
    for row in rows:
        try:
            payload = json.loads(row.response_data)
        except (TypeError, ValueError) as exc:
            log_error(ErrorCategory.CACHE, f'APICache #{row.id} 响应无法解析: {exc}', level='warning')
            continue
        _merge_sources(sources, iter_book_entries(payload))

    # 2) 仓库内的 API 快照 / 静态新书 JSON
    for directory in (cache_dir, static_data_dir):
        if not directory or not directory.is_dir():
            continue
        for path in sorted(directory.glob('*.json')):
            if path.name == 'all_books.json':
                continue
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                log_error(ErrorCategory.CACHE, f'读取快照 {path} 失败: {exc}', level='warning')
                continue
            _merge_sources(sources, iter_book_entries(payload))

    # 3) 新书表（出版社爬取来源，自带 description）
    try:
        new_books = session.query(NewBook).filter(NewBook.description.isnot(None)).all()
    except Exception as exc:
        log_error(ErrorCategory.DB_QUERY, f'读取 NewBook 失败，跳过该来源: {exc}', level='warning')
        new_books = []
    for book in new_books:
        isbn = str(book.isbn13 or book.isbn10 or '').strip()
        description = str(book.description or '').strip()
        if isbn and description:
            metadata = {key: str(getattr(book, key)).strip() for key in _CONTEXT_KEYS if getattr(book, key, None)}
            sources.setdefault(isbn, EnglishSource(description=description, context=metadata))

    return sources


def find_inflated_rows(
    session: Any,
    sources: dict[str, EnglishSource],
    limit: int = 0,
) -> tuple[list[Hit], Stats]:
    """扫描 ``book_metadata``，返回命中列表与统计（含无法判定的条数）。"""
    from app.models.schemas import BookMetadata

    stats = Stats()
    hits: list[Hit] = []
    query = session.query(BookMetadata).filter(
        (BookMetadata.description_zh.isnot(None)) | (BookMetadata.details_zh.isnot(None))
    )
    for row in query.all():
        stats.scanned += 1
        isbn = str(row.isbn or '').strip()
        title = str(row.title or '').strip()

        details_zh = str(row.details_zh or '').strip()
        if details_zh:
            source_text = str(row.details or '').strip()
            if is_inflated_translation(source_text, details_zh):
                hits.append(
                    Hit(
                        isbn=isbn,
                        title=title,
                        field_name='details_zh',
                        source_text=source_text,
                        translated=details_zh,
                        origin='book_metadata.details',
                    )
                )

        description_zh = str(row.description_zh or '').strip()
        if description_zh:
            source = sources.get(isbn)
            if source is None:
                # 没有英文原文就无法算比率，也不做任何猜测：留给人工核对
                stats.unresolved += 1
            elif is_inflated_translation(source.description, description_zh, source.as_context()):
                hits.append(
                    Hit(
                        isbn=isbn,
                        title=title,
                        field_name='description_zh',
                        source_text=source.description,
                        translated=description_zh,
                        origin='nyt/api_cache',
                    )
                )

        if limit and len(hits) >= limit:
            break

    stats.hits = len(hits)
    return hits, stats


def scrub_pack_document(pack_doc: dict[str, Any], hits: list[Hit]) -> tuple[int, int]:
    """从语言包文档里删掉命中的坏值，返回 ``(删除条数, 值不一致而被保留的条数)``。

    只在语言包里的值与 DB 里被判定的坏值**完全一致**时才删，避免误删已被人工修正的值。
    """
    books = pack_doc.get('books')
    if not isinstance(books, dict):
        return 0, 0

    removed = 0
    mismatch = 0
    for hit in hits:
        entry = books.get(hit.isbn)
        if not isinstance(entry, dict):
            continue
        if str(entry.get(hit.field_name) or '').strip() != hit.translated:
            if entry.get(hit.field_name):
                mismatch += 1
            continue
        del entry[hit.field_name]
        removed += 1
        if not entry:
            del books[hit.isbn]
    return removed, mismatch


def _write_pack_document(pack_path: Path, pack_doc: dict[str, Any]) -> None:
    """原子写回语言包（临时文件 + replace），保留文档其它字段。"""
    from datetime import UTC, datetime

    pack_doc['updated_at'] = datetime.now(UTC).isoformat()
    tmp_path = pack_path.with_name(f'{pack_path.name}.tmp')
    tmp_path.write_text(json.dumps(pack_doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp_path.replace(pack_path)


def _clear_translation_cache(session: Any, hit: Hit) -> int:
    """删掉英文原文对应的翻译缓存行 —— 否则 ``_apply_exact_text_cache`` 会把坏值读回来。"""
    from app.models.schemas import TranslationCache
    from app.services.translation_cache_service import TranslationCacheService

    if not hit.source_text:
        return 0
    source_hash = TranslationCacheService._compute_source_hash(hit.source_text)
    deleted = (
        session.query(TranslationCache)
        .filter(
            TranslationCache.source_hash == source_hash,
            TranslationCache.source_lang == 'en',
            TranslationCache.target_lang == 'zh',
        )
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)


def apply_clears(
    session: Any,
    hits: list[Hit],
    stats: Stats,
    pack_path: Path | None = None,
    clear_pack: bool = True,
    clear_cache: bool = True,
) -> Stats:
    """逐条清空：DB 置 NULL → 翻译缓存删行 → 语言包删字段（最后一次原子写回）。"""
    from app.models.schemas import BookMetadata

    for hit in hits:
        try:
            row = session.get(BookMetadata, hit.isbn)
            if row is None:
                continue

            if clear_cache:
                stats.cleared_cache += _clear_translation_cache(session, hit)

            setattr(row, hit.field_name, None)
            session.commit()
            stats.cleared_db += 1
            emit(
                f'  🧹 {hit.isbn} {hit.title[:32]} [{hit.field_name}] '
                f'{len(hit.source_text)}→{len(hit.translated)} 字符（{hit.ratio:.2f}×）已清空'
            )
        except Exception as exc:
            session.rollback()
            stats.failures += 1
            log_error(
                ErrorCategory.DB_QUERY,
                f'清空 {hit.isbn}.{hit.field_name} 失败: {exc}',
                exc_info=True,
            )
            emit(f'  ✗ {hit.isbn} {hit.field_name} 清空失败：{type(exc).__name__}: {exc}')

    if clear_pack and pack_path and pack_path.exists():
        try:
            pack_doc = json.loads(pack_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            stats.failures += 1
            log_error(ErrorCategory.CACHE, f'读取语言包 {pack_path} 失败: {exc}', level='warning')
            pack_doc = None
        if isinstance(pack_doc, dict):
            stats.cleared_pack, stats.pack_mismatch = scrub_pack_document(pack_doc, hits)
            if stats.cleared_pack:
                try:
                    _write_pack_document(pack_path, pack_doc)
                except OSError as exc:
                    stats.failures += 1
                    log_error(ErrorCategory.CACHE, f'写回语言包 {pack_path} 失败: {exc}', level='warning')

    return stats


def _report_dry_run(hits: list[Hit], stats: Stats, pack_path: Path | None, clear_pack: bool) -> None:
    emit(f'命中 {stats.hits} 条（扫描 {stats.scanned} 行，缺少英文原文 {stats.unresolved} 行）：')
    emit('-' * 78)
    emit(f'{"ISBN":<15}{"字段":<17}{"en":>5}{"zh":>6}{"倍数":>8}  书名')
    for hit in hits:
        emit(
            f'{hit.isbn:<15}{hit.field_name:<17}{len(hit.source_text):>5}{len(hit.translated):>6}'
            f'{hit.ratio:>7.2f}×  {hit.title[:34]}'
        )
    emit('-' * 78)
    if clear_pack and pack_path and pack_path.exists():
        try:
            pack_doc = json.loads(pack_path.read_text(encoding='utf-8'))
            removed, mismatch = scrub_pack_document(json.loads(json.dumps(pack_doc)), hits)
            emit(f'语言包 {pack_path.name}：将删除 {removed} 条同值坏值，另有 {mismatch} 条与 DB 不同值（保留）。')
        except (OSError, ValueError) as exc:
            emit(f'语言包预演失败（未写入）：{exc}')
    if stats.unresolved:
        emit(f'⚠️ {stats.unresolved} 行有中文简介但找不到英文原文，已跳过（未做任何判定）。')
    emit('\n（dry-run：未写库、未改语言包、未删缓存。加 --apply 才执行）')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='清空被上下文注水的中文简介/详情')
    parser.add_argument('--apply', action='store_true', help='真正写入（默认只预演，不写任何东西）')
    parser.add_argument('--only-db', action='store_true', help='只清 book_metadata，不动语言包与翻译缓存')
    parser.add_argument('--limit', type=int, default=0, help='最多处理多少条命中（0 = 不限）')
    parser.add_argument('--pack', default=PACK_DEFAULT, help='语言包 JSON 路径')
    parser.add_argument('--cache-dir', default=CACHE_DIR_DEFAULT, help='上游 API 快照目录（英文原文来源）')
    parser.add_argument('--static-data-dir', default=STATIC_DATA_DIR_DEFAULT, help='静态新书 JSON 目录（英文原文来源）')
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / '.env')
    logging.getLogger().setLevel(logging.WARNING)

    from app import create_app
    from app.models.database import db

    pack_path = (ROOT / args.pack).resolve()

    with _quiet_process():
        app = create_app(os.environ.get('FLASK_ENV') or 'development')
        with app.app_context():
            _silence_sql_echo()
            sources = collect_english_sources(
                db.session,
                cache_dir=(ROOT / args.cache_dir).resolve(),
                static_data_dir=(ROOT / args.static_data_dir).resolve(),
            )
            emit(f'英文原文来源：{len(sources)} 本（api_cache/nyt + 快照 + new_books）')
            hits, stats = find_inflated_rows(db.session, sources, limit=args.limit)

            if not hits:
                emit(f'✅ 未发现注水译文（扫描 {stats.scanned} 行，缺英文原文 {stats.unresolved} 行）。')
                return 0

            if not args.apply:
                _report_dry_run(hits, stats, pack_path, clear_pack=not args.only_db)
                return 2

            stats = apply_clears(
                db.session,
                hits,
                stats,
                pack_path=pack_path,
                clear_pack=not args.only_db,
                clear_cache=not args.only_db,
            )
            emit('-' * 78)
            emit(
                f'扫描 {stats.scanned} 行 / 命中 {stats.hits} 条 / 清空 DB {stats.cleared_db} 条 / '
                f'语言包 {stats.cleared_pack} 条（保留 {stats.pack_mismatch} 条不同值）/ '
                f'翻译缓存 {stats.cleared_cache} 行 / 失败 {stats.failures} 条'
            )
            if stats.unresolved:
                emit(f'⚠️ 另有 {stats.unresolved} 行因缺英文原文未判定，需人工核对。')
            emit('提示：清空后需等下一次同步/翻译流程重新生成，见模块 docstring。')
            return 0 if stats.failures == 0 else 1


if __name__ == '__main__':
    try:
        exit_code = main()
    finally:
        flush_log()
    sys.exit(exit_code)
