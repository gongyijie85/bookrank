import re
from pathlib import Path

from flask import Blueprint, render_template, send_from_directory, abort, request
from werkzeug.utils import secure_filename

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单"""
    from flask import current_app
    
    # 获取分类参数
    category = request.args.get('category', 'combined-print-and-e-book-fiction')
    search_query = request.args.get('search', '')
    view_mode = request.args.get('view', 'grid')
    
    # TODO: 从缓存或API获取畅销书数据
    # 暂时返回空数据，等待数据同步
    books_data = []
    
    return render_template('index.html', 
                          categories=current_app.config['CATEGORIES'],
                          books=books_data,
                          current_category=category,
                          search_query=search_query,
                          view_mode=view_mode)


@main_bp.route('/cache/images/<filename>')
def cached_image(filename: str):
    """
    提供缓存的图片文件
    
    安全注意：验证文件名格式，防止路径遍历攻击
    """
    # 验证文件名格式（只允许MD5哈希格式的文件名）
    if not re.match(r'^[a-f0-9]{32}\.jpg$', filename):
        abort(404)
    
    # 使用secure_filename进一步确保安全
    safe_filename = secure_filename(filename)
    
    from flask import current_app
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
    
    # 获取筛选参数
    selected_award = request.args.get('award', '')
    selected_year = request.args.get('year', '')
    search_query = request.args.get('search', '')
    view_mode = request.args.get('view', 'grid')
    
    # 获取所有奖项
    awards_list = Award.query.all()
    
    # 获取所有年份（从图书数据中提取）
    years = db.session.query(AwardBook.year).distinct().order_by(AwardBook.year.desc()).all()
    years = [y[0] for y in years if y[0]]
    
    # 构建图书查询
    query = AwardBook.query
    
    if selected_award:
        award = Award.query.filter_by(name=selected_award).first()
        if award:
            query = query.filter_by(award_id=award.id)
    
    if selected_year:
        query = query.filter_by(year=int(selected_year))
    
    # 获取图书数据
    books = query.order_by(AwardBook.year.desc()).all()
    
    # 处理搜索
    if search_query and books:
        books = [b for b in books if 
                 search_query.lower() in b.title.lower() or 
                 search_query.lower() in b.author.lower()]
    
    # 为每本书添加奖项名称
    for book in books:
        award = Award.query.get(book.award_id)
        book.award_name = award.name if award else '未知奖项'
    
    return render_template('awards.html',
                          awards=awards_list,
                          books=books,
                          years=years,
                          selected_award=selected_award,
                          selected_year=selected_year if selected_year else None,
                          search_query=search_query,
                          view_mode=view_mode,
                          total_books=len(books))
