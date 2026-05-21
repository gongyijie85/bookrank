"""
应用服务初始化和后台任务管理

从 app/__init__.py 拆分出来，降低主模块复杂度
使用 APScheduler 替代 daemon 线程，确保任务可管理和优雅关闭。
"""

import logging
import os
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .models.schemas import SystemConfig
from .services import (
    BookService,
    CacheService,
    FileCache,
    GoogleBooksClient,
    ImageCacheService,
    MemoryCache,
    NYTApiClient,
)
from .utils import RateLimiter

logger = logging.getLogger(__name__)

# 全局调度器实例（应用生命周期内共享）
_scheduler: BackgroundScheduler | None = None


def init_services(app):
    """初始化业务服务（带容错：单个服务失败不影响其他服务）"""
    cfg = app.config

    memory_cache = MemoryCache(
        default_ttl=cfg['MEMORY_CACHE_TTL'],
        max_size=cfg.get('MEMORY_CACHE_MAX_SIZE', 1000),
    )
    file_cache = FileCache(cache_dir=cfg['CACHE_DIR'], default_ttl=cfg['CACHE_DEFAULT_TIMEOUT'])
    cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
    app.extensions['cache_service'] = cache_service
    app.logger.info('缓存服务初始化成功')

    nyt_client = _init_nyt_client(cfg, app)
    google_client = _init_google_client(cfg, app)
    image_cache = _init_image_cache(cfg, app)
    if image_cache:
        app.extensions['image_cache_service'] = image_cache
    translation_service = _init_translation_service(app)

    book_service = _init_book_service(nyt_client, google_client, cache_service, image_cache, app, cfg)

    _start_background_tasks(app, book_service, translation_service, google_client)


def _init_nyt_client(cfg, app):
    """初始化 NYT API 客户端"""
    try:
        rate_limiter = RateLimiter(max_calls=cfg['API_RATE_LIMIT'], window_seconds=cfg['API_RATE_LIMIT_WINDOW'])
        client = NYTApiClient(
            api_key=cfg.get('NYT_API_KEY', ''),
            base_url=cfg['NYT_API_BASE_URL'],
            rate_limiter=rate_limiter,
            timeout=cfg.get('API_TIMEOUT', 15),
            cache_ttl=cfg.get('NYT_CACHE_TTL', 86400 * 7),
        )
        app.logger.info('NYT API 客户端初始化成功')
        return client
    except Exception as e:
        app.logger.warning(f'NYT API 客户端初始化失败: {e}')
        return None


def _init_google_client(cfg, app):
    """初始化 Google Books API 客户端"""
    try:
        client = GoogleBooksClient(
            api_key=cfg.get('GOOGLE_API_KEY'),
            base_url=cfg['GOOGLE_BOOKS_API_URL'],
            timeout=cfg.get('API_TIMEOUT', 8),
            cache_ttl=cfg.get('GOOGLE_BOOKS_CACHE_TTL', 86400),
        )
        app.logger.info('Google Books 客户端初始化成功')
        return client
    except Exception as e:
        app.logger.warning(f'Google Books 客户端初始化失败: {e}')
        return None


def _init_image_cache(cfg, app):
    """初始化图片缓存服务"""
    try:
        return ImageCacheService(cache_dir=cfg['IMAGE_CACHE_DIR'], default_cover='/static/default-cover.png')
    except Exception as e:
        app.logger.warning(f'图片缓存服务初始化失败: {e}')
        return None


def _init_translation_service(app):
    """初始化翻译服务"""
    try:
        from .services.zhipu_translation_service import get_translation_service

        service = get_translation_service(app=app)
        app.extensions['translation_service'] = service
        return service
    except Exception as e:
        app.logger.warning(f'翻译服务初始化失败: {e}')
        return None


def _init_book_service(nyt_client, google_client, cache_service, image_cache, app, cfg):
    """初始化图书服务"""
    if not nyt_client or not cache_service:
        app.logger.warning('缺少 NYT 客户端或缓存服务，图书服务未初始化')
        return None

    try:
        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            app=app,
            max_workers=cfg['MAX_WORKERS'],
            categories=cfg['CATEGORIES'],
        )
        app.extensions['book_service'] = book_service

        def _trigger_weekly_report():
            with app.app_context():
                try:
                    from .tasks.weekly_report_task import generate_weekly_report

                    app.logger.info('排行榜数据刷新，检查是否需要生成周报...')
                    generate_weekly_report()
                except Exception as e:
                    app.logger.error(f'数据刷新触发周报生成失败: {e}')

        book_service.on_data_refreshed(_trigger_weekly_report)

        app.logger.info('图书服务初始化成功')
        return book_service
    except Exception as e:
        app.logger.error(f'图书服务初始化失败: {e}')
        return None


