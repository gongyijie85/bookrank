import logging
import os
import secrets
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, session
from flask_cors import CORS
from flask_talisman import Talisman

from .config import config
from .models import db, init_db
from .routes import api_bp, main_bp, public_api_bp
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
    # CORS 配置优化
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
                "max_age": 3600,
            }
        },
        supports_credentials=True
    )

    init_db(app)

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

    # 内存缓存配置（增大缓存容量）
    memory_cache = MemoryCache(default_ttl=cfg['MEMORY_CACHE_TTL'])

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

    # 绑定到蓝图
    api_bp.book_service = book_service
    public_api_bp.book_service = book_service


def _register_blueprints(app):
    """注册蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(public_api_bp)


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


def _configure_logging(app):
    """配置日志"""
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)

        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)

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


app = create_app(os.environ.get('FLASK_ENV', 'production'))
