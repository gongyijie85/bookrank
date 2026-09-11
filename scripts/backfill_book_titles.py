"""补齐 NYT 榜单缺失的中文书名（一次性回填工具）。

用途
----
页面中文模式下，书名缺失 ``title_zh`` 时会回退显示英文原文（见 templates/index.html）。
静态语言包 ``static/data/book_language_pack.zh.json`` 是部署态（HF Space）实际读取的来源，
一旦某本书在包内查不到，线上就会持续显示英文。

本脚本扫描所有 NYT 分类榜，找出缺失中文书名的书，调用既有翻译服务补齐，
并同时写入两处持久层：

1. ``static/data/book_language_pack.zh.json``（部署态直接生效，随仓库提交）
2. ``book_metadata`` 表（跨重启的权威持久层）

两处写入均复用 ``BookLanguagePack.translate_and_store_books``，不新增写入路径。

用法::

    python scripts/backfill_book_titles.py --dry-run     # 只列出待补书籍，不调 API
    python scripts/backfill_book_titles.py               # 补齐书名 + 简介
    python scripts/backfill_book_titles.py --with-details  # 连详情一起补（较慢）

退出码：0 = 无缺失；2 = --dry-run 且存在待补项；1 = 翻译失败仍有遗留。避免中文输出被
终端编码破坏，诊断详情同时写入 ``.scratch/backfill_titles.log``（该目录已被 git 忽略）。
"""

import argparse
import logging
import os
import sys
from typing import Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.services.zhipu_translation_service import get_translation_service
from app.utils.service_helpers import get_service

# 翻译服务自身的进度日志会淹没脚本输出，收敛到 WARNING
logging.getLogger().setLevel(logging.WARNING)

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.scratch', 'backfill_titles.log')
_log_lines: list[str] = []


def emit(message: str = '') -> None:
    """同时写终端与日志文件；终端编码异常时不影响记录，也不影响退出码。"""
    _log_lines.append(message)
    try:
        print(message)
    except UnicodeEncodeError:
        # GBK 等窄编码终端：降级为 ASCII 替换输出。降级路径本身也必须不抛异常，
        # 否则会在 finally 里把正常路径的退出码污染成 1（实测踩过）。
        try:
            print(message.encode('ascii', 'replace').decode('ascii'))
        except Exception:
            pass


def flush_log() -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(_log_lines) + '\n')
    except OSError:
        pass


def _has_cjk(text: Any) -> bool:
    """判断译文是否真的含中文，挡住模型原样回显英文的情况。"""
    return any('\u4e00' <= ch <= '\u9fff' for ch in str(text or ''))


# 语言标记类噪音：实测 details_zh 里出现 88 例（占 details 有值条的 31%），
# 取值就是「原文语言名」本身，无任何信息量（如 details_zh='英文'）。
_LANGUAGE_MARKER_NOISE = frozenset({'英文', '英语', '中文', '汉语', '- 英文', '-英文', '英文。', '英语。'})

# 已知无信息量的占位值
_PLACEHOLDER_NOISE = frozenset({'暂无详细描述', '暂无简介', '无', '-', '--', 'N/A', '小说'})


def _is_noise_value(value: Any) -> bool:
    """判断 details_zh 的值是否为无信息量的噪音。

    只匹配明确的语言标记与占位符，不做长度启发式：
    实测 ``>30`` 字的 details_zh 全部正常，而 ``<=5`` 字恰好全是噪音，
    两者之间只有 2 例正常值，说明用显式集合比按长度裁剪更安全。
    """
    return str(value or '').strip() in (_LANGUAGE_MARKER_NOISE | _PLACEHOLDER_NOISE)


def _book_isbn(book: Any) -> str:
    return str(getattr(book, 'isbn13', None) or getattr(book, 'isbn10', None) or '')


