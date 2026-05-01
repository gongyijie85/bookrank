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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app import app, db

_db_init_lock = threading.Lock()
_db_initialized = False


def _run_migrations():
    """运行数据库迁移（先检查是否已有迁移记录，避免重复执行）

    调用方需确保已在 app.app_context() 内。
    """
    try:
        result = db.session.execute(
            db.text("SELECT version_num FROM alembic_version")
        ).fetchone()
        if result:
            logger.info(f"数据库迁移已是最新版本: {result[0]}")
            return True
    except Exception:
        logger.info("alembic_version 表不存在，需要执行迁移")

    try:
        from flask_migrate import upgrade as _upgrade
        _upgrade()
        logger.info("数据库迁移完成")
        return True
    except Exception as e:
        logger.warning(f"迁移失败: {e}")
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

            _db_initialized = True
            logger.info("数据库初始化完成")


@app.before_request
def _ensure_db_ready():
    """确保数据库已初始化（惰性）"""
    _init_database_lazy()


application = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
