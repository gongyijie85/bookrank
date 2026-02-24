import re
from pathlib import Path

from flask import Blueprint, render_template, send_from_directory, abort, request, current_app
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单"""
    default_category = list(current_app.config['CATEGORIES'].keys())[0]
    category = request.args.get('category', default_category)
    search_query = request.args.get('search', '')
    view_mode = request.args.get('view', 'list')
    
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
    
    if search_query and books_data:
        books_data = [b for b in books_data if 
                      search_query.lower() in b.get('title', '').lower() or 
                      search_query.lower() in b.get('author', '').lower()]
    
    return render_template('index.html', 
                          categories=current_app.config['CATEGORIES'],
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
    
    selected_award = request.args.get('award', '')
    selected_year = request.args.get('year', '')
    search_query = request.args.get('search', '')
    view_mode = request.args.get('view', 'grid')
    
    awards_list = Award.query.all()
    
    years = db.session.query(AwardBook.year).distinct().order_by(AwardBook.year.desc()).all()
    years = [y[0] for y in years if y[0]]
    
    query = AwardBook.query.options(joinedload(AwardBook.award)).filter_by(is_displayable=True)
    
    if selected_award:
        award = Award.query.filter_by(name=selected_award).first()
        if award:
            query = query.filter_by(award_id=award.id)
    
    if selected_year:
        query = query.filter_by(year=int(selected_year))
    
    books = query.order_by(AwardBook.year.desc()).all()
    
    if search_query and books:
        books = [b for b in books if 
                 search_query.lower() in b.title.lower() or 
                 search_query.lower() in b.author.lower()]
    
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
