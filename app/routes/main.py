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
                update_time = book_service._cache.get_cache_time(f"books_{category}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to get cached books: {e}")

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
