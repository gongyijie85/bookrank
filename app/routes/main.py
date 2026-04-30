import re
import logging
import threading
from pathlib import Path
from typing import Optional, Tuple

from flask import Blueprint, render_template, send_from_directory, abort, request, current_app
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload

from ..utils import clean_translation_text

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


def _get_books_for_category(category: str) -> Tuple[list, Optional[str]]:
    """
    获取指定分类的书籍数据（统一入口）
    
    Returns:
        (books_data, update_time)
    """
    categories = current_app.config['CATEGORIES']
    default_category = list(categories.keys())[0]
    
    if category not in categories:
        category = default_category
    
    books_data = []
    update_time = None
    
    try:
        book_service = current_app.extensions.get('book_service')
        if book_service:
            books = book_service.get_books_by_category(category)
            if books:
                books_data = [book.to_dict() for book in books]
    except Exception as e:
        logger.warning(f"Failed to get cached books: {e}")
        books_data = []
    
    try:
        if book_service:
            update_time = book_service._cache.get_cache_time(f"books_{category}")
    except Exception:
        update_time = None
    
    return books_data, update_time


def _filter_books_by_search(books_data: list, search_query: str) -> list:
    """根据搜索词过滤书籍列表（内存中）"""
    if not search_query or not books_data:
        return books_data
    
    search_lower = search_query.lower()
    return [
        b for b in books_data
        if search_lower in b.get('title', '').lower()
        or search_lower in b.get('author', '').lower()
    ]


def _filter_books_by_publisher(books_data: list, publisher: str) -> list:
    """根据出版社过滤书籍列表"""
    if not publisher or not books_data:
        return books_data
    publisher_lower = publisher.lower()
    return [b for b in books_data if publisher_lower in b.get('publisher', '').lower()]


def _filter_books_by_weeks(books_data: list, weeks_filter: str) -> list:
    """根据上榜周数过滤书籍列表"""
    if not weeks_filter or not books_data:
        return books_data
    
    if weeks_filter == 'new':
        return [b for b in books_data if b.get('weeks_on_list', 0) <= 1]
    elif weeks_filter == 'trending':
        return [b for b in books_data if 2 <= b.get('weeks_on_list', 0) <= 4]
    elif weeks_filter == 'classic':
        return [b for b in books_data if b.get('weeks_on_list', 0) >= 5]
    return books_data


