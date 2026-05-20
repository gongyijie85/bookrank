"""
Render 部署启动入口（免费版优化版）

优化点：
1. 惰性数据库初始化（第一次请求时执行，减少冷启动时间）
2. 减少启动时的数据库查询次数
3. 缩短连接超时，适应 Render 免费版限制
"""
import os
import logging
import threading

from sqlalchemy import inspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app import app, db

_db_init_lock = threading.Lock()
_db_initialized = False

HEALTH_CHECK_PATHS = {
    '/api/health',
    '/health',
    '/health/detailed',
    '/health/ready',
}


def _cleanup_dirty_translations():
    """一次性清理数据库中残留的翻译脏数据（如末尾'译'字、Markdown标记等）"""
    try:
        from app.utils.api_helpers import clean_translation_text
        import re

        count = 0

        from app.models.schemas import BookMetadata, AwardBook
        for Model in (BookMetadata, AwardBook):
            try:
                records = Model.query.filter(Model.title_zh.isnot(None)).all()
                for record in records:
                    original = record.title_zh
                    cleaned = clean_translation_text(original, 'title')
                    if cleaned != original:
                        record.title_zh = cleaned
                        count += 1
            except Exception:
                pass

        from app.models.new_book import NewBook
        try:
            records = NewBook.query.filter(NewBook.title_zh.isnot(None)).all()
            for record in records:
                original = record.title_zh
                cleaned = clean_translation_text(original, 'title')
                if cleaned != original:
                    record.title_zh = cleaned
                    count += 1
        except Exception:
            pass

        if count > 0:
            db.session.commit()
            logger.info(f"翻译脏数据清理完成: 修复 {count} 条记录")
        else:
            logger.info("翻译数据干净，无需清理")
    except Exception as e:
        logger.warning(f"翻译脏数据清理跳过: {e}")
        db.session.rollback()


def _run_migrations():
    """运行数据库迁移（先检查是否已有迁移记录，避免重复执行）

    调用方需确保已在 app.app_context() 内。
    """
    try:
        result = db.session.execute(
            db.text("SELECT version_num FROM alembic_version")
        ).fetchone()
        if result:
            from flask_migrate import upgrade as _upgrade

            _upgrade()
            logger.info(f"数据库迁移已是最新版本: {result[0]}")
            return True
    except Exception:
        db.session.rollback()
        logger.info("alembic_version 表不存在，需要检查当前 schema")

    has_app_tables, schema_is_current = _inspect_schema_state()
    if schema_is_current:
        return _stamp_current_schema("现有 schema 已完整，写入 Alembic 版本")

    if not has_app_tables:
        try:
            db.create_all()
            return _stamp_current_schema("新数据库已按当前模型创建，写入 Alembic 版本")
        except Exception as e:
            db.session.rollback()
            logger.warning(f"按模型创建数据库失败: {e}")

    try:
        from flask_migrate import upgrade as _upgrade
        _upgrade()
        logger.info("数据库迁移完成")
        return True
    except Exception as e:
        db.session.rollback()
        logger.warning(f"迁移失败: {e}")
        return False


def _inspect_schema_state():
    """检查当前数据库是否已具备模型要求的表和字段。"""
    try:
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        model_tables = set(db.metadata.tables.keys())
        has_app_tables = bool(existing_tables & model_tables)

        if not model_tables.issubset(existing_tables):
            return has_app_tables, False

        for table_name, table in db.metadata.tables.items():
            existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
            expected_columns = set(table.columns.keys())
            if not expected_columns.issubset(existing_columns):
                return has_app_tables, False

        return has_app_tables, True
    except Exception as e:
        logger.warning(f"检查数据库 schema 失败: {e}")
        return False, False


def _stamp_current_schema(reason):
    """把已存在的当前 schema 标记为 Alembic head。"""
    try:
        from flask_migrate import stamp as _stamp

        _stamp(revision='head')
        logger.info(reason)
        return True
    except Exception as e:
        db.session.rollback()
        logger.warning(f"写入 Alembic 版本失败: {e}")
        return False


def _init_database_lazy():
    """惰性初始化数据库（线程安全双重检查锁）"""
    global _db_initialized
    if _db_initialized:
        return

    with _db_init_lock:
        if _db_initialized:
            return

        with app.app_context():
            logger.info("首次请求，初始化数据库...")

            if not _run_migrations():
                try:
                    db.create_all()
                    logger.info("使用 create_all 创建表")
                except Exception as e:
                    logger.error(f"创建表失败: {e}")

            try:
                from app.models.schemas import Award
                from app.models.new_book import Publisher
                from app.initialization import init_awards_data

                if db.session.query(Award).count() == 0:
                    logger.info("初始化奖项数据...")
                    init_awards_data(app)

                if db.session.query(Publisher).count() == 0:
                    logger.info("初始化出版社数据...")
                    from app.services.new_book_service import NewBookService
                    service = NewBookService()
                    service.init_publishers()

            except Exception as e:
                logger.warning(f"基础数据初始化跳过: {e}")

            _cleanup_dirty_translations()

            _db_initialized = True
            logger.info("数据库初始化完成")


@app.before_request
def _ensure_db_ready():
    """确保数据库已初始化（惰性）"""
    from flask import request

    if request.path in HEALTH_CHECK_PATHS or request.path.startswith('/static/'):
        return

    _init_database_lazy()


application = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