# ==================== APScheduler 后台任务管理 ====================


def _start_background_tasks(app, book_service, translation_service, google_client):
    """
    使用 APScheduler 启动后台任务（替代旧的 daemon 线程）

    优势:
    - 任务无丢失（进程退出前自动等待）
    - 错失执行有容错（misfire_grace_time）
    - 防止重复执行（max_instances=1）
    - 统一管理（可暂停/恢复/移除）
    """
    global _scheduler

    if app.config.get('TESTING'):
        app.logger.info('⏸️ 测试环境跳过后台任务调度器')
        return

    if os.environ.get('DISABLE_BACKGROUND_THREADS', '').lower() == 'true':
        app.logger.info('⏸️ 后台任务已禁用（DISABLE_BACKGROUND_THREADS=true）')
        return

    if _scheduler and _scheduler.running:
        app.logger.warning('调度器已在运行，跳过重复初始化')
        return

    is_render_free = os.environ.get('RENDER', '').lower() == 'true'
    initial_delay = 1800 if is_render_free else 300  # 30 分钟 / 5 分钟
    cover_sync_delay = 120 if is_render_free else 60

    _scheduler = BackgroundScheduler(
        daemon=False,  # 非 daemon：进程退出前等待任务完成
        job_defaults={
            'coalesce': True,  # 合并错过的执行
            'max_instances': 1,  # 防止重叠执行
            'misfire_grace_time': 3600,  # 1小时内错过的允许补执行
        },
    )

    now = datetime.now()

    # 1. 周报启动检查（一次性，延迟执行）
    if book_service:
        _scheduler.add_job(
            func=_scheduler_wrapper(app, _weekly_report_task),
            trigger=DateTrigger(run_date=now, timezone=UTC),
            id='weekly_report_init',
            name='周报启动检查',
        )
        # DateTrigger with run_date=now fires immediately; we want delay
        # Remove and re-add with proper delay
        _scheduler.remove_job('weekly_report_init')

        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _weekly_report_task),
            trigger=DateTrigger(run_date=now + timedelta(seconds=initial_delay), timezone=UTC),
            id='weekly_report_init',
            name='周报启动检查',
        )
        app.logger.info(f'📅 周报启动检查已安排（{initial_delay}秒后）')

    # 2. 新书速递自动同步（每14天一次）
    if translation_service:
        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _auto_sync_task),
            trigger=IntervalTrigger(days=14, start_date=now + timedelta(seconds=initial_delay * 2), timezone=UTC),
            id='auto_sync',
            name='新书速递自动同步',
        )
        app.logger.info(f'📅 新书速递自动同步已安排（每14天，首次{initial_delay * 2}秒后）')

    # 3. 获奖书籍封面同步（一次性，延迟执行）
    if google_client:
        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _cover_sync_task),
            trigger=DateTrigger(run_date=now + timedelta(seconds=cover_sync_delay), timezone=UTC),
            id='cover_sync_init',
            name='获奖书籍封面同步',
        )
        app.logger.info(f'📅 获奖书籍封面同步已安排（{cover_sync_delay}秒后）')

    # 4. 翻译缓存自动清理（每 30 分钟一次，避免限流中间件混杂非幂等副作用）
    if translation_service:
        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _translation_cache_cleanup_task),
            trigger=IntervalTrigger(minutes=30, start_date=now + timedelta(seconds=600), timezone=UTC),
            id='translation_cache_cleanup',
            name='翻译缓存自动清理',
        )
        app.logger.info('📅 翻译缓存自动清理已安排（每30分钟，首次600秒后）')

    _scheduler.start()
    app.logger.info('✅ APScheduler 后台任务调度器已启动')


def _scheduler_wrapper(app, task_func):
    """
    为 APScheduler job 创建包装函数
    - 自动创建 app context
    - 捕获所有异常（防止调度器崩溃）
    """

    def wrapper():
        try:
            with app.app_context():
                task_func(app)
        except Exception as e:
            app.logger.error(f'后台任务 [{task_func.__name__}] 失败: {e}', exc_info=True)

    wrapper.__name__ = task_func.__name__
    return wrapper