def _sort_books(books_data: list, sort_by: str) -> list:
    """对书籍列表进行排序"""
    if not books_data:
        return books_data
    
    if sort_by == 'rank_change':
        # 按排名变化幅度排序（变化大的在前）
        def rank_change_key(b):
            try:
                last_week = int(b.get('rank_last_week', '0') or '0')
                current = b.get('rank', 999)
                return abs(last_week - current) if last_week > 0 else 0
            except (ValueError, TypeError):
                return 0
        return sorted(books_data, key=rank_change_key, reverse=True)
    
    elif sort_by == 'weeks_desc':
        # 按上榜周数降序
        return sorted(books_data, key=lambda b: b.get('weeks_on_list', 0), reverse=True)
    
    elif sort_by == 'weeks_asc':
        # 按上榜周数升序（新书在前）
        return sorted(books_data, key=lambda b: b.get('weeks_on_list', 999))
    
    # 默认按排名排序
    return books_data


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单（支持多维度筛选和排序）"""
    categories = current_app.config['CATEGORIES']
    default_category = list(categories.keys())[0]
    
    # 获取并验证参数
    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category
    
    search_query = request.args.get('search', '').strip()[:100]
    view_mode = request.args.get('view', 'list')
    if view_mode not in ['grid', 'list']:
        view_mode = 'list'
    
    # 新增筛选参数
    publisher_filter = request.args.get('publisher', '').strip()
    weeks_filter = request.args.get('weeks', '')  # new/trending/classic
    sort_by = request.args.get('sort', '')  # rank_change/weeks_desc/weeks_asc
    
    # 获取书籍数据
    books_data, update_time = _get_books_for_category(category)
    
    # 应用筛选（顺序：搜索 -> 出版社 -> 上榜周数）
    if search_query:
        books_data = _filter_books_by_search(books_data, search_query)
    if publisher_filter:
        books_data = _filter_books_by_publisher(books_data, publisher_filter)
    if weeks_filter:
        books_data = _filter_books_by_weeks(books_data, weeks_filter)
    
    # 排序
    if sort_by:
        books_data = _sort_books(books_data, sort_by)
    
    # 获取所有出版社列表（用于筛选下拉框）
    publishers = sorted(set(
        b.get('publisher', '') for b in books_data 
        if b.get('publisher') and b.get('publisher') not in ('Unknown', 'Unknown Publisher')
    ))
    
    return render_template('index.html',
                          categories=categories,
                          books=books_data,
                          current_category=category,
                          search_query=search_query,
                          view_mode=view_mode,
                          update_time=update_time,
                          publishers=publishers,
                          publisher_filter=publisher_filter,
                          weeks_filter=weeks_filter,
                          sort_by=sort_by)


@main_bp.route('/cache/images/<filename>')
def cached_image(filename: str):
    """
    提供缓存的图片文件

    安全注意：验证文件名格式，防止路径遍历攻击
    """
    # 严格验证文件名格式：32位十六进制哈希
    if not re.match(r'^[a-f0-9]{32}\.jpg$', filename):
        abort(404)

    safe_filename = secure_filename(filename)
    cache_dir = current_app.config.get('IMAGE_CACHE_DIR', Path('cache/images'))

    return send_from_directory(cache_dir, safe_filename)





@main_bp.route('/awards')
def awards():
    """图书奖项榜单页面"""
    from ..models.schemas import Award, AwardBook, db
    from sqlalchemy import func

    try:
        selected_award = request.args.get('award', '')
        selected_year = request.args.get('year', '')
        
        # 验证年份
        if selected_year:
            try:
                year_int = int(selected_year)
                if year_int < 1900 or year_int > 2100:
                    selected_year = ''
            except (ValueError, TypeError):
                selected_year = ''
        
        search_query = request.args.get('search', '').strip()[:100]
        view_mode = request.args.get('view', 'grid')
        if view_mode not in ['grid', 'list']:
            view_mode = 'grid'
        
        # 查询奖项列表
        awards_list = Award.query.all()
        
        # 获取所有可用年份
        years = db.session.query(AwardBook.year).distinct().order_by(AwardBook.year.desc()).all()
        years = [y[0] for y in years if y[0]]
        
        # 构建查询
        query = AwardBook.query.options(joinedload(AwardBook.award)).filter_by(is_displayable=True)
        
        if selected_award:
            award = Award.query.filter_by(name=selected_award).first()
            if award:
                query = query.filter_by(award_id=award.id)
        
        if selected_year:
            query = query.filter_by(year=int(selected_year))
        
        # 获取书籍数据
        books = query.order_by(AwardBook.year.desc()).all()
        
        # 搜索结果过滤
        if search_query:
            search_lower = search_query.lower()
            books = [
                b for b in books
                if search_lower in b.title.lower() or search_lower in b.author.lower()
            ]
        
        # 转换为字典列表（简化逻辑）
        books_data = []
        for book in books:
            books_data.append({
                'id': book.id,
                'title': book.title,
                'author': book.author,
                'description': book.description,
                'details': book.details,
                'cover_local_path': book.cover_local_path,
                'cover_original_url': book.cover_original_url,
                'isbn13': book.isbn13,
                'isbn10': book.isbn10,
                'publisher': book.publisher,
                'publication_year': book.publication_year,
                'year': book.year,
                'category': book.category,
                'award_name': book.award.name if book.award else '未知奖项',
                'buy_links': book.buy_links
            })
        
        # 统计每个奖项的图书数量
        book_counts = dict(
            db.session.query(AwardBook.award_id, func.count(AwardBook.id))
            .group_by(AwardBook.award_id).all()
        )
        for award in awards_list:
            award.book_count = book_counts.get(award.id, 0)
        
        return render_template('awards.html',
                              awards=awards_list,
                              books=books_data,
                              years=years,
                              selected_award=selected_award,
                              selected_year=selected_year if selected_year else None,
                              search_query=search_query,
                              view_mode=view_mode,
                              total_books=len(books_data))
    except Exception as e:
        logger.error(f'Failed to load awards page: {e}', exc_info=True)
        return render_template('awards.html',
                              awards=[],
                              books=[],
                              years=[],
                              selected_award='',
                              selected_year=None,
                              search_query='',
                              view_mode='grid',
                              total_books=0)


@main_bp.route('/new-books')
def new_books():
    """新书速递页面"""

    # 获取筛选参数
    selected_publisher = request.args.get('publisher', '', type=int)
    selected_category = request.args.get('category', '')
    selected_days = min(max(1, request.args.get('days', 30, type=int)), 365)
    search_query = request.args.get('search', '').strip()[:100]
    page = min(max(1, request.args.get('page', 1, type=int)), 10000)
    per_page = 20
    view_mode = request.args.get('view', 'grid')
    if view_mode not in ['grid', 'list']:
        view_mode = 'grid'

    # 初始化服务和数据
    from ..services.new_book_service import NewBookService
    service = NewBookService()

    try:
        publishers = service.get_publishers(active_only=True)
    except Exception as e:
        logger.warning(f"获取出版社列表失败: {e}")
        publishers = []

    # 预计算出版社书籍数量
    publisher_book_counts = {}
    for pub in publishers:
        try:
            publisher_book_counts[pub.id] = pub.books.count() if hasattr(pub, 'books') else 0
        except Exception:
            publisher_book_counts[pub.id] = 0

    try:
        categories = service.get_categories()
    except Exception as e:
        logger.warning(f"获取分类列表失败: {e}")
        categories = []

    try:
        stats = service.get_statistics()
    except Exception as e:
        logger.warning(f"获取统计数据失败: {e}")
        stats = {
            'total_books': 0, 'total_publishers': 0,
            'active_publishers': 0, 'recent_books_7d': 0, 'top_categories': []
        }

    try:
        if search_query:
            books, total = service.search_books(search_query, page, per_page)
        else:
            books, total = service.get_new_books(
                publisher_id=selected_publisher if selected_publisher else None,
                category=selected_category if selected_category else None,
                days=selected_days,
                page=page, per_page=per_page
            )
    except Exception as e:
        logger.warning(f"获取书籍数据失败: {e}")
        books, total = [], 0

    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    return render_template('new_books.html',
                          publishers=publishers,
                          publisher_book_counts=publisher_book_counts,
                          categories=categories,
                          books=books,
                          stats=stats,
                          selected_publisher=selected_publisher,
                          selected_category=selected_category,
                          selected_days=selected_days,
                          search_query=search_query,
                          view_mode=view_mode,
                          page=page,
                          total=total,
                          total_pages=total_pages,
                          per_page=per_page)


@main_bp.route('/publishers')
def publishers():
    """出版社导航页面 - 显示45个出版社链接"""
    publishers_data = [
        {
            "category": "1. 综合大型出版集团",
            "publishers": [
                {"name": "企鹅兰登书屋（全球站）", "name_en": "Penguin Random House", "url": "https://www.penguinrandomhouse.com", "description": "全球最大大众出版集团，全品类新书首发"},
                {"name": "企鹅兰登书屋（英国站）", "name_en": "Penguin UK", "url": "https://www.penguin.co.uk", "description": "企鹅兰登英国区独立站点，本土英文新书资讯"},
                {"name": "麦克米伦出版集团", "name_en": "Pan Macmillan", "url": "https://www.panmacmillan.com", "description": "英国老牌出版集团，英语市场新书为主"},
                {"name": "哈珀柯林斯", "name_en": "HarperCollins", "url": "https://www.harpercollins.com", "description": "全球出版集团，畅销书、经典文学新书榜单"},
                {"name": "阿歇特图书集团", "name_en": "Hachette Book Group", "url": "https://www.hachettebookgroup.com", "description": "阿歇特英美分支，商业类、童书新书"},
                {"name": "西蒙与舒斯特", "name_en": "Simon & Schuster", "url": "https://www.simonandschuster.com", "description": "美国出版社，小说、非虚构类新书全覆盖"},
                {"name": "艾伦与昂温", "name_en": "Allen & Unwin", "url": "https://www.allenandunwin.com", "description": "澳大利亚独立出版社，本土文学社科新书"},
                {"name": "布卢姆斯伯里", "name_en": "Bloomsbury", "url": "https://www.bloomsbury.com", "description": "英国出版社，《哈利·波特》出品方，学术+大众新书"},
            ]
        },
        {
            "category": "2. 童书出版",
            "publishers": [
                {"name": "麦克米伦童书", "name_en": "MacKids", "url": "https://www.mackids.com", "description": "麦克米伦旗下童书子品牌，儿童文学启蒙新书"},
                {"name": "好奇乌鸦", "name_en": "Nosy Crow", "url": "https://www.nosycrow.com", "description": "英国独立童书社，互动绘本、儿童文学新书"},
                {"name": "奥斯本出版", "name_en": "Usborne Publishing", "url": "https://www.usborne.com", "description": "英国童书社，科普故事类童书新书首发"},
                {"name": "烛芯出版社", "name_en": "Candlewick Press", "url": "https://www.candlewick.com", "description": "美国童书社，获奖绘本、儿童文学新书"},
                {"name": "沃克图书澳大利亚", "name_en": "Walker Books Australia", "url": "https://www.walkerbooks.com.au", "description": "沃克集团澳分支，澳洲本土儿童读物新书"},
                {"name": "魔法狮子图书", "name_en": "Enchanted Lion Books", "url": "https://www.enchantedlionbooks.com", "description": "美国独立社，多元文化艺术导向童书新书"},
                {"name": "学乐出版", "name_en": "Scholastic", "url": "https://www.scholastic.com", "description": "全球最大儿童教育出版，教辅儿童文学新书"},
                {"name": "卡尔顿童书", "name_en": "Carlton Kids Books", "url": "https://www.carltonbooks.co.uk/childrens-books", "description": "英国卡尔顿童书，低幼益智类新书"},
                {"name": "艾格蒙特英国", "name_en": "Egmont UK", "url": "https://www.egmont.co.uk", "description": "北欧出版集团英分支，儿童读物教育类新书"},
            ]
        },
        {
            "category": "3. 艺术、设计、科普、图文",
            "publishers": [
                {"name": "泰晤士与哈德逊", "name_en": "Thames & Hudson", "url": "https://www.thameshudson.com", "description": "全球顶尖艺术设计出版社，专业图文新书首发"},
                {"name": "劳伦斯·金出版", "name_en": "Laurence King Publishing", "url": "https://www.laurenceking.com", "description": "艺术设计流行文化类专业新书"},
                {"name": "DK出版", "name_en": "DK", "url": "https://www.dk.com", "description": "图文科普百科新书，全年龄段适用"},
                {"name": "普雷斯特尔出版", "name_en": "Prestel Publishing", "url": "https://www.prestelpublishing.com", "description": "德国艺术出版社，艺术建筑摄影类新书"},
                {"name": "纪事图书", "name_en": "Chronicle Books", "url": "https://www.chroniclebooks.com", "description": "美国出版社，艺术生活方式类精美新书"},
                {"name": "夸托集团", "name_en": "Quarto Group", "url": "https://www.quartogroup.com", "description": "全球图文类集团，手工生活科普新书"},
                {"name": "国家地理学习", "name_en": "National Geographic Learning", "url": "https://www.ngl.cengage.com", "description": "国家地理旗下，科普地理教育类新书"},
            ]
        },
        {
            "category": "4. 学术与教育出版",
            "publishers": [
                {"name": "剑桥大学出版社", "name_en": "Cambridge University Press", "url": "https://www.cambridge.org", "description": "剑桥大学出版社，学术著作教材新书"},
                {"name": "剑桥在线教育平台", "name_en": "Cambridge LMS", "url": "https://www.cambridge.org/education", "description": "剑桥在线教育平台，教材类新书学习资源"},
                {"name": "麦克米伦教育", "name_en": "Macmillan Education", "url": "https://www.macmillaneducation.com", "description": "麦克米伦教育，K12高等教育教材新书"},
                {"name": "洞察出版", "name_en": "Insight Editions", "url": "https://www.insighteditions.com", "description": "流行文化艺术教育类图文新书"},
                {"name": "DC加拿大教育出版", "name_en": "DC Canada Education Publishing", "url": "https://www.dccanada.com", "description": "加拿大教育儿童图书，本土教材童书新书"},
            ]
        },
        {
            "category": "5. 图书行业资讯、批发、目录",
            "publishers": [
                {"name": "出版人周刊", "name_en": "Publishers Weekly", "url": "https://www.publishersweekly.com", "description": "美国权威出版媒体，全球新书动态行业资讯"},
                {"name": "加德纳图书批发", "name_en": "Gardners Books", "url": "https://www.gardners.com", "description": "英国最大图书批发商，全品类新书批发目录"},
                {"name": "沃克曼出版", "name_en": "Workman Publishing", "url": "https://www.workman.com", "description": "美国出版社，实用类生活方式童书目录及新书"},
                {"name": "21世纪阅读", "name_en": "21st Century Reading", "url": "https://21stcenturyreading.com", "description": "在线电子书平台，新书电子版首发阅读资源"},
                {"name": "足迹读者图书馆", "name_en": "Footprint Reader Library", "url": "https://footprintreaders.com", "description": "在线阅读图书馆，新书借阅电子图书目录"},
                {"name": "国家地理连接", "name_en": "my NG connect", "url": "https://myngconnect.com", "description": "国家地理教育资源平台，科普类新书教学资源"},
                {"name": "本屋俱乐部", "name_en": "Honyaclub", "url": "https://www.honyaclub.com", "description": "日本在线书店，日系新书进口图书目录"},
                {"name": "未来屋书店", "name_en": "mibon.jp", "url": "https://www.mibon.jp", "description": "日本连锁书店在线平台，日文外文新书资讯"},
            ]
        },
    ]
    
    total_publishers = sum(len(cat["publishers"]) for cat in publishers_data)
    
    return render_template('publishers.html',
                          publishers_data=publishers_data,
                          total_publishers=total_publishers)


@main_bp.route('/cache-management')
def cache_management():
    """翻译缓存管理页面"""
    return render_template('cache_management.html')


@main_bp.route('/analytics')
def analytics_dashboard():
    """数据统计仪表盘"""
    return render_template('analytics_dashboard.html')


@main_bp.route('/new-book/<int:book_id>')
def new_book_detail(book_id):
    """新书详情页（异步翻译，不阻塞响应）"""
    from ..models.new_book import NewBook
    from ..models.database import db
    import threading
    
    book = NewBook.query.get(book_id)
    
    if not book:
        return render_template('error.html', 
                           message="书籍不存在",
                           back_url=request.referrer or '/new-books')
    
    # 异步翻译（不阻塞响应）
    if not book.title_zh or not book.description_zh:
        def translate_book_async():
            """后台翻译线程"""
            try:
                translation_service = current_app.extensions.get('translation_service')
                if translation_service:
                    with current_app.app_context():
                        fresh_book = NewBook.query.get(book_id)
                        if fresh_book and not fresh_book.title_zh:
                            fresh_book.title_zh = translation_service.translate(
                                fresh_book.title, 'en', 'zh', field_type='title'
                            )
                        if fresh_book and fresh_book.description and not fresh_book.description_zh:
                            fresh_book.description_zh = translation_service.translate(
                                fresh_book.description[:1000], 'en', 'zh', field_type='description'
                            )
                        db.session.commit()
                        logger.info(f"Book {book_id} translated in background")
            except Exception as e:
                logger.warning(f"Background translation failed for book {book_id}: {e}")
        
        thread = threading.Thread(target=translate_book_async, daemon=True)
        thread.start()
    
    return render_template('new_book_detail.html',
                          book=book,
                          back_url=request.referrer or '/new-books')


@main_bp.route('/award-book/<int:book_id>')
def award_book_detail(book_id):
    """获奖图书详情页"""
    from ..models.schemas import AwardBook
    
    # 获取获奖图书
    book = AwardBook.query.get(book_id)
    
    if book:
        # 书籍存在，显示详情页
        return render_template('award_book_detail.html',
                              book=book,
                              back_url=request.referrer or '/awards')
    else:
        # 书籍不存在，返回错误页面
        return render_template('error.html', 
                           message="书籍不存在",
                           back_url=request.referrer or '/awards')


@main_bp.route('/book/<int:book_index>')
def book_detail(book_index):
    """书籍详情页（集成 Google Books API 获取详细信息）"""
    categories = current_app.config['CATEGORIES']
    default_category = list(categories.keys())[0]
    
    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category
    
    # 使用统一函数获取书籍数据
    books_data, _ = _get_books_for_category(category)
    
    # 验证书籍索引
    if book_index < 0 or book_index >= len(books_data):
        return render_template('error.html', 
                           message="书籍不存在",
                           back_url=request.referrer or '/')
    
    book = books_data[book_index]

    # 尝试从 Google Books API 获取详细信息（带多重容错）
    isbn = book.get('isbn13') or book.get('isbn10')
    if isbn:
        _fetch_google_books_details(book, isbn)
        # 合并数据库中的中文翻译（如果没有则触发翻译保存）
        _merge_or_translate_book(book, isbn)

    return render_template('book_detail.html',
                          book=book,
                          book_index=book_index,
                          category=category,
                          back_url=request.referrer or '/?category=' + category)


def _fetch_google_books_details(book: dict, isbn: str) -> None:
    """
    从 Google Books API 获取详细信息并更新 book 字典（带缓存）

    缓存策略：
    - 使用内存缓存，TTL 7 天（Google Books 数据变化不频繁）
    - 缓存键: google_books_detail:{isbn}
    """
    cache_key = f"google_books_detail:{isbn}"
    cache_service = None

    # 尝试获取缓存服务
    try:
        book_service = current_app.extensions.get('book_service')
        if book_service and hasattr(book_service, '_cache'):
            cache_service = book_service._cache
    except Exception:
        pass

    # 尝试从缓存获取
    if cache_service:
        try:
            cached = cache_service.get(cache_key)
            if cached:
                _update_book_from_google_books(book, cached)
                return
        except Exception:
            pass

    # 获取 Google Books 客户端
    google_client = None
    try:
        if book_service and hasattr(book_service, '_google_client'):
            google_client = book_service._google_client
    except Exception:
        pass

    if not google_client:
        try:
            from ..services.api_client import GoogleBooksClient
            google_client = GoogleBooksClient(
                api_key=current_app.config.get('GOOGLE_API_KEY'),
                base_url=current_app.config.get(
                    'GOOGLE_BOOKS_API_URL',
                    'https://www.googleapis.com/books/v1/volumes'
                ),
                timeout=8
            )
        except Exception as e:
            logger.warning(f"创建 Google Books 客户端失败: {e}")
            return

    # 调用 API 获取详情
    try:
        details = google_client.fetch_book_details(isbn)
        if not details:
            return

        _update_book_from_google_books(book, details)

        # 写入缓存（7天）
        if cache_service:
            try:
                cache_service.set(cache_key, details, ttl=604800)
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Google Books API 调用失败 ISBN {isbn}: {e}")


def _translate_field_async(book: dict, source_field: str, target_field: str) -> None:
    """异步翻译书籍字段（不阻塞响应）"""
    def _do_translate():
        try:
            translation_service = current_app.extensions.get('translation_service')
            if translation_service:
                with current_app.app_context():
                    text = book.get(source_field, '')
                    if text and not book.get(target_field):
                        ft = 'title' if target_field == 'title_zh' else 'description' if target_field == 'description_zh' else 'details' if target_field == 'details_zh' else 'text'
                        translated = translation_service.translate(text, 'en', 'zh', field_type=ft)
                        if translated:
                            book[target_field] = translated
                            logger.info(f"已翻译 {source_field} -> {target_field}")
        except Exception as e:
            logger.warning(f"异步翻译失败 {source_field}: {e}")

    thread = threading.Thread(target=_do_translate, daemon=True)
    thread.start()


def _update_book_from_google_books(book: dict, details: dict) -> None:
    """使用 Google Books 数据更新 book 字典（仅更新有效字段），并异步翻译中文"""
    # 详细描述（最高优先级）
    if details.get('details') and details['details'] != 'No detailed description available.':
        book['details'] = details['details']
        # 异步翻译详细描述
        _translate_field_async(book, 'details', 'details_zh')
    
    # 页数
    if details.get('page_count') and details['page_count'] != 'Unknown':
        book['page_count'] = str(details['page_count'])
    
    # 出版日期
    if details.get('publication_dt') and details['publication_dt'] != 'Unknown':
        book['publication_dt'] = details['publication_dt']
    
    # 语言
    if details.get('language') and details['language'] != 'Unknown':
        book['language'] = details['language']
    
    # 出版社（仅当原有数据无效时更新）
    if details.get('publisher') and details['publisher'] not in ('Unknown', 'Unknown Publisher'):
        current_publisher = book.get('publisher', '')
        if not current_publisher or current_publisher in ('Unknown', 'Unknown Publisher'):
            book['publisher'] = details['publisher']
    
    # 封面（仅当没有封面时）
    if details.get('cover_url') and not book.get('cover'):
        book['cover'] = details['cover_url']
    
    # ISBN 补充
    if details.get('isbn_13') and not book.get('isbn13'):
        book['isbn13'] = details['isbn_13']
    if details.get('isbn_10') and not book.get('isbn10'):
        book['isbn10'] = details['isbn_10']
    
    # 翻译简介（如果已有英文描述但没有中文）
    if book.get('description') and not book.get('description_zh'):
        _translate_field_async(book, 'description', 'description_zh')


def _merge_or_translate_book(book: dict, isbn: str) -> None:
    """从数据库合并中文翻译，如果没有则同步翻译并保存"""
    try:
        from ..models.schemas import BookMetadata, db

        # 查询数据库中的翻译
        meta = BookMetadata.query.get(isbn)
        if meta:
            # 合并已有的中文翻译到 book 字典（清理可能的前缀）
            if meta.description_zh and not book.get('description_zh'):
                book['description_zh'] = clean_translation_text(meta.description_zh, 'description')
            if meta.details_zh and not book.get('details_zh'):
                book['details_zh'] = clean_translation_text(meta.details_zh, 'details')
            if meta.title_zh and not book.get('title_zh'):
                book['title_zh'] = clean_translation_text(meta.title_zh, 'title')

            # 如果数据库已经有全部翻译，直接返回
            if meta.title_zh and meta.description_zh and meta.details_zh:
                return

        # 数据库没有翻译，尝试同步翻译并保存
        title = book.get('title', '')
        description = book.get('description', '')
        details = book.get('details', '')

        if not title and not description and not details:
            return

        translation_service = current_app.extensions.get('translation_service')
        if not translation_service:
            return

        title_zh = ''
        description_zh = ''
        details_zh = ''

        # 同步翻译书名
        if title and not book.get('title_zh'):
            try:
                title_zh = translation_service.translate(title, 'en', 'zh', field_type='title')
            except Exception as e:
                logger.warning(f"书名翻译失败: {e}")

        # 同步翻译 description
        if description and description != 'No summary available.':
            try:
                description_zh = translation_service.translate(description, 'en', 'zh', field_type='description')
            except Exception as e:
                logger.warning(f"简介翻译失败: {e}")

        # 同步翻译 details
        if details and details != 'No detailed description available.':
            try:
                details_zh = translation_service.translate(details, 'en', 'zh', field_type='details')
            except Exception as e:
                logger.warning(f"详情翻译失败: {e}")

        # 保存到数据库
        if not meta:
            meta = BookMetadata(
                isbn=isbn,
                title=book.get('title', ''),
                author=book.get('author', '')
            )
            db.session.add(meta)

        if title_zh:
            meta.title_zh = title_zh
            book['title_zh'] = title_zh
        if description_zh:
            meta.description_zh = description_zh
            book['description_zh'] = description_zh
        if details_zh:
            meta.details_zh = details_zh
            book['details_zh'] = details_zh

        from datetime import datetime, timezone
        meta.translated_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info(f"图书 {isbn} 翻译已保存到数据库")

    except Exception as e:
        logger.warning(f"合并/翻译图书失败 {isbn}: {e}")
        db.session.rollback()


@main_bp.route('/api/book-details')
def book_details_api():
    """获取书籍详细信息 API"""
    try:
        book_index = request.args.get('book_index', type=int)
        isbn = request.args.get('isbn')
        category = request.args.get('category')
        
        if book_index is None or not isbn:
            return {'success': False, 'error': 'Missing parameters'}
        
        # 使用统一函数获取书籍数据
        books_data, _ = _get_books_for_category(category or '')
        
        # 验证书籍索引
        if book_index < 0 or book_index >= len(books_data):
            return {'success': False, 'error': 'Book not found'}
        
        book = books_data[book_index]
        details = book.get('description', '暂无详细介绍')
        
        return {'success': True, 'details': details}
    except Exception as e:
        logger.error(f"Error in book details API: {e}")
        return {'success': False, 'error': 'Internal error'}


@main_bp.route('/api/category-books')
def api_category_books():
    """AJAX获取分类图书列表"""
    from flask import jsonify
    
    categories = current_app.config['CATEGORIES']
    category = request.args.get('category', list(categories.keys())[0])
    
    if category not in categories:
        return jsonify({'success': False, 'error': '无效的分类'}), 400
    
    books_data = []
    update_time = None
    
    try:
        book_service = current_app.extensions.get('book_service')
        if book_service:
            books = book_service.get_books_by_category(category)
            if books:
                books_data = [book.to_dict() for book in books]
                update_time = book_service._cache.get_cache_time(f"books_{category}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to get cached books: {e}")
    
    return jsonify({
        'success': True,
        'books': books_data,
        'category': category,
        'update_time': update_time
    })


@main_bp.route('/reports/weekly')
def weekly_reports():
    """周报列表页"""
    from datetime import datetime
    from ..services.weekly_report_service import WeeklyReportService
    
    book_service = current_app.extensions.get('book_service')
    if not book_service:
        return render_template('error.html', message="服务不可用", back_url='/')
    
    report_service = WeeklyReportService(book_service)
    reports = report_service.get_reports()
    return render_template('weekly_reports.html', reports=reports)


def _parse_report_content(report):
    """解析周报内容 JSON"""
    import json
    if not report or not report.content:
        return None
    try:
        content = json.loads(report.content) if isinstance(report.content, str) else report.content
    except (json.JSONDecodeError, TypeError):
        return None
    return content


def _validate_date(date_str: str) -> tuple:
    """验证日期字符串，返回 (是否有效, 错误消息, 日期对象)"""
    from datetime import datetime
    if not date_str or len(date_str) != 10 or date_str[4] != '-' or date_str[7] != '-':
        return False, "日期格式错误", None
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        current_date = datetime.now().date()
        if date_obj.year < 2020 or date_obj > current_date:
            return False, "无效的日期范围", None
        return True, None, date_obj
    except ValueError:
        return False, "日期格式错误", None


@main_bp.route('/reports/weekly/<date>')
def weekly_report_detail(date):
    """周报详情页"""
    from datetime import datetime
    from ..services.weekly_report_service import WeeklyReportService
    from ..models.schemas import ReportView, UserBehavior
    from ..models.database import db
    
    book_service = current_app.extensions.get('book_service')
    if not book_service:
        return render_template('error.html', message="服务不可用", back_url='/reports/weekly')
    
    # 验证日期
    is_valid, error_msg, report_date = _validate_date(date)
    if not is_valid:
        return render_template('error.html', message=error_msg, back_url='/reports/weekly')
    
    report_service = WeeklyReportService(book_service)
    
    try:
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_template('error.html', message="周报不存在", back_url='/reports/weekly')
        
        # 记录浏览行为
        session_id = request.cookies.get('session_id', 'anonymous')
        user_agent = request.user_agent.string[:500]
        ip_address = request.remote_addr
        
        existing_view = ReportView.query.filter_by(
            report_id=report.id,
            session_id=session_id
        ).first()
        
        if not existing_view:
            new_view = ReportView(
                report_id=report.id,
                session_id=session_id,
                user_agent=user_agent,
                ip_address=ip_address
            )
            db.session.add(new_view)
            report.view_count = (report.view_count or 0) + 1
            
            behavior = UserBehavior(
                session_id=session_id,
                event_type='view_report',
                target_id=date,
                target_type='report',
                user_agent=user_agent,
                ip_address=ip_address
            )
            db.session.add(behavior)
            db.session.commit()
        
        content_data = _parse_report_content(report)
        return render_template('weekly_report_detail.html', report=report, content=content_data)
        
    except Exception as e:
        current_app.logger.error(f"周报详情渲染错误: {str(e)}", exc_info=True)
        return render_template('error.html', message="周报加载失败，请稍后再试", back_url='/reports/weekly'), 500

@main_bp.route('/reports/weekly/<date>/export')
def export_weekly_report(date):
    """导出周报"""
    from flask import send_file
    from ..services.weekly_report_service import WeeklyReportService
    from ..services.export_service import ExportService
    from ..models.schemas import UserBehavior
    from ..models.database import db
    
    book_service = current_app.extensions.get('book_service')
    if not book_service:
        return render_template('error.html', message="服务不可用", back_url='/reports/weekly')
    
    # 验证日期
    is_valid, error_msg, report_date = _validate_date(date)
    if not is_valid:
        return render_template('error.html', message=error_msg, back_url='/reports/weekly')
    
    report_service = WeeklyReportService(book_service)
    export_service = ExportService()
    
    try:
        # 尝试根据周结束日期获取周报
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_template('error.html', message="周报不存在", back_url='/reports/weekly')
        
        # 获取导出格式
        format_type = request.args.get('format', 'pdf').lower()
        if format_type not in ['pdf', 'excel']:
            return render_template('error.html', message="不支持的导出格式", back_url=f'/reports/weekly/{date}')
        
        # 导出配置
        export_config = {
            'pdf': {
                'export_method': export_service.export_weekly_report_pdf,
                'error_message': "PDF导出失败",
                'filename': f"bookrank-weekly-report-{date}.pdf",
                'mimetype': 'application/pdf'
            },
            'excel': {
                'export_method': export_service.export_weekly_report_excel,
                'error_message': "Excel导出失败",
                'filename': f"bookrank-weekly-report-{date}.xlsx",
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        }
        
        # 执行导出
        config = export_config[format_type]
        buffer = config['export_method'](report)
        if not buffer:
            return render_template('error.html', message=config['error_message'], back_url=f'/reports/weekly/{date}')
        
        # 记录导出行为
        session_id = request.cookies.get('session_id', 'anonymous')
        user_agent = request.user_agent.string[:500]
        ip_address = request.remote_addr
        
        behavior = UserBehavior(
            session_id=session_id,
            event_type='export_report',
            target_id=date,
            target_type='report',
            user_agent=user_agent,
            ip_address=ip_address
        )
        db.session.add(behavior)
        db.session.commit()
        
        # 返回文件
        return send_file(buffer, as_attachment=True, download_name=config['filename'], mimetype=config['mimetype'])
            
    except Exception as e:
        current_app.logger.error(f"导出周报时出错: {str(e)}")
        return render_template('error.html', message="导出失败", back_url=f'/reports/weekly/{date}')
