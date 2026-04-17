import logging
import os
import threading
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask, session
from flask_cors import CORS

from .config import config
from .models import db, init_db
from .models.schemas import UserPreference, SearchHistory, BookMetadata, Award, AwardBook, TranslationCache, APICache, SystemConfig, WeeklyReport, ReportView, UserBehavior
from .models.new_book import Publisher, NewBook

PROJECT_ROOT = Path(__file__).parent.parent

from .routes import api_bp, main_bp, public_api_bp, new_books_bp, health_bp, analytics_bp
from .services import (
    CacheService, MemoryCache, FileCache,
    NYTApiClient, GoogleBooksClient, ImageCacheService,
    BookService
)
from .utils import RateLimiter
from .initialization import init_awards_data, init_sample_books


def create_app(config_name='default'):
    """
    应用工厂函数

    Args:
        config_name: 配置名称 ('development', 'production', 'testing')

    Returns:
        Flask应用实例
    """
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / 'templates'),
        static_folder=str(PROJECT_ROOT / 'static')
    )

    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    _init_extensions(app, config_name)
    _init_services(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _configure_logging(app)

    # 应用安全头（所有环境）
    _apply_security_headers(app)
    
    # 启用API速率限制（生产环境）
    if config_name == 'production':
        _enable_rate_limiting(app)

    return app


def _init_extensions(app, config_name: str):
    """初始化Flask扩展"""
    # CORS 配置 - 根据环境调整
    if config_name == 'production':
        # 生产环境使用具体的域名列表
        cors_origins = app.config.get('CORS_ORIGINS', [])
        if not cors_origins:
            cors_origins = []
        cors_methods = ['GET', 'POST', 'OPTIONS']
    else:
        # 开发环境允许所有来源
        cors_origins = '*'
        cors_methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": cors_origins,
                "methods": cors_methods,
                "allow_headers": ["Content-Type", "Authorization"],
                "expose_headers": ["Content-Length", "Content-Disposition"],
                "max_age": 3600,
                "supports_credentials": True
            }
        },
        supports_credentials=True
    )

    init_db(app)

    # 初始化邮件服务
    from flask_mail import Mail
    app.extensions['mail'] = Mail(app)

    # 初始化数据库迁移
    from flask_migrate import Migrate
    global migrate
    migrate = Migrate(app, db)

    # 设置数据库事件监听器（处理 Render PostgreSQL 休眠恢复）
    _setup_db_event_listeners(app)

    # 只在首次启动时初始化数据
    if config_name != 'testing':
        _init_awards_data(app)


def _init_awards_data(app):
    """自动初始化奖项数据"""
    with app.app_context():
        init_awards_data(app)
        init_sample_books(app)


def _init_services(app):
    """初始化业务服务"""
    cfg = app.config

    # 内存缓存配置（Render 免费版优化：减少缓存容量以降低内存使用）
    memory_cache = MemoryCache(default_ttl=cfg['MEMORY_CACHE_TTL'], max_size=1000)

    # 文件缓存配置
    file_cache = FileCache(
        cache_dir=cfg['CACHE_DIR'],
        default_ttl=cfg['CACHE_DEFAULT_TIMEOUT']
    )

    cache_service = CacheService(memory_cache, file_cache, flask_cache=None)

    # 限流器配置
    rate_limiter = RateLimiter(
        max_calls=cfg['API_RATE_LIMIT'],
        window_seconds=cfg['API_RATE_LIMIT_WINDOW']
    )

    # NYT API 客户端配置
    nyt_client = NYTApiClient(
        api_key=cfg.get('NYT_API_KEY', ''),
        base_url=cfg['NYT_API_BASE_URL'],
        rate_limiter=rate_limiter,
        timeout=cfg.get('API_TIMEOUT', 15)
    )

    # Google Books API 客户端配置（连接池优化）
    google_client = GoogleBooksClient(
        api_key=cfg.get('GOOGLE_API_KEY'),
        base_url=cfg['GOOGLE_BOOKS_API_URL'],
        timeout=cfg.get('API_TIMEOUT', 8)
    )

    # 图片缓存服务配置
    image_cache = ImageCacheService(
        cache_dir=cfg['IMAGE_CACHE_DIR'],
        default_cover='/static/default-cover.png'
    )

    # 翻译服务配置
    from .services.zhipu_translation_service import get_translation_service
    translation_service = get_translation_service(app=app)

    # 图书服务配置
    book_service = BookService(
        nyt_client=nyt_client,
        google_client=google_client,
        cache_service=cache_service,
        image_cache=image_cache,
        app=app,
        max_workers=cfg['MAX_WORKERS'],
        categories=cfg['CATEGORIES']
    )

    # 注册到应用扩展
    app.extensions['book_service'] = book_service
    app.extensions['translation_service'] = translation_service

    # 绑定到蓝图
    api_bp.book_service = book_service
    public_api_bp.book_service = book_service

    # 启动新书速递自动同步线程（14天一次）
    _start_auto_sync_thread(app)

    # 启动周报自动生成线程（每周一次）
    _start_weekly_report_thread(app)

    # 启动获奖书籍封面同步（启动后5分钟执行一次）
    _start_award_cover_sync_thread(app)


