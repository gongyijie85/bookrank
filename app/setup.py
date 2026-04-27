"""
应用服务初始化和后台线程管理

从 app/__init__.py 拆分出来，降低主模块复杂度
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone

from .models.schemas import SystemConfig
from .services import (
    CacheService, MemoryCache, FileCache,
    NYTApiClient, GoogleBooksClient, ImageCacheService,
    BookService
)
from .utils import RateLimiter

logger = logging.getLogger(__name__)


def init_services(app):
    """初始化业务服务（带容错：单个服务失败不影响其他服务）"""
    cfg = app.config

    memory_cache = MemoryCache(default_ttl=cfg['MEMORY_CACHE_TTL'], max_size=500)
    file_cache = FileCache(
        cache_dir=cfg['CACHE_DIR'],
        default_ttl=cfg['CACHE_DEFAULT_TIMEOUT']
    )
    cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
    app.logger.info("缓存服务初始化成功")

    nyt_client = _init_nyt_client(cfg, app)
    google_client = _init_google_client(cfg, app)
    image_cache = _init_image_cache(cfg, app)
    translation_service = _init_translation_service(app)

    book_service = _init_book_service(
        nyt_client, google_client, cache_service, image_cache, app, cfg
    )

    _start_background_threads(app, book_service, translation_service, google_client)


def _init_nyt_client(cfg, app):
    """初始化 NYT API 客户端"""
    try:
        rate_limiter = RateLimiter(
            max_calls=cfg['API_RATE_LIMIT'],
            window_seconds=cfg['API_RATE_LIMIT_WINDOW']
        )
        client = NYTApiClient(
            api_key=cfg.get('NYT_API_KEY', ''),
            base_url=cfg['NYT_API_BASE_URL'],
            rate_limiter=rate_limiter,
            timeout=cfg.get('API_TIMEOUT', 15)
        )
        app.logger.info("NYT API 客户端初始化成功")
        return client
    except Exception as e:
        app.logger.warning(f"NYT API 客户端初始化失败: {e}")
        return None


def _init_google_client(cfg, app):
    """初始化 Google Books API 客户端"""
    try:
        client = GoogleBooksClient(
            api_key=cfg.get('GOOGLE_API_KEY'),
            base_url=cfg['GOOGLE_BOOKS_API_URL'],
            timeout=cfg.get('API_TIMEOUT', 8)
        )
        app.logger.info("Google Books 客户端初始化成功")
        return client
    except Exception as e:
        app.logger.warning(f"Google Books 客户端初始化失败: {e}")
        return None


def _init_image_cache(cfg, app):
    """初始化图片缓存服务"""
    try:
        return ImageCacheService(
            cache_dir=cfg['IMAGE_CACHE_DIR'],
            default_cover='/static/default-cover.png'
        )
    except Exception as e:
        app.logger.warning(f"图片缓存服务初始化失败: {e}")
        return None


def _init_translation_service(app):
    """初始化翻译服务"""
    try:
        from .services.zhipu_translation_service import get_translation_service
        service = get_translation_service(app=app)
        app.extensions['translation_service'] = service
        return service
    except Exception as e:
        app.logger.warning(f"翻译服务初始化失败: {e}")
        return None


def _init_book_service(nyt_client, google_client, cache_service, image_cache, app, cfg):
    """初始化图书服务"""
    from .routes import api_bp, public_api_bp

    if not nyt_client or not cache_service:
        app.logger.warning("缺少 NYT 客户端或缓存服务，图书服务未初始化")
        return None

    try:
        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            app=app,
            max_workers=cfg['MAX_WORKERS'],
            categories=cfg['CATEGORIES']
        )
        app.extensions['book_service'] = book_service
        api_bp.book_service = book_service
        public_api_bp.book_service = book_service

        # 注册数据刷新后的周报生成回调
        def _trigger_weekly_report():
            with app.app_context():
                try:
                    from .tasks.weekly_report_task import generate_weekly_report
                    app.logger.info('排行榜数据刷新，检查是否需要生成周报...')
                    generate_weekly_report()
                except Exception as e:
                    app.logger.error(f'数据刷新触发周报生成失败: {e}')

        book_service.on_data_refreshed(_trigger_weekly_report)

        app.logger.info("图书服务初始化成功")
        return book_service
    except Exception as e:
        app.logger.error(f"图书服务初始化失败: {e}")
        return None


def _start_background_threads(app, book_service, translation_service, google_client):
    """启动后台守护线程（Render 免费版优化：增加延迟、减少频率）"""
    # 通过环境变量控制是否启动后台线程（免费版 Render 建议关闭）
    if os.environ.get('DISABLE_BACKGROUND_THREADS', '').lower() == 'true':
        app.logger.info("⏸️ 后台线程已禁用（DISABLE_BACKGROUND_THREADS=true）")
        return

    # Render 免费版：大幅增加初始延迟，减少启动时资源占用
    is_render_free = os.environ.get('RENDER', '').lower() == 'true'
    initial_delay = 1800 if is_render_free else 300  # 30 分钟 / 5 分钟

    if book_service:
        _start_background_thread(app, '周报启动检查', _weekly_report_task, initial_delay, 0)
    if translation_service:
        _start_background_thread(app, '新书速递自动同步', _auto_sync_task, initial_delay * 2, 1209600)
    if google_client:
        _start_background_thread(app, '获奖书籍封面同步', _cover_sync_task, initial_delay, 0)


def _start_background_thread(app, name: str, task, initial_delay: int, interval: int):
    """启动后台守护线程的通用方法"""
    def worker():
        time.sleep(initial_delay)
        while True:
            try:
                task(app)
            except Exception as e:
                app.logger.error(f'{name}线程异常: {e}', exc_info=True)
                time.sleep(3600)
            if interval <= 0:
                break
            time.sleep(interval)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    period_desc = f'{interval // 86400}天周期' if interval > 0 else '仅执行一次'
    app.logger.info(f'{name}线程已启动（{period_desc}）')


def _weekly_report_task(app):
    """周报自动生成任务"""
    with app.app_context():
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
    with app.app_context():
        try:
            from .services.new_book_service import NewBookService
            service = NewBookService(translation_service=app.extensions.get('translation_service'))

            last_sync = SystemConfig.get_value('last_auto_sync_time')
            if last_sync:
                last_sync_time = datetime.fromisoformat(last_sync)
                if last_sync_time.tzinfo is None:
                    last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - last_sync_time).days
                if days_since < 14:
                    app.logger.info(f'距离上次同步仅 {days_since} 天，跳过')
                    return

            app.logger.info('开始自动同步新书数据...')
            service.init_publishers()
            results = service.sync_all_publishers(max_books_per_publisher=15, batch_size=1)
            SystemConfig.set_value('last_auto_sync_time', datetime.now(timezone.utc).isoformat())

            total_added = sum(r.get('added', 0) for r in results)
            total_updated = sum(r.get('updated', 0) for r in results)
            app.logger.info(f'自动同步完成：新增 {total_added} 本，更新 {total_updated} 本')

        except Exception as e:
            app.logger.error(f'自动同步失败: {e}', exc_info=True)
            _log_failure(app, 'last_sync_failure')


def _cover_sync_task(app):
    """获奖书籍封面自动同步任务"""
    with app.app_context():
        try:
            from .services.api_client import GoogleBooksClient
            from .services.award_cover_sync_service import AwardCoverSyncService
            from .config import Config

            app.logger.info('开始检查获奖书籍封面...')

            google_client = GoogleBooksClient(
                api_key=Config.GOOGLE_API_KEY,
                base_url='https://www.googleapis.com/books/v1/volumes'
            )
            sync_service = AwardCoverSyncService(google_client)

            result = sync_service.sync_missing_covers(batch_size=30, delay=0.5)

            if result.get('status') == 'success':
                app.logger.info(
                    f"封面同步完成: 更新{result.get('updated', 0)}本, "
                    f"跳过{result.get('skipped', 0)}本"
                )
            elif result.get('status') == 'complete':
                app.logger.info("所有获奖书籍封面已完整")
            else:
                app.logger.warning(f"封面同步状态: {result.get('status')}")

        except Exception as e:
            app.logger.error(f'封面同步失败: {e}', exc_info=True)


def _log_failure(app, key: str):
    """记录失败时间到系统配置"""
    try:
        SystemConfig.set_value(key, datetime.now(timezone.utc).isoformat())
    except Exception as log_error:
        app.logger.error(f'记录失败时间失败: {log_error}')
