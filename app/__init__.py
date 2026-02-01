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
    """自动初始化奖项数据（Render免费版优化：智能更新）"""
    try:
        with app.app_context():
            from .models.schemas import Award, AwardBook
            
            app.logger.info("🚀 开始检查奖项数据...")
            
            # 检查是否已有奖项数据
            award_count = Award.query.count()
            book_count = AwardBook.query.count()
            
            # 如果数据已存在且完整，跳过初始化
            if award_count >= 5 and book_count >= 12:
                app.logger.info(f"✅ 数据已完整 ({award_count} 个奖项, {book_count} 本图书)")
                return
            
            app.logger.info(f"📊 当前数据: {award_count} 个奖项, {book_count} 本图书")
            
            # 定义奖项数据
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
            
            # 智能创建：只创建不存在的奖项
            created_awards = 0
            for award_data in awards_data:
                existing = Award.query.filter_by(name=award_data['name']).first()
                if not existing:
                    award = Award(**award_data)
                    db.session.add(award)
                    created_awards += 1
            
            if created_awards > 0:
                db.session.commit()
                app.logger.info(f"✅ 已创建 {created_awards} 个新奖项")
            else:
                app.logger.info("✅ 所有奖项已存在")
            
            # 创建示例图书数据
            _init_sample_books(app)
            
    except Exception as e:
        app.logger.error(f"❌ 初始化奖项数据失败: {e}", exc_info=True)


