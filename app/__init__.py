import logging
from pathlib import Path
from flask import Flask
from flask_cors import CORS

from .config import config
from .models import db, init_db
from .routes import api_bp, main_bp
from .services import (
    CacheService, MemoryCache, FileCache,
    NYTApiClient, GoogleBooksClient, ImageCacheService,
    BookService
)
from .utils import RateLimiter

# 获取项目根目录
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
    
    # 加载配置
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # 初始化扩展
    _init_extensions(app)
    
    # 初始化服务
    _init_services(app)
    
    # 注册蓝图
    _register_blueprints(app)
    
    # 注册错误处理器
    _register_error_handlers(app)
    
    # 配置日志
    _configure_logging(app)
    
    return app


def _init_extensions(app):
    """初始化Flask扩展"""
    # CORS
    CORS(app)
    
    # 数据库
    init_db(app)
    
    # Flask缓存 - 使用简单的字典缓存避免扩展问题
    # 不直接使用 Flask-Caching，而是使用自定义缓存服务


def _init_services(app):
    """初始化业务服务"""
    config = app.config
    
    # 创建缓存服务（不使用Flask-Caching，只使用内存和文件缓存）
    memory_cache = MemoryCache(default_ttl=config['MEMORY_CACHE_TTL'])
    file_cache = FileCache(
        cache_dir=config['CACHE_DIR'],
        default_ttl=config['CACHE_DEFAULT_TIMEOUT']
    )
    
    cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
    
    # 创建限流器
    rate_limiter = RateLimiter(
        max_calls=config['API_RATE_LIMIT'],
        window_seconds=config['API_RATE_LIMIT_WINDOW']
    )
    
    # 创建API客户端
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
    
    # 创建图片缓存服务
    image_cache = ImageCacheService(
        cache_dir=config['IMAGE_CACHE_DIR'],
        default_cover='/static/default-cover.png'
    )
    
    # 创建图书服务
    book_service = BookService(
        nyt_client=nyt_client,
        google_client=google_client,
        cache_service=cache_service,
        image_cache=image_cache,
        max_workers=config['MAX_WORKERS'],
        categories=config['CATEGORIES']
    )
    
    # 将服务存储在应用上下文中
    app.extensions['book_service'] = book_service
    
    # 将book_service注入到api_bp中
    api_bp.book_service = book_service


def _register_blueprints(app):
    """注册蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)


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
        # 生产环境日志配置
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        
        # 配置第三方库日志级别
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy').setLevel(logging.WARNING)


# 为 Gunicorn 直接暴露 app 实例
# 使用环境变量 FLASK_ENV 或默认为 production
import os
app = create_app(os.environ.get('FLASK_ENV', 'production'))
