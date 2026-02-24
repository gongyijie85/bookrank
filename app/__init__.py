import logging
import os
from pathlib import Path
from flask import Flask
from flask_cors import CORS

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
    
    _init_extensions(app)
    _init_services(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _configure_logging(app)
    
    return app


def _init_extensions(app):
    """初始化Flask扩展"""
    CORS(app)
    init_db(app)
    _init_awards_data(app)


def _init_awards_data(app):
    """自动初始化奖项数据"""
    with app.app_context():
        init_awards_data(app)
        init_sample_books(app)


def _init_services(app):
    """初始化业务服务"""
    config = app.config
    
    memory_cache = MemoryCache(default_ttl=config['MEMORY_CACHE_TTL'])
    file_cache = FileCache(
        cache_dir=config['CACHE_DIR'],
        default_ttl=config['CACHE_DEFAULT_TIMEOUT']
    )
    
    cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
    
    rate_limiter = RateLimiter(
        max_calls=config['API_RATE_LIMIT'],
        window_seconds=config['API_RATE_LIMIT_WINDOW']
    )
    
    nyt_client = NYTApiClient(
        api_key=config.get('NYT_API_KEY', ''),
        base_url=config['NYT_API_BASE_URL'],
        rate_limiter=rate_limiter,
        timeout=config.get('API_TIMEOUT', 15)
    )
    
    google_client = GoogleBooksClient(
        api_key=config.get('GOOGLE_API_KEY'),
        base_url=config['GOOGLE_BOOKS_API_URL'],
        timeout=config.get('API_TIMEOUT', 8)
    )
    
    image_cache = ImageCacheService(
        cache_dir=config['IMAGE_CACHE_DIR'],
        default_cover='/static/default-cover.png'
    )
    
    book_service = BookService(
        nyt_client=nyt_client,
        google_client=google_client,
        cache_service=cache_service,
        image_cache=image_cache,
        max_workers=config['MAX_WORKERS'],
        categories=config['CATEGORIES']
    )
    
    app.extensions['book_service'] = book_service
    
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
        
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy').setLevel(logging.WARNING)


app = create_app(os.environ.get('FLASK_ENV', 'production'))
