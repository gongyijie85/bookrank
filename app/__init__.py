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
                },
                {
                    'name': '星云奖',
                    'name_en': 'Nebula Award',
                    'country': '美国',
                    'description': '美国科幻和奇幻作家协会颁发的年度大奖，与雨果奖并称为科幻界双璧。评选范围包括最佳长篇小说、中篇小说、短篇小说等。',
                    'category_count': 6,
                    'icon_class': 'fa-star',
                    'established_year': 1965,
                    'award_month': 5
                },
                {
                    'name': '国际布克奖',
                    'name_en': 'International Booker Prize',
                    'country': '英国',
                    'description': '布克奖的姊妹奖项，专门颁发给翻译成英语并在英国出版的外国小说。作者和译者平分奖金，是挖掘非英语佳作的重要风向标。',
                    'category_count': 1,
                    'icon_class': 'fa-globe',
                    'established_year': 2005,
                    'award_month': 5
                },
                {
                    'name': '爱伦·坡奖',
                    'name_en': 'Edgar Award',
                    'country': '美国',
                    'description': '美国推理作家协会颁发的年度大奖，以推理小说之父爱伦·坡命名。是推理小说界的最高荣誉，涵盖小说、电视、电影等多个领域。',
                    'category_count': 12,
                    'icon_class': 'fa-user-secret',
                    'established_year': 1946,
                    'award_month': 4
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
        # ISBN已通过Google Books API和Amazon验证
        sample_books = [
            # ========================================
            # 普利策奖 (Pulitzer Prize)
            # ========================================
            # 2025年普利策小说奖
            {'award_name': '普利策奖', 'year': 2025, 'category': '小说', 'rank': 1,
             'title': 'James', 'author': 'Percival Everett',
             'description': 'A brilliant reimagining of Adventures of Huckleberry Finn from the perspective of Jim, the enslaved man.',
             'isbn13': '9780385550369',
             'cover_url': None},  # 将通过Google Books API获取
            
            # 2024年普利策小说奖
            {'award_name': '普利策奖', 'year': 2024, 'category': '小说', 'rank': 1,
             'title': 'The Nickel Boys', 'author': 'Colson Whitehead',
             'description': 'Based on the true story of a reform school in Florida that operated for over a century.',
             'isbn13': '9780385537070',
             'cover_url': None},
            
            # 2023年普利策小说奖
            {'award_name': '普利策奖', 'year': 2023, 'category': '小说', 'rank': 1,
             'title': 'Demon Copperhead', 'author': 'Barbara Kingsolver',
             'description': 'A modern retelling of David Copperfield set in Appalachia, following a boy born to a teenage single mother.',
             'isbn13': '9780063251922',
             'cover_url': None},
            
            # 2023年普利策非虚构奖
            {'award_name': '普利策奖', 'year': 2023, 'category': '非虚构', 'rank': 1,
             'title': 'His Name Is George Floyd', 'author': 'Robert Samuels, Toluse Olorunnipa',
             'description': 'A biography of George Floyd that explores the racial justice movement and systemic inequality in America.',
             'isbn13': '9780593491930',
             'cover_url': None},
            
            # 2022年普利策小说奖
            {'award_name': '普利策奖', 'year': 2022, 'category': '小说', 'rank': 1,
             'title': 'The Netanyahus', 'author': 'Joshua Cohen',
             'description': 'A comic novel about a Jewish historian who meets the Netanyahu family in 1959.',
             'isbn13': '9781681376070',
             'cover_url': None},
            
            # ========================================
            # 布克奖 (Booker Prize)
            # ========================================
            # 2024年布克奖
            {'award_name': '布克奖', 'year': 2024, 'category': '小说', 'rank': 1,
             'title': 'Orbital', 'author': 'Samantha Harvey',
             'description': 'A novel set on the International Space Station, exploring the lives of six astronauts.',
             'isbn13': '9780802163807',
             'cover_url': None},
            
            # 2023年布克奖
            {'award_name': '布克奖', 'year': 2023, 'category': '小说', 'rank': 1,
             'title': 'Prophet Song', 'author': 'Paul Lynch',
             'description': 'A dystopian novel about a mother searching for her son in a collapsing Ireland.',
             'isbn13': '9780802161513',
             'cover_url': None},
            
            # 2022年布克奖
            {'award_name': '布克奖', 'year': 2022, 'category': '小说', 'rank': 1,
             'title': 'The Seven Moons of Maali Almeida', 'author': 'Shehan Karunatilaka',
             'description': 'A satirical novel about a war photographer who wakes up dead in a celestial visa office.',
             'isbn13': '9781324035910',
             'cover_url': None},
            
            # ========================================
            # 诺贝尔文学奖 (Nobel Prize in Literature)
            # ========================================
            # 2024年诺贝尔文学奖得主：韩江
            {'award_name': '诺贝尔文学奖', 'year': 2024, 'category': '文学', 'rank': 1,
             'title': 'The Vegetarian', 'author': 'Han Kang',
             'description': 'A dark and surreal novel about a woman who decides to stop eating meat and the consequences that follow.',
             'isbn13': '9780553448184',
             'cover_url': None},
            
            # 2023年诺贝尔文学奖得主：约恩·福瑟
            {'award_name': '诺贝尔文学奖', 'year': 2023, 'category': '文学', 'rank': 1,
             'title': 'A New Name: Septology VI-VII', 'author': 'Jon Fosse',
             'description': 'The final installment of the Septology series, exploring the life of an aging painter.',
             'isbn13': '9781555978896',
             'cover_url': None},
            
            # 2022年诺贝尔文学奖得主：安妮·埃尔诺
            {'award_name': '诺贝尔文学奖', 'year': 2022, 'category': '文学', 'rank': 1,
             'title': 'The Years', 'author': 'Annie Ernaux',
             'description': 'A memoir that blends personal and collective history from 1941 to 2006.',
             'isbn13': '9781609808927',
             'cover_url': None},
            
            # ========================================
            # 雨果奖 (Hugo Award)
            # ========================================
            # 2025年雨果奖最佳长篇小说
            {'award_name': '雨果奖', 'year': 2025, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'The Tainted Cup', 'author': 'Robert Jackson Bennett',
             'description': 'A mystery fantasy novel featuring a Holmes-like detective in a world where magic is powered by parasitic infection.',
             'isbn13': '9781984820709',
             'cover_url': None},
            
            # 2024年雨果奖最佳长篇小说
            {'award_name': '雨果奖', 'year': 2024, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'Some Desperate Glory', 'author': 'Emily Tesh',
             'description': 'A space opera about a young woman raised on a space station to avenge Earth\'s destruction.',
             'isbn13': '9781250834989',
             'cover_url': None},
            
            # 2023年雨果奖最佳长篇小说
            {'award_name': '雨果奖', 'year': 2023, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'Nettle & Bone', 'author': 'T. Kingfisher',
             'description': 'A fantasy novel about a princess who must save her sister from an abusive husband.',
             'isbn13': '9781250244048',
             'cover_url': None},
            
            # ========================================
            # 美国国家图书奖 (National Book Award)
            # ========================================
            # 2024年美国国家图书奖小说奖
            {'award_name': '美国国家图书奖', 'year': 2024, 'category': '小说', 'rank': 1,
             'title': 'James', 'author': 'Percival Everett',
             'description': 'A reimagining of Huckleberry Finn from Jim\'s perspective, winner of both Pulitzer and National Book Award.',
             'isbn13': '9780385550369',
             'cover_url': None},
            
            # 2023年美国国家图书奖小说奖
            {'award_name': '美国国家图书奖', 'year': 2023, 'category': '小说', 'rank': 1,
             'title': 'The Rabbit Hutch', 'author': 'Tess Gunty',
             'description': 'A debut novel about loneliness and connection in a small Indiana town.',
             'isbn13': '9780593534668',
             'cover_url': None},
            
            # 2022年美国国家图书奖小说奖
            {'award_name': '美国国家图书奖', 'year': 2022, 'category': '小说', 'rank': 1,
             'title': 'The Rabbit Hutch', 'author': 'Tess Gunty',
             'description': 'A debut novel about loneliness and connection in a small Indiana town.',
             'isbn13': '9780593534668',
             'cover_url': None},
            
            # ========================================
            # 星云奖 (Nebula Award)
            # ========================================
            # 2023年星云奖最佳长篇小说
            {'award_name': '星云奖', 'year': 2023, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'Babel: Or the Necessity of Violence', 'author': 'R.F. Kuang',
             'description': 'A dark academia fantasy about a magical translation institute in 1830s Oxford, exploring colonialism and language.',
             'isbn13': '9780063021426',
             'cover_url': None},
            
            # 2022年星云奖最佳长篇小说
            {'award_name': '星云奖', 'year': 2022, 'category': '最佳长篇小说', 'rank': 1,
             'title': 'A Desolation Called Peace', 'author': 'Arkady Martine',
             'description': 'Sequel to A Memory Called Empire, continuing the story of an interstellar empire and its complex diplomatic relations.',
             'isbn13': '9781250186461',
             'cover_url': None},
            
            # ========================================
            # 国际布克奖 (International Booker Prize)
            # ========================================
            # 2024年国际布克奖
            {'award_name': '国际布克奖', 'year': 2024, 'category': '翻译小说', 'rank': 1,
             'title': 'Kairos', 'author': 'Jenny Erpenbeck',
             'description': 'A love story set in East Germany before the fall of the Berlin Wall, exploring personal and political transformation.',
             'isbn13': '9780811232011',
             'cover_url': None},
            
            # 2023年国际布克奖
            {'award_name': '国际布克奖', 'year': 2023, 'category': '翻译小说', 'rank': 1,
             'title': 'Time Shelter', 'author': 'Georgi Gospodinov',
             'description': 'A novel about a clinic that recreates past decades to help Alzheimer\'s patients, exploring memory and nostalgia.',
             'isbn13': '9781324008372',
             'cover_url': None},
            
            # 2022年国际布克奖
            {'award_name': '国际布克奖', 'year': 2022, 'category': '翻译小说', 'rank': 1,
             'title': 'Tomb of Sand', 'author': 'Geetanjali Shree',
             'description': 'An Indian widow defies expectations and travels to Pakistan to confront her past, translated from Hindi.',
             'isbn13': '9781953861162',
             'cover_url': None},
            
            # ========================================
            # 爱伦·坡奖 (Edgar Award)
            # ========================================
            # 2024年爱伦·坡奖最佳小说
            {'award_name': '爱伦·坡奖', 'year': 2024, 'category': '最佳小说', 'rank': 1,
             'title': 'The River We Remember', 'author': 'William Kent Krueger',
             'description': 'A murder mystery set in 1950s Minnesota, exploring small-town secrets and racial tensions.',
             'isbn13': '9781982178697',
             'cover_url': None},
            
            # 2023年爱伦·坡奖最佳小说
            {'award_name': '爱伦·坡奖', 'year': 2023, 'category': '最佳小说', 'rank': 1,
             'title': 'The Accomplice', 'author': 'Lisa Lutz',
             'description': 'A psychological thriller about two lifelong friends bound by a dark secret from their teenage years.',
             'isbn13': '9781982168322',
             'cover_url': None},
            
            # 2022年爱伦·坡奖最佳小说
            {'award_name': '爱伦·坡奖', 'year': 2022, 'category': '最佳小说', 'rank': 1,
             'title': 'Billy Summers', 'author': 'Stephen King',
             'description': 'A hired killer with a conscience takes on one last job, but things go terribly wrong.',
             'isbn13': '9781982173616',
             'cover_url': None},
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
        
        # 为没有本地封面的图书获取 Google Books 封面
        _fetch_missing_covers(app)
        
    except Exception as e:
        app.logger.error(f"❌ 初始化示例图书失败: {e}", exc_info=True)
        db.session.rollback()


def _fetch_missing_covers(app):
    """为缺失封面的图书获取封面（优先使用 Open Library，回退到 Google Books）"""
    try:
        from .models.schemas import AwardBook
        from .services import OpenLibraryClient, GoogleBooksClient, ImageCacheService
        
        # 创建客户端
        openlib_client = OpenLibraryClient(timeout=10)
        google_client = GoogleBooksClient(
            api_key=app.config.get('GOOGLE_API_KEY'),
            base_url='https://www.googleapis.com/books/v1/volumes',
            timeout=10
        )
        
        image_cache = ImageCacheService(
            cache_dir=app.config['IMAGE_CACHE_DIR'],
            default_cover='/static/default-cover.png'
        )
        
        # 获取需要更新封面的图书
        books = AwardBook.query.filter(
            (AwardBook.cover_local_path.is_(None)) | 
            (AwardBook.cover_local_path == '/static/default-cover.png')
        ).all()
        
        if not books:
            app.logger.info("✅ 所有图书已有封面")
            return
        
        app.logger.info(f"📚 开始为 {len(books)} 本图书获取封面...")
        
        updated = 0
        failed_books = []
        
        for i, book in enumerate(books, 1):
            try:
                cover_url = None
                source = None
                
                # 第一步：尝试 Open Library（免费，无需 API Key）
                if book.isbn13:
                    cover_url = openlib_client.get_cover_url(book.isbn13, size='L')
                    if cover_url:
                        source = 'Open Library'
                
                # 第二步：如果 Open Library 失败，尝试 Google Books
                if not cover_url:
                    cover_url = google_client.get_cover_url(
                        isbn=book.isbn13,
                        title=book.title,
                        author=book.author
                    )
                    if cover_url:
                        source = 'Google Books'
                
                if not cover_url:
                    app.logger.warning(f"  [{i}/{len(books)}] 未找到封面: {book.title}")
                    failed_books.append(book)
                    continue
                
                # 下载并缓存封面
                cached_url = image_cache.get_cached_image_url(cover_url, ttl=86400*365)
                
                if cached_url and cached_url != '/static/default-cover.png':
                    book.cover_original_url = cover_url
                    book.cover_local_path = cached_url
                    updated += 1
                    app.logger.info(f"  [{i}/{len(books)}] ✅ {book.title[:30]}... ({source})")
                else:
                    app.logger.warning(f"  [{i}/{len(books)}] ⚠️ 下载失败: {book.title[:30]}...")
                    failed_books.append(book)
                
                # 每5本保存一次
                if i % 5 == 0:
                    db.session.commit()
                
                # 延迟避免请求过快
                import time
                time.sleep(0.3)
                
            except Exception as e:
                app.logger.error(f"  [{i}/{len(books)}] ❌ 错误: {e}")
                failed_books.append(book)
                continue
        
        db.session.commit()
        app.logger.info(f"✅ 封面更新完成: {updated}/{len(books)} 本")
        
        # 尝试通过 Open Library API 补充图书详细信息
        if failed_books:
            _enrich_books_from_openlibrary(app, failed_books, openlib_client, image_cache)
        
    except Exception as e:
        app.logger.error(f"❌ 获取封面失败: {e}", exc_info=True)


def _enrich_books_from_openlibrary(app, books, openlib_client, image_cache):
    """通过 Open Library API 补充图书详细信息"""
    try:
        from .models.schemas import AwardBook
        
        app.logger.info(f"📖 尝试通过 Open Library API 补充 {len(books)} 本图书信息...")
        
        enriched = 0
        for i, book in enumerate(books, 1):
            try:
                if not book.isbn13:
                    continue
                
                # 获取图书详情
                book_data = openlib_client.fetch_book_by_isbn(book.isbn13)
                
                if not book_data:
                    continue
                
                # 更新图书信息
                if book_data.get('description') and len(book_data['description']) > len(book.description or ''):
                    book.description = book_data['description']
                
                # 获取封面
                if book_data.get('cover_url') and not book.cover_local_path:
                    cached_url = image_cache.get_cached_image_url(book_data['cover_url'], ttl=86400*365)
                    if cached_url and cached_url != '/static/default-cover.png':
                        book.cover_original_url = book_data['cover_url']
                        book.cover_local_path = cached_url
                        enriched += 1
                        app.logger.info(f"  [{i}/{len(books)}] ✅ 补充信息: {book.title[:30]}...")
                
                # 每3本保存一次
                if i % 3 == 0:
                    db.session.commit()
                
                import time
                time.sleep(0.5)
                
            except Exception as e:
                app.logger.error(f"  [{i}/{len(books)}] ❌ 错误: {e}")
                continue
        
        db.session.commit()
        app.logger.info(f"✅ 信息补充完成: {enriched} 本")
        
    except Exception as e:
        app.logger.error(f"❌ 补充图书信息失败: {e}", exc_info=True)


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
