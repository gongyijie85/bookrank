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


def batch_import_from_dict(
    table_models: dict[str, type],
    tables_data: dict,
    max_records_per_table: int = 50000,
) -> dict[str, int]:
    """从字典数据批量导入（带 schema 验证）

    安全约束：
    - 表名必须在白名单 table_models 中（调用方控制白名单）
    - 字段必须存在于模型列定义中（自动剔除未知字段，防止注入未受控字段）
    - 每张表最多导入 max_records_per_table 条，防止单次请求耗尽内存/磁盘
    - 输入必须是 dict 或包含 records 的 dict；非法记录被跳过
    """
    if not isinstance(tables_data, dict):
        raise ValueError('tables_data 必须是 dict')

    imported_counts: dict[str, int] = {}
    for table_name, records_data in tables_data.items():
        model = table_models.get(table_name)
        if not model:
            logger.warning(f'跳过非白名单表: {table_name}')
            continue

        # 抽取记录列表
        if isinstance(records_data, dict):
            records = records_data.get('records', [])
        elif isinstance(records_data, list):
            records = records_data
        else:
            logger.warning(f'表 {table_name} 数据格式无效，跳过')
            continue

        if not isinstance(records, list):
            logger.warning(f'表 {table_name} records 必须是 list，跳过')
            continue

        # 数量限制
        if len(records) > max_records_per_table:
            logger.warning(f'表 {table_name} 记录数 {len(records)} 超过上限 {max_records_per_table}，截断')
            records = records[:max_records_per_table]

        # 提取模型的合法列名作为字段白名单
        allowed_fields = _get_model_columns(model)
        # 强制排除的字段（自增/时间戳）
        blocked_fields = {'id', 'created_at', 'updated_at'}

        count = 0
        for record in records:
            if not isinstance(record, dict):
                continue

            # 仅保留白名单字段
            cleaned = {k: v for k, v in record.items() if k in allowed_fields and k not in blocked_fields}
            if not cleaned:
                continue

            try:
                obj = model(**cleaned)
                db.session.add(obj)
                count += 1
            except Exception as e:
                logger.debug(f'导入 {table_name} 记录失败: {e}')
                db.session.rollback()
                continue

        imported_counts[table_name] = count

    db.session.commit()
    return imported_counts


def _get_model_columns(model: type) -> set[str]:
    """提取 SQLAlchemy 模型的所有列名（用作字段白名单）"""
    try:
        table = getattr(model, '__table__', None)
        if table is None:
            return set()
        return {col.name for col in table.columns}
    except Exception:
        return set()
