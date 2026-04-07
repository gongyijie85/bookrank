import logging
import os
import secrets
import threading
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask, session
from flask_cors import CORS
from flask_talisman import Talisman

from .config import config
from .models import db, init_db
from .models.schemas import UserPreference, SearchHistory, BookMetadata, Award, AwardBook, TranslationCache, APICache, SystemConfig
from .models.new_book import Publisher, NewBook
from .routes import api_bp, main_bp, public_api_bp, new_books_bp, health_bp
from .services import (
    CacheService, MemoryCache, FileCache,
    NYTApiClient, GoogleBooksClient, ImageCacheService,
    BookService
)
from .utils import RateLimiter
from .initialization import init_awards_data, init_sample_books
from .utils.security import add_security_headers

PROJECT_ROOT = Path(__file__).parent.parent


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

    # 生产环境应用安全头
    if config_name == 'production':
        _apply_security_headers(app)

    return app


def _init_extensions(app, config_name: str):
    """初始化Flask扩展"""
    # CORS 配置 - 根据环境调整
    if config_name == 'production':
        cors_origins = app.config.get('CORS_ORIGINS', [])
        cors_methods = ['GET', 'POST', 'OPTIONS']
    else:
        cors_origins = '*'
        cors_methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": cors_origins,
                "methods": cors_methods,
                "allow_headers": ["Content-Type", "Authorization"],
                "max_age": 3600,
            }
        },
        supports_credentials=True
    )

    init_db(app)

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

    # 内存缓存配置（Render 免费版优化：增大缓存容量）
    memory_cache = MemoryCache(default_ttl=cfg['MEMORY_CACHE_TTL'], max_size=2000)

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
    from .services.translation_service import TranslationService
    translation_service = TranslationService()

    # 图书服务配置
    book_service = BookService(
        nyt_client=nyt_client,
        google_client=google_client,
        cache_service=cache_service,
        image_cache=image_cache,
        max_workers=cfg['MAX_WORKERS'],
        categories=cfg['CATEGORIES']
    )

    # 注册到应用扩展
    app.extensions['book_service'] = book_service
    app.extensions['translation_service'] = translation_service

    # 绑定到蓝图
    api_bp.book_service = book_service
    public_api_bp.book_service = book_service

    # 启动新书速递自动同步线程（7天一次）
    _start_auto_sync_thread(app)


def _register_blueprints(app):
    """注册蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(public_api_bp)
    app.register_blueprint(new_books_bp)
    app.register_blueprint(health_bp)


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
    import time as _time

    @event.listens_for(Pool, "checkout")
    def handle_checkout(dbapi_connection, connection_record, connection_proxy):
        """连接检出时检查"""
        pass

    @event.listens_for(Pool, "checkin")
    def handle_checkin(dbapi_connection, connection_record):
        """连接归还时记录"""
        pass

    @event.listens_for(Pool, "connect")
    def on_connect(dbapi_connection, connection_record):
        """新连接建立时"""
        app.logger.debug("数据库新连接已建立")

    @event.listens_for(Pool, "reset")
    def on_reset(dbapi_connection, connection_record):
        """连接重置时"""
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception:
            pass


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
        # 防止点击劫持
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # XSS 防护
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # 内容类型 sniffing 防护
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # 引用来源策略
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # 移除服务器版本信息
        response.headers['Server'] = 'BookRank'
        return response


def _start_auto_sync_thread(app):
    """启动新书速递自动同步线程（7天一次）"""
    def auto_sync_task():
        """自动同步任务"""
        with app.app_context():
            try:
                from .services.new_book_service import NewBookService
                service = NewBookService(translation_service=app.extensions.get('translation_service'))
                
                # 检查是否需要同步（每7天一次）
                last_sync_key = 'last_auto_sync_time'
                last_sync = SystemConfig.get_value(last_sync_key)
                
                if last_sync:
                    last_sync_time = datetime.fromisoformat(last_sync)
                    days_since_last_sync = (datetime.now() - last_sync_time).days
                    if days_since_last_sync < 7:
                        app.logger.info(f'距离上次同步仅 {days_since_last_sync} 天，跳过自动同步')
                        return
                
                app.logger.info('开始自动同步新书数据...')
                
                # 静默同步，不显示提示
                service.init_publishers()
                results = service.sync_all_publishers(max_books_per_publisher=20)
                
                # 更新最后同步时间
                SystemConfig.set_value(last_sync_key, datetime.now().isoformat())
                
                total_added = sum(r.get('added', 0) for r in results)
                total_updated = sum(r.get('updated', 0) for r in results)
                
                app.logger.info(f'自动同步完成：新增 {total_added} 本，更新 {total_updated} 本')
                
            except Exception as e:
                app.logger.error(f'自动同步失败: {e}', exc_info=True)
    
    def sync_worker():
        """同步工作线程"""
        # 首次启动时等待5分钟，避免影响应用启动
        time.sleep(300)
        
        while True:
            try:
                auto_sync_task()
            except Exception as e:
                app.logger.error(f'自动同步线程异常: {e}')
            
            # 每7天执行一次（7 * 24 * 60 * 60 = 604800秒）
            time.sleep(604800)
    
    # 启动后台线程
    sync_thread = threading.Thread(target=sync_worker, daemon=True)
    sync_thread.start()
    app.logger.info('新书速递自动同步线程已启动（7天周期）')


app = create_app(os.environ.get('FLASK_ENV', 'development'))
