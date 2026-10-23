"""
Render 部署启动入口（免费版优化版）

优化点：
1. 生产请求不执行迁移或数据初始化；迁移由发布流程显式执行
2. 减少启动时的数据库查询次数
3. 缩短连接超时，适应 Render 免费版限制
"""

import logging
import os
import threading
from typing import Any, cast

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app import app, db
from app.utils.space_runtime import is_space_runtime

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

        count = 0

        from app.models.schemas import AwardBook, BookMetadata

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
            records = NewBook.query.filter(cast('Any', NewBook.title_zh).is_not(None)).all()
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
            logger.info(f'翻译脏数据清理完成: 修复 {count} 条记录')
        else:
            logger.info('翻译数据干净，无需清理')
    except Exception as e:
        logger.warning(f'翻译脏数据清理跳过: {e}')
        db.session.rollback()


def _run_migrations():
    """本地初始化使用的迁移；失败保留版本历史，不自动 stamp/create_all。"""
    try:
        if is_space_runtime():
            result = db.session.execute(db.text('SELECT version_num FROM alembic_version')).fetchone()
            if result:
                return True
        from flask_migrate import upgrade as _upgrade

        _upgrade()
        return True
    except Exception as exc:
        db.session.rollback()
        logger.warning('迁移失败，保留现有 schema 和迁移记录: %s', type(exc).__name__)
        return False


def _init_database_lazy():
    """惰性初始化数据库（线程安全双重检查锁）"""
    global _db_initialized
    if _db_initialized:
        return True

    with _db_init_lock:
        if _db_initialized:
            return True

        with app.app_context():
            logger.info('首次请求，初始化数据库...')

            try:
                from app.initialization import init_awards_data
                from app.models.new_book import Publisher
                from app.models.schemas import Award

                if db.session.query(Award).count() == 0:
                    logger.info('初始化奖项数据...')
                    init_awards_data(app)

                if db.session.query(Publisher).count() == 0:
                    logger.info('初始化出版社数据...')
                    from app.services.new_book import create_new_book_modules

                    modules = create_new_book_modules()
                    modules.publisher_manager.init_publishers()

            except Exception as e:
                db.session.rollback()
                logger.warning('基础数据初始化失败: %s', type(e).__name__)
                return False

            _db_initialized = True
            logger.info('数据库初始化完成')
            return True


@app.before_request
def _ensure_db_ready():
    """确保数据库已初始化（惰性）"""
    from flask import request

    if request.path in HEALTH_CHECK_PATHS or request.path.startswith('/static/'):
        return

    if app.config.get('APP_ENV') == 'production':
        return None

    if not _init_database_lazy():
        return {'success': False, 'error': 'database_initialization_failed'}, 503
    return None


application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