def _init_sample_books(app):
    """初始化示例图书数据"""
    try:
        from .models.schemas import Award, AwardBook
        
        # 示例图书数据（包含真实ISBN和封面图片）
        sample_books = [
            # 普利策奖
            {'award_name': '普利策奖', 'year': 2023, 'category': '小说', 'rank': 1,
             'title': 'Demon Copperhead', 'author': 'Barbara Kingsolver',
             'description': 'A modern retelling of David Copperfield set in Appalachia, following a boy born to a teenage single mother.',
             'isbn13': '9780063251922',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1667400945i/60561215.jpg'},
            {'award_name': '普利策奖', 'year': 2023, 'category': '非虚构', 'rank': 1,
             'title': 'His Name Is George Floyd', 'author': 'Robert Samuels, Toluse Olorunnipa',
             'description': 'A biography of George Floyd that explores the racial justice movement and systemic inequality in America.',
             'isbn13': '9780593491930',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1666951046i/61295405.jpg'},
            {'award_name': '普利策奖', 'year': 2022, 'category': '小说', 'rank': 1,
             'title': 'The Netanyahus', 'author': 'Joshua Cohen',
             'description': 'A comic novel about a Jewish historian who meets the Netanyahu family in 1959.',
             'isbn13': '9781681376070',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1632764182i/58340706.jpg'},
            
            # 布克奖
            {'award_name': '布克奖', 'year': 2023, 'category': '小说', 'rank': 1,
             'title': 'Prophet Song', 'author': 'Paul Lynch',
             'description': 'A dystopian novel about a mother searching for her son in a collapsing Ireland.',
             'isbn13': '9781954118259',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1674220043i/75246613.jpg'},
            {'award_name': '布克奖', 'year': 2022, 'category': '小说', 'rank': 1,
             'title': 'The Seven Moons of Maali Almeida', 'author': 'Shehan Karunatilaka',
             'description': 'A satirical novel about a war photographer who wakes up dead in a celestial visa office.',
             'isbn13': '9789357022876',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1644144088i/60190659.jpg'},
            {'award_name': '布克奖', 'year': 2021, 'category': '小说', 'rank': 1,
             'title': 'The Promise', 'author': 'Damon Galgut',
             'description': 'A story about a white South African family and a promise made to their Black servant.',
             'isbn13': '9781609456517',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1619021347i/56781769.jpg'},
            
            # 诺贝尔文学奖
            {'award_name': '诺贝尔文学奖', 'year': 2022, 'category': '文学', 'rank': 1,
             'title': 'The Years', 'author': 'Annie Ernaux',
             'description': 'A memoir that blends personal and collective history from 1941 to 2006.',
             'isbn13': '9781609808927',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1534801779i/40977547.jpg'},
            {'award_name': '诺贝尔文学奖', 'year': 2023, 'category': '文学', 'rank': 1,
             'title': 'Time Shelter', 'author': 'Georgi Gospodinov',
             'description': 'A novel about memory, nostalgia, and the twentieth century.',
             'isbn13': '9781324008372',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1658767717i/61718037.jpg'},
            
            # 雨果奖
            {'award_name': '雨果奖', 'year': 2023, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'Nettle & Bone', 'author': 'T. Kingfisher',
             'description': 'A fantasy novel about a princess who must save her sister from an abusive husband.',
             'isbn13': '9781250244048',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1651605882i/57693192.jpg'},
            {'award_name': '雨果奖', 'year': 2022, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'A Desolation Called Peace', 'author': 'Arkady Martine',
             'description': 'Sequel to A Memory Called Empire, continuing the story of an interstellar empire.',
             'isbn13': '9781250186461',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1607446898i/45154552.jpg'},
            {'award_name': '雨果奖', 'year': 2021, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'Network Effect', 'author': 'Martha Wells',
             'description': 'The first full-length novel in the Murderbot Diaries series.',
             'isbn13': '9781250229861',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1569960398i/52381746.jpg'},
            
            # 美国国家图书奖
            {'award_name': '美国国家图书奖', 'year': 2023, 'category': '小说', 'rank': 1,
             'title': 'The Rabbit Hutch', 'author': 'Tess Gunty',
             'description': 'A debut novel about loneliness and connection in a small Indiana town.',
             'isbn13': '9780593534668',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1646095937i/60317273.jpg'},
            {'award_name': '美国国家图书奖', 'year': 2022, 'category': '小说', 'rank': 1,
             'title': 'The Rabbit Hutch', 'author': 'Tess Gunty',
             'description': 'A debut novel about loneliness and connection in a small Indiana town.',
             'isbn13': '9780593534668',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1646095937i/60317273.jpg'},
            {'award_name': '美国国家图书奖', 'year': 2021, 'category': '小说', 'rank': 1,
             'title': 'Hell of a Book', 'author': 'Jason Mott',
             'description': 'A novel about a Black author on a book tour while dealing with personal and societal trauma.',
             'isbn13': '9780593237941',
             'cover_url': 'https://images-na.ssl-images-amazon.com/images/S/compressed.photo.goodreads.com/books/1611954638i/55835474.jpg'},
        ]
        
        # 智能创建：只创建不存在的图书（根据ISBN判断）
        created_count = 0
        updated_count = 0
        
        for book_data in sample_books:
            award = Award.query.filter_by(name=book_data['award_name']).first()
            if not award:
                continue
            
            isbn = book_data.get('isbn13')
            
            # 检查是否已存在（根据ISBN或标题+作者）
            if isbn:
                existing = AwardBook.query.filter_by(isbn13=isbn).first()
            else:
                existing = AwardBook.query.filter_by(
                    title=book_data['title'],
                    author=book_data['author']
                ).first()
            
            if existing:
                # 更新现有记录（补充ISBN和封面）
                if isbn and not existing.isbn13:
                    existing.isbn13 = isbn
                    updated_count += 1
                if book_data.get('cover_url') and not existing.cover_original_url:
                    existing.cover_original_url = book_data['cover_url']
                    updated_count += 1
            else:
                # 创建新记录
                book = AwardBook(
                    award_id=award.id,
                    year=book_data['year'],
                    category=book_data['category'],
                    rank=book_data['rank'],
                    title=book_data['title'],
                    author=book_data['author'],
                    description=book_data['description'],
                    isbn13=isbn,
                    cover_original_url=book_data.get('cover_url')
                )
                db.session.add(book)
                created_count += 1
        
        if created_count > 0 or updated_count > 0:
            db.session.commit()
            app.logger.info(f"✅ 图书: 新建 {created_count} 本, 更新 {updated_count} 本")
        else:
            app.logger.info("✅ 所有图书已是最新")
        
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
