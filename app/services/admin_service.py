"""Admin batch operations service layer."""

import logging

from ..models.database import db

logger = logging.getLogger(__name__)


def batch_update_categories(id_to_category: dict[int, str]) -> int:
    """批量更新 NewBook 分类，返回更新条数"""
    from ..models.new_book import NewBook

    books = db.session.query(NewBook).filter(NewBook.id.in_(list(id_to_category.keys()))).all()  # type: ignore[attr-defined]
    for book in books:
        book.category = id_to_category[book.id]
    db.session.commit()
    return len(books)


def get_weekly_report_by_id(report_id: int):
    """获取周报记录"""
    from ..models.schemas import WeeklyReport

    return db.session.get(WeeklyReport, report_id)


def update_translation_cache_records(t_ids: list[int], fix_fn) -> int:
    """批量更新翻译缓存记录"""
    from ..models.schemas import TranslationCache

    if not t_ids:
        return 0
    records = db.session.query(TranslationCache).filter(TranslationCache.id.in_(t_ids)).all()
    for record in records:
        fix_fn(record)
    return len(records)


def update_book_metadata_records(isbn_list: list[str], fix_fn) -> int:
    """批量更新书目元数据记录"""
    from ..models.schemas import BookMetadata

    if not isbn_list:
        return 0
    records = db.session.query(BookMetadata).filter(BookMetadata.isbn.in_(isbn_list)).all()
    for record in records:
        fix_fn(record)
    return len(records)


def batch_commit() -> None:
    """提交当前事务"""
    db.session.commit()


def rollback() -> None:
    """回滚当前事务"""
    db.session.rollback()


def batch_import_from_dict(table_models: dict[str, type], tables_data: dict) -> dict[str, int]:
    """从字典数据批量导入"""
    imported_counts: dict[str, int] = {}
    for table_name, records_data in tables_data.items():
        model = table_models.get(table_name)
        if not model:
            continue

        records = records_data.get('records', []) if isinstance(records_data, dict) else records_data
        count = 0
        for record in records:
            record.pop('id', None)
            record.pop('created_at', None)
            record.pop('updated_at', None)
            try:
                obj = model(**record)
                db.session.add(obj)
                count += 1
            except Exception:
                db.session.rollback()
                continue

        imported_counts[table_name] = count

    db.session.commit()
    return imported_counts