def _read_pack_document() -> dict[str, Any]:
    """从磁盘直接读取静态语言包（绕过服务内缓存，用于复核写入结果）。"""
    import json
    from pathlib import Path

    pack_path = Path('static/data/book_language_pack.zh.json')
    if not pack_path.exists():
        return {}
    try:
        raw = json.loads(pack_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_pack_document(doc: dict[str, Any]) -> None:
    """把语言包写回磁盘（临时文件 + 原子替换，保留文档其它字段）。"""
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    pack_path = Path('static/data/book_language_pack.zh.json')
    doc['updated_at'] = datetime.now(UTC).isoformat()
    tmp_path = pack_path.with_name(f'{pack_path.name}.tmp')
    tmp_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp_path.replace(pack_path)


def collect_missing(book_service: Any, categories: dict[str, str]) -> list[Any]:
    """遍历全部分类榜，返回缺少中文书名的书（按 ISBN 去重）。

    同时纳入两类“伪已翻译”条目：语言包里的 title_zh 不含中文，或与英文原书名一致。
    实测存在模型把 Source 原样回显的情况（如 SCION → SCION），这类值会让页面继续显示
    英文，必须按缺失处理并重新翻译。
    """
    seen: set[str] = set()
    missing: list[Any] = []
    for category_id, category_name in categories.items():
        try:
            books = book_service.get_books_by_category(category_id, auto_translate=False, notify_refresh=False)
        except Exception as exc:
            emit(f'  ⚠️ 分类 {category_name} ({category_id}) 获取失败：{exc}')
            continue
        for book in books or []:
            isbn = _book_isbn(book)
            if not isbn or isbn in seen:
                continue
            title_zh = str(getattr(book, 'title_zh', None) or '').strip()
            title_en = str(getattr(book, 'title', None) or '').strip()
            if not title_zh or not _has_cjk(title_zh) or title_zh.casefold() == title_en.casefold():
                seen.add(isbn)
                missing.append(book)
    return missing


def _translate_title_directly(translator: Any, book: Any, retries: int) -> str:
    """用单字段路径翻译书名；这是应对模型英文回显的兜底。

    实测：合并 JSON 路径（translate_book_info → translate_book_fields）对个别短书名会
    原样回显英文（如 SCION → "Scion"），而同一文本走单字段 translate() 稳定返回中文
    （SCION → 后裔）。因此回显时清空 title_zh 改用单字段路径。
    """
    import time

    for attempt in range(1, retries + 1):
        try:
            translated = translator.translate(book.title, 'en', 'zh', field_type='title', context=book.to_dict())
        except Exception as exc:
            emit(f'      ↻ 单字段翻译异常：{type(exc).__name__}: {exc}')
            translated = None
        if translated and _has_cjk(translated):
            if attempt > 1:
                emit(f'      ✓ 单字段路径第 {attempt} 次成功')
            return str(translated)
        if attempt < retries:
            time.sleep(2**attempt)
    return ''


def _translate_one_book(
    pack: Any,
    translator: Any,
    book: Any,
    fields: tuple[str, ...],
    book_service: Any,
    retries: int,
) -> dict[str, int]:
    """翻译单本并写入语言包/元数据；瞬时失败按指数退避重试。

    使用 force=True 重新翻译，而不是先清空字段：清空会让长简介反复重译，
    既慢又浪费 API 配额（实测会导致脚本超时）。force 保留既有值，只覆盖译文。
    回显场景（SCION → "Scion"）再走单字段路径兜底。
    """
    import time

    last_stats: dict[str, int] = {}
    title_en = str(getattr(book, 'title', None) or '').strip()

    def title_is_bad() -> bool:
        value = str(getattr(book, 'title_zh', None) or '').strip()
        # 英文回显（SCION → Scion）比空值更糟：页面会继续显示英文，必须按失败处理
        return not _has_cjk(value) or value.casefold() == title_en.casefold()

    for attempt in range(1, retries + 1):
        try:
            last_stats = pack.translate_and_store_books(
                [book],
                translator=translator,
                save_metadata=book_service.save_book_translation,
                force=True,
            )
        except Exception as exc:
            last_stats = {'error': 0, 'failures': 1}
            emit(f'      ↻ 第 {attempt} 次异常：{type(exc).__name__}: {exc}')

        if not title_is_bad():
            if attempt > 1:
                emit(f'      ✓ 第 {attempt} 次尝试成功')
            return last_stats

        # 合并路径回显英文时，改走单字段路径补齐书名
        if 'title' in fields and getattr(book, 'title', None):
            direct = _translate_title_directly(translator, book, retries)
            if direct:
                book.title_zh = direct
                pack.translate_and_store_books(
                    [book],
                    translator=None,  # 只把已有翻译写进语言包，不再调 API
                    save_metadata=book_service.save_book_translation,
                )
                if not title_is_bad():
                    emit('      ✓ 经单字段路径补齐书名')
                    return last_stats

        if attempt < retries:
            emit(f'      ↻ 第 {attempt} 次未取到有效中文书名，退避后重试')
            time.sleep(2**attempt)
    return last_stats


def _apply_upstream_guards(book_service: Any, categories: dict[str, str]) -> int:
    """扫描全部榜单，丢弃 details_zh 里的语言标记噪音，返回清理条数。

    实测语言包里 88 条 details_zh 是「原文语言名」本身（'英文' / '- 英文' / '小说'），
    占 details 有值条的 31%，其中 32 本当时正在榜上。这类值源于 details 源文本本身
    即语言标记（模型忠实翻译所致），无任何信息量。

    只清噪音值、**保留英文 details 原文**，页面因此不再渲染「详情: 英文」。
    本函数幂等：可在缺书名时提前返回之前调用，从而只清数据而不触发任何翻译 API。
    """
    cleaned = 0
    for category_id in categories:
        try:
            books = book_service.get_books_by_category(category_id, auto_translate=False, notify_refresh=False)
        except Exception:
            continue
        for book in books or []:
            noise = getattr(book, 'details_zh', None)
            if not noise or not _is_noise_value(noise):
                continue
            isbn = _book_isbn(book)
            book.details_zh = None
            if isbn:
                try:
                    book_service.save_book_translation(isbn=isbn, details_zh=None)
                except Exception:
                    pass
            emit(f'  🧹 清除噪音 details_zh: {isbn} {str(noise)!r}')
            cleaned += 1
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description='补齐缺失的中文书名')
    parser.add_argument('--dry-run', action='store_true', help='只列出待补书籍，不调用翻译 API')
    parser.add_argument('--with-details', action='store_true', help='连详情字段一起补（较慢，API 调用更多）')
    parser.add_argument('--limit', type=int, default=0, help='最多处理多少本（0 = 不限）')
    parser.add_argument('--retries', type=int, default=3, help='单本失败重试次数（默认 3，应对 API 抖动）')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        book_service = get_service('book_service')
        if not book_service:
            emit('错误：无法获取 book_service')
            return 1

        categories = app.config.get('CATEGORIES', {})
        translator = get_translation_service(app=app)
        pack = book_service._language_pack

        emit('=' * 64)
        emit('上游数据守卫：清除 details_zh 的语言标记噪音')
        emit('=' * 64)
        noise_count = _apply_upstream_guards(book_service, categories)

        # 语言包是独立的一份数据：上面只清了内存里的 Book 对象与 book_metadata，
        # 盘上的包仍需同步剔除噪音，否则线上渲染仍会读到坏值。
        pack_doc = _read_pack_document()
        pack_books = pack_doc.get('books', {}) if isinstance(pack_doc, dict) else {}
        pack_noise = 0
        for entry in pack_books.values():
            if isinstance(entry, dict) and _is_noise_value(entry.get('details_zh')):
                del entry['details_zh']
                pack_noise += 1
        if pack_noise:
            _write_pack_document(pack_doc)

        emit(f'共清除 {noise_count} 条噪音 details_zh（语言包内另剔除 {pack_noise} 条）。\n')

        emit('=' * 64)
        emit('扫描全部 NYT 分类榜，查找缺少中文书名的书')
        emit('=' * 64)

        missing = collect_missing(book_service, categories)
        if args.limit:
            missing = missing[: args.limit]

        emit(f'\n共发现 {len(missing)} 本缺中文书名的书：')
        for book in missing:
            emit(f'  · {_book_isbn(book)}  {book.title}')

        if not missing:
            emit('\n✅ 无缺失，无需回填。')
            return 0

        if args.dry_run:
            emit('\n（--dry-run：未调用翻译 API，未写入任何文件）')
            return 2

        if not translator.is_available():
            emit('\n错误：翻译服务不可用（检查 SILICONFLOW_API_KEY / ZHIPU_API_KEY 配置）')
            return 1

        # 只补 title/description；details 往往数千字，按需开启
        fields = ('title', 'description', 'details') if args.with_details else ('title', 'description')

        emit(f'\n开始回填（字段：{"、".join(fields)}）…')
        emit('-' * 64)

        filled = 0
        failed: list[tuple[str, str]] = []
        for index, book in enumerate(missing, start=1):
            isbn = _book_isbn(book)
            title_before = book.title
            stats = _translate_one_book(pack, translator, book, fields, book_service, args.retries)

            title_after = str(getattr(book, 'title_zh', None) or '').strip()
            if _has_cjk(title_after):
                filled += 1
                emit(
                    f'  [{index}/{len(missing)}] {title_before} → {title_after}'
                    f'  （翻译字段 {stats.get("fields_translated", 0)} 个）'
                )
            else:
                failed.append((isbn, title_before))
                emit(
                    f'  [{index}/{len(missing)}] {title_before} → ✗ 未取得有效中文书名'
                    f'  （重试 {stats.get("attempts", 1)} 次，失败计数 {stats.get("failures", 0)}）'
                )

        emit('-' * 64)
        emit(f'成功补齐：{filled} / {len(missing)}')
        if failed:
            emit(f'仍缺中文书名：{len(failed)} 本')
            for isbn, title in failed:
                emit(f'  · {isbn}  {title}')

        # 复核：直接重新读盘，确认写入落地（不走服务缓存）
        pack_doc = _read_pack_document()
        pack_books = pack_doc.get('books', {}) if isinstance(pack_doc, dict) else {}
        hit = sum(1 for b in missing if _book_isbn(b) in pack_books)
        left_junk = sum(
            1
            for e in pack_books.values()
            if isinstance(e, dict) and str(e.get('details_zh') or '').strip() in ('英文', '- 英文', '小说')
        )
        emit(
            f'\n语言包复核：磁盘 {len(pack_books)} 条；本次目标命中 {hit} / {len(missing)} 本；'
            f'残留英文 details_zh {left_junk} 条（updated_at={pack_doc.get("updated_at", "?")}）'
        )

        return 0 if not failed and not left_junk else 1


if __name__ == '__main__':
    try:
        exit_code = main()
    finally:
        flush_log()
    sys.exit(exit_code)
