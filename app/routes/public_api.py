"""
公开API路由
供外部系统调用的API接口
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from functools import wraps

from ..models.schemas import AwardBook, Award
from ..models.database import db
from ..services import BookService
from ..utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

public_api_bp = Blueprint('public_api', __name__, url_prefix='/api/public')


class PublicAPIResponse:
    """统一API响应格式"""
    
    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        return jsonify(response), status_code
    
    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


def rate_limit(max_requests=60, window=60):
    """
    API限流装饰器
    
    Args:
        max_requests: 时间窗口内最大请求数
        window: 时间窗口（秒）
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limiter = get_rate_limiter(max_requests, window)
            client_id = request.remote_addr or 'unknown'
            
            if not limiter.is_allowed(client_id):
                retry_after = limiter.get_retry_after(client_id)
                return PublicAPIResponse.error(
                    f'Rate limit exceeded. Retry after {retry_after}s.',
                    429
                )
            
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ============================================
# 畅销书API
# ============================================

@public_api_bp.route('/bestsellers')
@rate_limit(max_requests=60, window=60)
def get_all_bestsellers():
    """
    获取所有分类畅销书
    
    Query Parameters:
        limit (int): 每个分类返回的图书数量，默认10，最大50
    
    Returns:
        {
            "success": true,
            "data": {
                "categories": {...},
                "books": {
                    "hardcover-fiction": [...],
                    "hardcover-nonfiction": [...],
                    ...
                },
                "last_updated": "2024-01-01T00:00:00Z"
            }
        }
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(limit, 50)  # 最大50本
        
        book_service: BookService = public_api_bp.book_service
        categories = current_app.config.get('CATEGORIES', {})
        
        all_books = {}
        for cat_id, cat_name in categories.items():
            books = book_service.get_books_by_category(cat_id)
            all_books[cat_id] = {
                'category_name': cat_name,
                'books': [book.to_dict() for book in books[:limit]]
            }
        
        return PublicAPIResponse.success(data={
            'categories': categories,
            'books': all_books,
            'last_updated': book_service.get_latest_cache_time()
        })
        
    except Exception as e:
        logger.error(f"Error in get_all_bestsellers: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/bestsellers/<category>')
@rate_limit(max_requests=60, window=60)
def get_bestsellers_by_category(category: str):
    """
    获取指定分类畅销书
    
    Path Parameters:
        category (str): 分类ID (hardcover-fiction, hardcover-nonfiction, trade-fiction-paperback, paperback-nonfiction)
    
    Query Parameters:
        limit (int): 返回的图书数量，默认20，最大50
    
    Returns:
        {
            "success": true,
            "data": {
                "category_id": "hardcover-fiction",
                "category_name": "精装小说",
                "books": [...],
                "last_updated": "2024-01-01T00:00:00Z"
            }
        }
    """
    try:
        categories = current_app.config.get('CATEGORIES', {})
        
        if category not in categories:
            return PublicAPIResponse.error(
                f'Invalid category. Available categories: {list(categories.keys())}',
                400
            )
        
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, 50)
        
        book_service: BookService = public_api_bp.book_service
        books = book_service.get_books_by_category(category)
        
        return PublicAPIResponse.success(data={
            'category_id': category,
            'category_name': categories[category],
            'books': [book.to_dict() for book in books[:limit]],
            'total': len(books),
            'last_updated': book_service.get_latest_cache_time()
        })
        
    except Exception as e:
        logger.error(f"Error in get_bestsellers_by_category: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/bestsellers/search')
@rate_limit(max_requests=60, window=60)
def search_bestsellers():
    """
    搜索畅销书
    
    Query Parameters:
        keyword (str): 搜索关键词（必需，至少2个字符）
        limit (int): 返回结果数量，默认20，最大50
    
    Returns:
        {
            "success": true,
            "data": {
                "keyword": "xxx",
                "books": [...],
                "total": 10
            }
        }
    """
    try:
        keyword = request.args.get('keyword', '').strip()
        
        if not keyword:
            return PublicAPIResponse.error('Keyword is required', 400)
        
        if len(keyword) < 2:
            return PublicAPIResponse.error('Keyword must be at least 2 characters', 400)
        
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, 50)
        
        book_service: BookService = public_api_bp.book_service
        results = book_service.search_books(keyword)
        
        return PublicAPIResponse.success(data={
            'keyword': keyword,
            'books': [book.to_dict() for book in results[:limit]],
            'total': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error in search_bestsellers: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


# ============================================
# 获奖图书API
# ============================================

@public_api_bp.route('/awards')
@rate_limit(max_requests=60, window=60)
def get_all_awards():
    """
    获取所有奖项列表
    
    Returns:
        {
            "success": true,
            "data": {
                "awards": [
                    {
                        "id": 1,
                        "name": "普利策奖",
                        "name_en": "Pulitzer Prize",
                        "description": "...",
                        "book_count": 5
                    },
                    ...
                ]
            }
        }
    """
    try:
        awards = Award.query.all()
        
        awards_data = []
        for award in awards:
            book_count = AwardBook.query.filter_by(
                award_id=award.id,
                is_displayable=True
            ).count()
            
            awards_data.append({
                'id': award.id,
                'name': award.name,
                'name_en': award.name_en,
                'description': award.description,
                'book_count': book_count
            })
        
        return PublicAPIResponse.success(data={
            'awards': awards_data,
            'total': len(awards_data)
        })
        
    except Exception as e:
        logger.error(f"Error in get_all_awards: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/awards/<award_name>')
@rate_limit(max_requests=60, window=60)
def get_award_books(award_name: str):
    """
    获取指定奖项的获奖图书
    
    Path Parameters:
        award_name (str): 奖项名称（如：普利策奖、布克奖、雨果奖等）
    
    Query Parameters:
        year (int): 筛选年份（可选）
        limit (int): 返回数量，默认20，最大50
    
    Returns:
        {
            "success": true,
            "data": {
                "award": {...},
                "books": [...],
                "years": [2022, 2023, 2024, 2025]
            }
        }
    """
    try:
        award = Award.query.filter_by(name=award_name).first()
        
        if not award:
            available_awards = [a.name for a in Award.query.all()]
            return PublicAPIResponse.error(
                f'Award not found. Available awards: {available_awards}',
                404
            )
        
        query = AwardBook.query.filter_by(
            award_id=award.id,
            is_displayable=True
        )
        
        # 年份筛选
        year = request.args.get('year', type=int)
        if year:
            query = query.filter_by(year=year)
        
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, 50)
        
        books = query.order_by(AwardBook.year.desc()).limit(limit).all()
        
        # 获取所有年份
        years_query = db.session.query(AwardBook.year).filter_by(
            award_id=award.id,
            is_displayable=True
        ).distinct().order_by(AwardBook.year.desc()).all()
        years = [y[0] for y in years_query]
        
        return PublicAPIResponse.success(data={
            'award': {
                'id': award.id,
                'name': award.name,
                'name_en': award.name_en,
                'description': award.description
            },
            'books': [book.to_dict() for book in books],
            'total': len(books),
            'years': years
        })
        
    except Exception as e:
        logger.error(f"Error in get_award_books: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/awards/<award_name>/<int:year>')
@rate_limit(max_requests=60, window=60)
def get_award_books_by_year(award_name: str, year: int):
    """
    获取指定奖项和年份的获奖图书
    
    Path Parameters:
        award_name (str): 奖项名称
        year (int): 年份
    
    Returns:
        {
            "success": true,
            "data": {
                "award": {...},
                "year": 2024,
                "books": [...]
            }
        }
    """
    try:
        award = Award.query.filter_by(name=award_name).first()
        
        if not award:
            available_awards = [a.name for a in Award.query.all()]
            return PublicAPIResponse.error(
                f'Award not found. Available awards: {available_awards}',
                404
            )
        
        books = AwardBook.query.filter_by(
            award_id=award.id,
            year=year,
            is_displayable=True
        ).order_by(AwardBook.rank).all()
        
        if not books:
            return PublicAPIResponse.error(
                f'No books found for {award_name} in {year}',
                404
            )
        
        return PublicAPIResponse.success(data={
            'award': {
                'id': award.id,
                'name': award.name,
                'name_en': award.name_en
            },
            'year': year,
            'books': [book.to_dict() for book in books],
            'total': len(books)
        })
        
    except Exception as e:
        logger.error(f"Error in get_award_books_by_year: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


# ============================================
# 图书详情API
# ============================================

@public_api_bp.route('/book/<isbn>')
@rate_limit(max_requests=60, window=60)
def get_book_details(isbn: str):
    """
    获取图书详细信息
    
    Path Parameters:
        isbn (str): 图书ISBN-13
    
    Returns:
        {
            "success": true,
            "data": {
                "book": {...}
            }
        }
    """
    try:
        # 先在畅销书中查找
        book_service: BookService = public_api_bp.book_service
        all_books = []
        
        for cat_id in current_app.config['CATEGORIES'].keys():
            all_books.extend(book_service.get_books_by_category(cat_id))
        
        book = next((b for b in all_books if b.isbn13 == isbn), None)
        
        if book:
            return PublicAPIResponse.success(data={
                'book': book.to_dict(),
                'source': 'bestseller'
            })
        
        # 在获奖图书中查找
        award_book = AwardBook.query.filter_by(isbn13=isbn).first()
        
        if award_book:
            return PublicAPIResponse.success(data={
                'book': award_book.to_dict(),
                'source': 'award'
            })
        
        return PublicAPIResponse.error('Book not found', 404)
        
    except Exception as e:
        logger.error(f"Error in get_book_details: {e}", exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


# ============================================
# API信息
# ============================================

@public_api_bp.route('/')
def api_info():
    """
    API信息端点
    
    Returns:
        {
            "success": true,
            "data": {
                "name": "BookRank Public API",
                "version": "1.0.0",
                "endpoints": [...]
            }
        }
    """
    return PublicAPIResponse.success(data={
        'name': 'BookRank Public API',
        'version': '1.0.0',
        'description': '提供畅销书排行榜和获奖图书数据的公开API',
        'endpoints': [
            {
                'path': '/api/public/bestsellers',
                'method': 'GET',
                'description': '获取所有分类畅销书'
            },
            {
                'path': '/api/public/bestsellers/<category>',
                'method': 'GET',
                'description': '获取指定分类畅销书'
            },
            {
                'path': '/api/public/bestsellers/search',
                'method': 'GET',
                'description': '搜索畅销书'
            },
            {
                'path': '/api/public/awards',
                'method': 'GET',
                'description': '获取所有奖项列表'
            },
            {
                'path': '/api/public/awards/<award_name>',
                'method': 'GET',
                'description': '获取指定奖项的获奖图书'
            },
            {
                'path': '/api/public/awards/<award_name>/<year>',
                'method': 'GET',
                'description': '获取指定奖项和年份的获奖图书'
            },
            {
                'path': '/api/public/book/<isbn>',
                'method': 'GET',
                'description': '获取图书详细信息'
            }
        ],
        'rate_limit': '60 requests per minute per IP',
        'documentation': 'https://github.com/gongyijie85/bookrank#api-documentation'
    })