def _translation_cache_cleanup_task(app):
    """翻译缓存自动清理任务（替代旧的限流中间件副作用）"""
    try:
        with app.app_context():
            from .services.translation_cache_service import get_translation_cache_service

            cache_svc = get_translation_cache_service()
            if cache_svc:
                cache_svc.auto_cleanup(max_items=8000, keep_recent_days=30)
                app.logger.info('翻译缓存自动清理完成')
    except Exception as e:
        app.logger.warning(f'翻译缓存自动清理跳过: {e}')


def shutdown_scheduler(app):
    """优雅关闭调度器（在应用退出时调用）"""
    global _scheduler
    if _scheduler and _scheduler.running:
        app.logger.info('正在关闭 APScheduler...')
        _scheduler.shutdown(wait=True)
        _scheduler = None
        app.logger.info('✅ APScheduler 已关闭')


# ==================== 任务函数（与原实现一致） ====================


def _weekly_report_task(app):
    """周报自动生成任务"""
    try:
        from .tasks.weekly_report_task import generate_weekly_report

        app.logger.info('开始自动生成周报...')
        report = generate_weekly_report()
        if report:
            app.logger.info(f'周报生成成功: {report.title}')
        else:
            app.logger.warning('周报生成失败或已存在')
    except Exception as e:
        app.logger.error(f'自动生成周报失败: {e}', exc_info=True)
        _log_failure(app, 'last_report_failure')


def _auto_sync_task(app):
    """新书速递自动同步任务"""
    try:
        from .services.new_book_service import NewBookService

        service = NewBookService(translation_service=app.extensions.get('translation_service'))

        last_sync = SystemConfig.get_value('last_auto_sync_time')
        if last_sync:
            last_sync_time = datetime.fromisoformat(last_sync)
            if last_sync_time.tzinfo is None:
                last_sync_time = last_sync_time.replace(tzinfo=UTC)
            days_since = (datetime.now(UTC) - last_sync_time).days
            if days_since < 14:
                app.logger.info(f'距离上次同步仅 {days_since} 天，跳过')
                return

        app.logger.info('开始自动同步新书数据...')
        service.init_publishers()
        results = service.sync_all_publishers(max_books_per_publisher=15, batch_size=1)
        SystemConfig.set_value('last_auto_sync_time', datetime.now(UTC).isoformat())

        total_added = sum(r.get('added', 0) for r in results)
        total_updated = sum(r.get('updated', 0) for r in results)
        app.logger.info(f'自动同步完成：新增 {total_added} 本，更新 {total_updated} 本')

    except Exception as e:
        app.logger.error(f'自动同步失败: {e}', exc_info=True)
        _log_failure(app, 'last_sync_failure')


def _cover_sync_task(app):
    """获奖书籍封面自动同步任务"""
    try:
        from .services.award_cover_sync_service import AwardCoverSyncService

        app.logger.info('开始检查获奖书籍封面...')

        book_service = app.extensions.get('book_service')
        google_client = (
            book_service._google_client if book_service and hasattr(book_service, '_google_client') else None
        )

        if not google_client:
            from .config import Config
            from .services.google_books_client import GoogleBooksClient

            google_client = GoogleBooksClient(
                api_key=Config.GOOGLE_API_KEY, base_url='https://www.googleapis.com/books/v1/volumes'
            )

        sync_service = AwardCoverSyncService(
            google_client,
            image_cache=app.extensions.get('image_cache_service'),
        )

        result = sync_service.sync_missing_covers(batch_size=30, delay=0.5)

        if result.get('status') == 'success':
            app.logger.info(f'封面同步完成: 更新{result.get("updated", 0)}本, 跳过{result.get("skipped", 0)}本')
        elif result.get('status') == 'complete':
            app.logger.info('所有获奖书籍封面已完整')
        else:
            app.logger.warning(f'封面同步状态: {result.get("status")}')

    except Exception as e:
        app.logger.error(f'封面同步失败: {e}', exc_info=True)


def _log_failure(app, key: str):
    """记录失败时间到系统配置"""
    try:
        SystemConfig.set_value(key, datetime.now(UTC).isoformat())
    except Exception as log_error:
        app.logger.error(f'记录失败时间失败: {log_error}')
