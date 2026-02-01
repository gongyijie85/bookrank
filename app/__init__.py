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
    
    # 自动初始化奖项数据（如果数据库为空）
    _init_awards_data(app)
    
    # Flask缓存 - 使用简单的字典缓存避免扩展问题
    # 不直接使用 Flask-Caching，而是使用自定义缓存服务


def _init_awards_data(app):
    """自动初始化奖项数据（仅在数据库为空时执行）"""
    try:
        with app.app_context():
            from .models.schemas import Award
            
            # 检查是否已有奖项数据
            award_count = Award.query.count()
            if award_count > 0:
                app.logger.info(f"✅ 奖项数据已存在 ({award_count} 个奖项)，跳过初始化")
                return
            
            app.logger.info("🚀 开始自动初始化奖项数据...")
            
            # 创建奖项数据
            awards_data = [
                {
                    'name': '普利策奖',
                    'name_en': 'Pulitzer Prize',
                    'country': '美国',
                    'description': '美国新闻界和文学界的最高荣誉，分为新闻奖、文学奖和音乐奖。文学奖包括小说、戏剧、历史、传记、诗歌和一般非虚构类作品。',
                    'category_count': 6,
                    'icon_class': 'fa-trophy',
                    'established_year': 1917,
                    'award_month': 5
                },
                {
                    'name': '美国国家图书奖',
                    'name_en': 'National Book Award',
                    'country': '美国',
                    'description': '美国文学界的重要奖项，设立于1950年，分为小说、非虚构、诗歌、青少年文学和翻译文学五个类别。',
                    'category_count': 5,
                    'icon_class': 'fa-book',
                    'established_year': 1950,
                    'award_month': 11
                },
                {
                    'name': '布克奖',
                    'name_en': 'Booker Prize',
                    'country': '英国',
                    'description': '英国最具声望的文学奖项，授予年度最佳英文小说。自1969年设立以来，已成为英语文学界最重要的奖项之一。',
                    'category_count': 1,
                    'icon_class': 'fa-star',
                    'established_year': 1969,
                    'award_month': 11
                },
                {
                    'name': '雨果奖',
                    'name_en': 'Hugo Award',
                    'country': '美国',
                    'description': '科幻文学界最高荣誉，以《惊奇故事》杂志创始人雨果·根斯巴克命名。评选范围包括最佳长篇小说、中篇小说、短篇小说等。',
                    'category_count': 8,
                    'icon_class': 'fa-rocket',
                    'established_year': 1953,
                    'award_month': 8
                },
                {
                    'name': '诺贝尔文学奖',
                    'name_en': 'Nobel Prize in Literature',
                    'country': '瑞典',
                    'description': '根据阿尔弗雷德·诺贝尔的遗嘱设立，授予在文学领域创作出具有理想倾向的最佳作品的人。是文学界最高荣誉之一。',
                    'category_count': 1,
                    'icon_class': 'fa-graduation-cap',
                    'established_year': 1901,
                    'award_month': 10
                }
            ]
            
            for award_data in awards_data:
                award = Award(**award_data)
                db.session.add(award)
            
            db.session.commit()
            app.logger.info(f"✅ 已创建 {len(awards_data)} 个奖项")
            
            # 创建示例图书数据
            _init_sample_books(app)
            
    except Exception as e:
        app.logger.error(f"❌ 初始化奖项数据失败: {e}", exc_info=True)


def _init_sample_books(app):
    """初始化示例图书数据"""
    try:
        from .models.schemas import Award, AwardBook
        
        # 示例图书数据
        sample_books = [
            # 普利策奖 2025
            {'award_name': '普利策奖', 'year': 2025, 'category': '小说', 'rank': 1,
             'title': 'The Maniac', 'author': 'Benjamín Labatut',
             'description': 'A gripping narrative about the life of John von Neumann and the dawn of the digital age.'},
            {'award_name': '普利策奖', 'year': 2025, 'category': '非虚构', 'rank': 1,
             'title': 'The Uninhabitable Earth', 'author': 'David Wallace-Wells',
             'description': 'An exploration of the devastating impacts of climate change on our planet.'},
            {'award_name': '普利策奖', 'year': 2024, 'category': '小说', 'rank': 1,
             'title': 'Trust', 'author': 'Hernan Diaz',
             'description': 'A novel about wealth, family, and the American Dream in the 1920s.'},
            
            # 布克奖
            {'award_name': '布克奖', 'year': 2025, 'category': '小说', 'rank': 1,
             'title': 'Orbital', 'author': 'Samantha Harvey',
             'description': 'A novel set in space, exploring human relationships and our place in the universe.'},
            {'award_name': '布克奖', 'year': 2024, 'category': '小说', 'rank': 1,
             'title': 'Prophet Song', 'author': 'Paul Lynch',
             'description': 'A dystopian novel about a mother searching for her son in a collapsing Ireland.'},
            
            # 诺贝尔文学奖
            {'award_name': '诺贝尔文学奖', 'year': 2025, 'category': '文学', 'rank': 1,
             'title': 'The Years', 'author': 'Annie Ernaux',
             'description': 'A memoir that blends personal and collective history.'},
            {'award_name': '诺贝尔文学奖', 'year': 2024, 'category': '文学', 'rank': 1,
             'title': 'Time Shelter', 'author': 'Georgi Gospodinov',
             'description': 'A novel about memory, nostalgia, and the twentieth century.'},
            
            # 雨果奖
            {'award_name': '雨果奖', 'year': 2025, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'Project Hail Mary', 'author': 'Andy Weir',
             'description': 'An astronaut must save Earth from disaster in this sci-fi adventure.'},
            {'award_name': '雨果奖', 'year': 2024, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'A Desolation Called Peace', 'author': 'Arkady Martine',
             'description': 'Sequel to A Memory Called Empire, continuing the story of an interstellar empire.'},
            
            # 美国国家图书奖
            {'award_name': '美国国家图书奖', 'year': 2025, 'category': '小说', 'rank': 1,
             'title': 'The Rabbit Hutch', 'author': 'Tess Gunty',
             'description': 'A debut novel about loneliness and connection in a small Indiana town.'},
            {'award_name': '美国国家图书奖', 'year': 2024, 'category': '小说', 'rank': 1,
             'title': 'Hell of a Book', 'author': 'Jason Mott',
             'description': 'A novel about a Black author on a book tour while dealing with personal and societal trauma.'},
        ]
        
        created_count = 0
        for book_data in sample_books:
            award = Award.query.filter_by(name=book_data['award_name']).first()
            if award:
                book = AwardBook(
                    award_id=award.id,
                    year=book_data['year'],
                    category=book_data['category'],
                    rank=book_data['rank'],
                    title=book_data['title'],
                    author=book_data['author'],
                    description=book_data['description']
                )
                db.session.add(book)
                created_count += 1
        
        db.session.commit()
        app.logger.info(f"✅ 已创建 {created_count} 本示例图书")
        
    except Exception as e:
        app.logger.error(f"❌ 初始化示例图书失败: {e}", exc_info=True)
        db.session.rollback()


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