def _register_blueprints(app):
    """注册蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(public_api_bp)
    app.register_blueprint(new_books_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(analytics_bp)


def _register_error_handlers(app):
    """注册全局错误处理器"""

    @app.errorhandler(400)
    def bad_request(error):
        return {'success': False, 'message': 'Bad request'}, 400

    @app.errorhandler(404)
    def not_found(error):
        return {'success': False, 'message': 'Resource not found'}, 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return {'success': False, 'message': 'Method not allowed'}, 405

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return {'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logging.error(f"Internal error: {error}", exc_info=True)
        return {'success': False, 'message': 'Internal server error'}, 500


def _setup_db_event_listeners(app):
    """设置数据库事件监听器，处理 Render PostgreSQL 休眠恢复"""
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError, DisconnectionError
    from sqlalchemy.pool import Pool

    @event.listens_for(Pool, "checkout")
    def handle_checkout(dbapi_connection, connection_record, connection_proxy):
        """连接检出时检查"""
        try:
            # 测试连接是否有效
            cursor = dbapi_connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
        except Exception as e:
            app.logger.warning(f"数据库连接检查失败: {e}")
            # 抛出异常，让连接池重新创建连接
            raise DisconnectionError("Connection check failed")

    @event.listens_for(Pool, "checkin")
    def handle_checkin(dbapi_connection, connection_record):
        """连接归还时记录"""
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception as e:
            app.logger.warning(f"连接归还时回滚失败: {e}")

    @event.listens_for(Pool, "connect")
    def on_connect(dbapi_connection, connection_record):
        """新连接建立时"""
        app.logger.debug("数据库新连接已建立")
        # 设置连接参数
        if hasattr(dbapi_connection, 'set_session'):
            try:
                dbapi_connection.set_session(autocommit=False, timezone='UTC')
            except Exception as e:
                app.logger.warning(f"设置连接参数失败: {e}")

    @event.listens_for(Pool, "reset")
    def on_reset(dbapi_connection, connection_record):
        """连接重置时"""
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception as e:
            app.logger.warning(f"连接重置时回滚失败: {e}")


def _configure_logging(app):
    """配置日志"""
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)

        app.logger.handlers.clear()
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.propagate = False

        # 降低第三方库的日志级别
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)


def _apply_security_headers(app):
    """应用安全响应头"""
    @app.after_request
    def add_security_headers(response):
        # 安全响应头配置
        security_headers = {
            'X-Frame-Options': 'SAMEORIGIN',
            'X-XSS-Protection': '1; mode=block',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Server': 'BookRank',
            'Content-Security-Policy': (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com 'unsafe-inline'; "
                "img-src 'self' data: https://*.nytimes.com https://*.amazon.com https://*.amazonaws.com https://books.google.com https://covers.openlibrary.org https://openlibrary.org https://*.penguinrandomhouse.com https://*.harpercollins.com https://*.macmillan.com https://*.simonandschuster.com https://*.hachettebookgroup.com; "
                "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://fonts.gstatic.com; "
                "connect-src 'self'; "
                "frame-src 'none'; "
                "object-src 'none';"
            ),
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()'
        }
        
        # 应用安全响应头
        for header, value in security_headers.items():
            response.headers[header] = value
        
        # 严格传输安全（仅在生产环境）
        if app.config.get('ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        return response


def _enable_rate_limiting(app):
    """启用API速率限制"""
    from flask import request, make_response
    from .utils.rate_limiter import get_rate_limiter
    
    rate_limiter = get_rate_limiter(
        max_requests=app.config.get('API_RATE_LIMIT', 60),
        window_seconds=app.config.get('API_RATE_LIMIT_WINDOW', 60)
    )
    
    @app.before_request
    def rate_limit_requests():
        """速率限制中间件"""
        # 排除静态文件、健康检查和前端页面请求
        if (request.path.startswith('/static/') or 
            request.path.startswith('/health/') or
            not request.path.startswith('/api/')):
            return None
        
        # 获取客户端IP
        client_ip = request.remote_addr or 'unknown'
        
        # 检查速率限制
        if not rate_limiter.is_allowed(client_ip):
            retry_after = rate_limiter.get_retry_after(client_ip)
            response = make_response({'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429)
            response.headers['Retry-After'] = str(retry_after)
            return response
        
        return None


def _start_background_thread(app, name: str, task, initial_delay: int, interval: int):
    """启动后台守护线程的通用方法"""
    def worker():
        time.sleep(initial_delay)
        while True:
            try:
                task()
            except Exception as e:
                app.logger.error(f'{name}线程异常: {e}', exc_info=True)
                time.sleep(3600)
            time.sleep(interval)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    app.logger.info(f'{name}线程已启动（{interval // 86400}天周期）')


def _start_auto_sync_thread(app):
    """启动新书速递自动同步线程（14天一次）"""
    def auto_sync_task():
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
                try:
                    SystemConfig.set_value('last_sync_failure', datetime.now(timezone.utc).isoformat())
                except Exception as log_error:
                    app.logger.error(f'记录同步失败时间失败: {log_error}')

    _start_background_thread(app, '新书速递自动同步', auto_sync_task, initial_delay=600, interval=1209600)


def _start_weekly_report_thread(app):
    """启动周报自动生成线程（每周一次）"""
    def weekly_report_task():
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
                try:
                    SystemConfig.set_value('last_report_failure', datetime.now(timezone.utc).isoformat())
                except Exception as log_error:
                    app.logger.error(f'记录周报生成失败时间失败: {log_error}')

    _start_background_thread(app, '周报自动生成', weekly_report_task, initial_delay=300, interval=604800)


def _start_award_cover_sync_thread(app):
    """启动获奖书籍封面自动同步线程（启动后执行一次）"""
    def cover_sync_task():
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

                # 执行同步（最多处理30本书）
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

    # 启动后5分钟执行一次（不重复，仅在需要时手动触发）
    _start_background_thread(app, '获奖书籍封面同步', cover_sync_task, initial_delay=300, interval=0)


app = create_app(os.environ.get('FLASK_ENV', 'development'))

# 导出迁移对象
migrate
