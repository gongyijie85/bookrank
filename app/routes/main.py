import re
from pathlib import Path

from flask import Blueprint, render_template, send_from_directory, abort, request, current_app
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单"""
    # 获取分类参数（带默认值和验证）
    categories = current_app.config['CATEGORIES']
    default_category = list(categories.keys())[0]

    # 验证分类参数
    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category

    search_query = request.args.get('search', '').strip()[:100]  # 限制搜索词长度
    view_mode = request.args.get('view', 'list')
    if view_mode not in ['grid', 'list']:
        view_mode = 'list'

    books_data = []
    update_time = None

    try:
        book_service = current_app.extensions.get('book_service')
        if book_service:
            books = book_service.get_books_by_category(category)
            if books:
                books_data = [book.to_dict() for book in books]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to get cached books: {e}")
        books_data = []

    try:
        if book_service:
            update_time = book_service._cache.get_cache_time(f"books_{category}")
    except Exception:
        update_time = None

    # 简单的搜索过滤（内存中）
    if search_query and books_data:
        search_lower = search_query.lower()
        books_data = [
            b for b in books_data
            if search_lower in b.get('title', '').lower()
            or search_lower in b.get('author', '').lower()
        ]

    return render_template('index.html',
                          categories=categories,
                          books=books_data,
                          current_category=category,
                          search_query=search_query,
                          view_mode=view_mode,
                          update_time=update_time)


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


@main_bp.route('/static/<path:path>')
def send_static(path: str):
    """提供静态文件"""
    return send_from_directory('static', path)


@main_bp.route('/awards')
def awards():
    """图书奖项榜单页面"""
    from ..models.schemas import Award, AwardBook, db
    from sqlalchemy import func

    # 获取请求参数并验证
    selected_award = request.args.get('award', '')
    selected_year = request.args.get('year', '')

    # 验证年份
    if selected_year:
        try:
            year_int = int(selected_year)
            if year_int < 1900 or year_int > 2100:
                selected_year = ''
        except ValueError:
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

    # 构建查询（使用 joinedload 优化性能）
    query = AwardBook.query.options(joinedload(AwardBook.award)).filter_by(is_displayable=True)

    if selected_award:
        award = Award.query.filter_by(name=selected_award).first()
        if award:
            query = query.filter_by(award_id=award.id)

    if selected_year:
        query = query.filter_by(year=int(selected_year))

    # 获取书籍数据（先排序再取全部）
    books = query.order_by(AwardBook.year.desc()).all()

    # 内存中过滤搜索结果
    if search_query:
        search_lower = search_query.lower()
        books = [
            b for b in books
            if search_lower in b.title.lower()
            or search_lower in b.author.lower()
        ]

    # 转换为字典列表
    books_data = []
    for book in books:
        book_dict = {
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
        }
        books_data.append(book_dict)

    # 统计每个奖项的图书数量
    book_counts = dict(
        db.session.query(AwardBook.award_id, func.count(AwardBook.id))
        .group_by(AwardBook.award_id)
        .all()
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


@main_bp.route('/new-books')
def new_books():
    """新书速递页面"""
    from ..models.new_book import Publisher, NewBook
    from ..services.new_book_service import NewBookService
    from ..models.database import db
    from sqlalchemy import func
    from sqlalchemy.exc import OperationalError

    service = NewBookService()

    # 尝试获取出版社列表，如果失败则初始化数据库
    try:
        publishers = service.get_publishers(active_only=True)
    except OperationalError as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no such column" in error_msg:
            current_app.logger.warning(f"⚠️ 数据库表不存在，正在初始化: {e}")
            db.create_all()
            service.init_publishers()
            publishers = service.get_publishers(active_only=True)
        else:
            raise

    # 获取筛选参数
    selected_publisher = request.args.get('publisher', '', type=int)
    selected_category = request.args.get('category', '')
    selected_days = request.args.get('days', 30, type=int)
    search_query = request.args.get('search', '').strip()[:100]
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # 验证参数
    selected_days = min(max(1, selected_days), 365)
    page = min(max(1, page), 10000)

    view_mode = request.args.get('view', 'grid')
    if view_mode not in ['grid', 'list']:
        view_mode = 'grid'

    # 获取分类列表
    categories = service.get_categories()

    # 获取统计数据
    stats = service.get_statistics()

    # 获取书籍数据
    if search_query:
        books, total = service.search_books(search_query, page, per_page)
    else:
        books, total = service.get_new_books(
            publisher_id=selected_publisher if selected_publisher else None,
            category=selected_category if selected_category else None,
            days=selected_days,
            page=page,
            per_page=per_page
        )

    # 计算分页信息
    total_pages = (total + per_page - 1) // per_page

    return render_template('new_books.html',
                          publishers=publishers,
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
    """出版社导航页面 - 显示44个出版社链接"""
    publishers_data = [
        {
            "category": "1. 综合大型出版集团",
            "publishers": [
                {"name": "企鹅兰登书屋", "name_en": "Penguin Random House", "url": "https://www.penguinrandomhouse.com", "description": "全球最大大众出版集团，覆盖小说、非虚构、童书等全品类，新书发布时效性强"},
                {"name": "麦克米伦出版集团", "name_en": "Pan Macmillan", "url": "https://www.panmacmillan.com", "description": "英国老牌出版集团，旗下多子品牌，涵盖文学、教育、童书，侧重英语市场新书"},
                {"name": "哈珀柯林斯", "name_en": "HarperCollins", "url": "https://www.harpercollins.com", "description": "全球领先出版集团，主打畅销书、经典文学，实时更新新书榜单"},
                {"name": "阿歇特图书集团", "name_en": "Hachette Book Group", "url": "https://www.hachettebookgroup.com", "description": "法国阿歇特英美分支，出版大众读物、童书，侧重商业类新书"},
                {"name": "西蒙与舒斯特", "name_en": "Simon & Schuster", "url": "https://www.simonandschuster.com", "description": "美国知名出版社，覆盖小说、非虚构、自助类书籍，新书资讯全面"},
                {"name": "艾伦与昂温", "name_en": "Allen & Unwin", "url": "https://www.allenandunwin.com", "description": "澳大利亚领先独立出版社，侧重本土文学、社科类新书"},
                {"name": "布卢姆斯伯里", "name_en": "Bloomsbury", "url": "https://www.bloomsbury.com", "description": "英国出版社，因《哈利·波特》闻名，兼顾学术与大众类新书"},
            ]
        },
        {
            "category": "2. 童书出版",
            "publishers": [
                {"name": "麦克米伦童书", "name_en": "MacKids", "url": "https://www.mackids.com", "description": "麦克米伦旗下童书子品牌，专注儿童文学、启蒙类新书"},
                {"name": "好奇乌鸦", "name_en": "Nosy Crow", "url": "https://www.nosycrow.com", "description": "英国独立童书社，主打互动绘本、儿童文学类新书"},
                {"name": "奥斯本出版", "name_en": "Usborne Publishing", "url": "https://www.usborne.com", "description": "英国知名童书社，高品质科普、故事类童书新书首发"},
                {"name": "烛芯出版社", "name_en": "Candlewick Press", "url": "https://www.candlewick.com", "description": "美国童书社，聚焦获奖绘本、儿童文学类新书"},
                {"name": "沃克图书澳大利亚", "name_en": "Walker Books Australia", "url": "https://www.walkerbooks.com.au", "description": "沃克集团澳分支，侧重澳洲本土儿童读物新书"},
                {"name": "魔法狮子图书", "name_en": "Enchanted Lion Books", "url": "https://www.enchantedlionbooks.com", "description": "美国独立社，多元文化、艺术导向的童书新书"},
                {"name": "学乐出版", "name_en": "Scholastic", "url": "https://www.scholastic.com", "description": "全球最大儿童教育出版公司，教辅、儿童文学新书全覆盖"},
                {"name": "卡尔顿童书", "name_en": "Carlton Kids Books", "url": "https://www.carltonbooks.co.uk/childrens-books", "description": "英国卡尔顿旗下童书品牌，低幼、益智类新书为主"},
                {"name": "艾格蒙特英国", "name_en": "Egmont UK", "url": "https://www.egmont.co.uk", "description": "北欧出版集团英分支，儿童读物、教育类新书"},
            ]
        },
        {
            "category": "3. 艺术、设计、科普、图文",
            "publishers": [
                {"name": "泰晤士与哈德逊", "name_en": "Thames & Hudson", "url": "https://www.thameshudson.com", "description": "全球顶尖艺术/设计/建筑类出版社，专业图文新书首发"},
                {"name": "劳伦斯·金出版", "name_en": "Laurence King Publishing", "url": "https://www.laurenceking.com", "description": "艺术、设计、流行文化类专业新书，侧重创意类读物"},
                {"name": "DK出版", "name_en": "DK", "url": "https://www.dk.com", "description": "图文并茂的科普、百科类新书，适合全年龄段"},
                {"name": "普雷斯特尔出版", "name_en": "Prestel Publishing", "url": "https://www.prestelpublishing.com", "description": "德国艺术出版社，艺术、建筑、摄影类专业新书"},
                {"name": "纪事图书", "name_en": "Chronicle Books", "url": "https://www.chroniclebooks.com", "description": "美国出版社，精美礼品书、艺术/生活方式类新书"},
                {"name": "夸托集团", "name_en": "Quarto Group", "url": "https://www.quartogroup.com", "description": "全球图文类图书集团，手工、生活、科普类新书"},
                {"name": "国家地理学习", "name_en": "National Geographic Learning", "url": "https://www.ngl.cengage.com", "description": "国家地理旗下教育品牌，科普、地理类教育新书"},
            ]
        },
        {
            "category": "4. 学术与教育出版",
            "publishers": [
                {"name": "剑桥大学出版社", "name_en": "Cambridge University Press", "url": "https://www.cambridge.org", "description": "顶尖学术出版社，学术著作、教材类新书，侧重高等教育"},
                {"name": "麦克米伦教育", "name_en": "Macmillan Education", "url": "https://www.macmillaneducation.com", "description": "全球教育出版服务商，K12、高等教育教材新书"},
                {"name": "洞察出版", "name_en": "Insight Editions", "url": "https://www.insighteditions.com", "description": "流行文化、艺术、教育类图文新书，侧重文创类"},
                {"name": "DC加拿大教育出版", "name_en": "DC Canada Education Publishing", "url": "https://www.dccanada.com", "description": "加拿大教育/儿童图书出版社，本土教材、童书新书"},
            ]
        },
        {
            "category": "5. 图书行业资讯、批发、目录",
            "publishers": [
                {"name": "出版人周刊", "name_en": "Publishers Weekly", "url": "https://www.publishersweekly.com", "description": "美国权威出版行业媒体，全球新书动态、行业资讯汇总"},
                {"name": "加德纳图书批发", "name_en": "Gardners Books", "url": "https://www.gardners.com", "description": "英国最大图书批发商，全品类图书目录、新书批发信息"},
                {"name": "沃克曼出版", "name_en": "Workman Publishing", "url": "https://www.workman.com", "description": "美国出版社，实用类、生活方式、童书目录及新书"},
                {"name": "21世纪阅读", "name_en": "21st Century Reading", "url": "https://21stcenturyreading.com", "description": "在线电子书资源平台，新书电子版首发、阅读资源"},
                {"name": "足迹读者图书馆", "name_en": "Footprint Reader Library", "url": "https://footprintreaders.com", "description": "在线阅读图书馆，新书借阅、电子图书目录"},
                {"name": "国家地理连接", "name_en": "my NG connect", "url": "https://myngconnect.com", "description": "国家地理教育资源平台，科普类新书、教学资源"},
                {"name": "剑桥学习平台", "name_en": "Cambridge LMS", "url": "https://www.cambridge.org/education", "description": "剑桥大学出版社在线教育平台，教材类新书、学习资源"},
                {"name": "本屋俱乐部", "name_en": "Honyaclub", "url": "https://www.honyaclub.com", "description": "日本在线书店，日系新书、进口图书目录"},
                {"name": "未来屋书店", "name_en": "mibon.jp", "url": "https://www.mibon.jp", "description": "日本大型连锁书店在线平台，日文/外文新书资讯"},
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
