import csv
import logging
import re
import secrets
from io import StringIO
from datetime import datetime
from urllib.parse import quote
from functools import wraps

from flask import Blueprint, jsonify, request, make_response, abort, session, current_app
from werkzeug.utils import secure_filename

from ..models.schemas import UserPreference, UserCategory, UserViewedBook, SearchHistory
from ..models.database import db
from ..utils.exceptions import APIRateLimitException, APIException, ValidationException
from ..services import BookService
from ..services.translation_service import TranslationService, translate_book_info
from ..utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ==================== 辅助函数 ====================

def get_session_id() -> str:
    """获取或生成安全的会话ID"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return session['session_id']


def validate_category(category: str) -> bool:
    """验证分类ID是否有效"""
    categories = current_app.config.get('CATEGORIES', {})
    return category in categories or category == 'all'


def validate_isbn(isbn: str) -> bool:
    """验证ISBN格式（ISBN-10 或 ISBN-13）"""
    if not isbn:
        return False
    # 移除非数字字符
    clean_isbn = re.sub(r'[^0-9X]', '', isbn.upper())
    if len(clean_isbn) == 10:
        return bool(re.match(r'^\d{9}[\dX]$', clean_isbn))
    elif len(clean_isbn) == 13:
        return bool(re.match(r'^\d{13}$', clean_isbn))
    return False


def validate_pagination_params(page: int, limit: int) -> tuple[int, int]:
    """验证并规范化分页参数"""
    # 确保 page 至少为 1
    page = max(1, page)
    # 限制每页最大数量，防止滥用
    limit = min(max(1, limit), 100)
    return page, limit


# ==================== 响应类 ====================

class APIResponse:
    """统一API响应格式"""

    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message
        }
        return jsonify(response), status_code

    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


# ==================== 限流装饰器 ====================

def api_rate_limit(max_requests: int = 60, window: int = 60):
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
                response = {
                    'success': False,
                    'message': f'Rate limit exceeded. Retry after {retry_after}s.',
                    'retry_after': retry_after
                }
                return jsonify(response), 429

            return f(*args, **kwargs)
        return wrapped
    return decorator


# ==================== 健康检查 ====================

@api_bp.route('/health')
def health_check():
    """健康检查端点"""
    return APIResponse.success(data={
        'status': 'healthy',
        'service': 'book-rank-api',
        'version': '2.0.0'
    })


@api_bp.route('/books/<category>')
@api_rate_limit(max_requests=60, window=60)
def get_books(category: str):
    """获取图书列表"""
    try:
        # 验证分类参数
        if not category or not isinstance(category, str):
            return APIResponse.error('Invalid category parameter', 400)

        if not validate_category(category):
            return APIResponse.error(
                f'Invalid category. Available categories: {list(current_app.config["CATEGORIES"].keys())} or "all"',
                400
            )

        session_id = get_session_id()
        book_service: BookService = api_bp.book_service

        if category == 'all':
            # 获取所有分类
            all_books = {}
            for cat_id in current_app.config['CATEGORIES'].keys():
                all_books[cat_id] = [
                    book.to_dict()
                    for book in book_service.get_books_by_category(cat_id)
                ]

            # 保存用户偏好
            save_user_categories(session_id, list(current_app.config['CATEGORIES'].keys()))

            return APIResponse.success(data={
                'books': all_books,
                'categories': current_app.config['CATEGORIES'],
                'latest_update': book_service.get_latest_cache_time()
            })
        else:
            # 获取单个分类
            books = book_service.get_books_by_category(category)

            # 保存用户偏好
            save_user_categories(session_id, [category])

            return APIResponse.success(data={
                'books': [book.to_dict() for book in books],
                'category_name': current_app.config['CATEGORIES'].get(category, category),
                'latest_update': book_service.get_latest_cache_time()
            })

    except APIRateLimitException as e:
        logger.warning(f"Rate limit exceeded: {e}")
        return APIResponse.error(
            f'Rate limit exceeded. Retry after {e.retry_after}s',
            429
        )
    except APIException as e:
        logger.error(f"API error: {e}")
        return APIResponse.error(str(e), e.status_code or 500)
    except Exception as e:
        logger.error(f"Unexpected error in get_books: {e}", exc_info=True)
        return APIResponse.error('Internal server error', 500)


@api_bp.route('/search')
@api_rate_limit(max_requests=30, window=60)
def search_books():
    """搜索图书"""
    try:
        keyword = request.args.get('keyword', '').strip()

        # 验证搜索关键词
        if not keyword:
            return APIResponse.error('Search keyword is required', 400)

        if len(keyword) < 2:
            return APIResponse.error('Keyword must be at least 2 characters', 400)

        if len(keyword) > 100:
            return APIResponse.error('Keyword must be at most 100 characters', 400)

        # 防止 SQL 注入和 XSS
        if not re.match(r'^[\w\s\-\u4e00-\u9fff]+$', keyword):
            return APIResponse.error('Invalid keyword format', 400)

        session_id = get_session_id()
        book_service: BookService = api_bp.book_service

        results = book_service.search_books(keyword)

        # 限制返回结果数量
        max_results = 50
        results = results[:max_results]

        save_search_history(session_id, keyword, len(results))

        if results:
            viewed_isbns = [book.id for book in results[:5]]
            save_viewed_books(session_id, viewed_isbns)

        return APIResponse.success(data={
            'books': [book.to_dict() for book in results],
            'count': len(results),
            'latest_update': book_service.get_latest_cache_time()
        })

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return APIResponse.error('Search failed', 500)


@api_bp.route('/search/history')
def get_search_history():
    """获取搜索历史"""
    try:
        session_id = get_session_id()
        limit = request.args.get('limit', 5, type=int)

        # 限制最大返回数量
        limit = min(limit, 20)

        history = SearchHistory.query.filter_by(
            session_id=session_id
        ).order_by(
            SearchHistory.created_at.desc()
        ).limit(limit).all()

        return APIResponse.success(data={
            'history': [h.to_dict() for h in history]
        })

    except Exception as e:
        logger.error(f"Get search history error: {e}", exc_info=True)
        return APIResponse.error('Failed to get search history', 500)


@api_bp.route('/user/preferences', methods=['GET', 'POST'])
def user_preferences():
    """获取或更新用户偏好"""
    try:
        session_id = get_session_id()

        if request.method == 'POST':
            # 验证请求内容类型
            if not request.is_json:
                return APIResponse.error('Content-Type must be application/json', 400)

            data = request.get_json() or {}

            # 获取或创建用户偏好
            preference = UserPreference.query.get(session_id)
            if not preference:
                preference = UserPreference(session_id=session_id)
                db.session.add(preference)

            # 更新视图模式（验证枚举值）
            view_mode = data.get('view_mode')
            if view_mode in ['grid', 'list']:
                preference.view_mode = view_mode

            # 更新分类偏好
            preferred_categories = data.get('preferred_categories')
            if preferred_categories and isinstance(preferred_categories, list):
                # 验证分类有效性
                valid_categories = list(current_app.config.get('CATEGORIES', {}).keys())
                valid_prefs = [c for c in preferred_categories if c in valid_categories]
                if valid_prefs:
                    save_user_categories(session_id, valid_prefs)

            # 更新浏览记录
            last_viewed_isbns = data.get('last_viewed_isbns')
            if last_viewed_isbns and isinstance(last_viewed_isbns, list):
                # 验证 ISBN 格式
                valid_isbns = [isbn for isbn in last_viewed_isbns if validate_isbn(isbn)]
                if valid_isbns:
                    save_viewed_books(session_id, valid_isbns)

            db.session.commit()
            return APIResponse.success(message='Preferences saved')

        else:  # GET
            preference = UserPreference.query.get(session_id)
            if preference:
                return APIResponse.success(data={'preferences': preference.to_dict()})
            else:
                return APIResponse.success(data={'preferences': {}})

    except Exception as e:
        logger.error(f"User preferences error: {e}", exc_info=True)
        db.session.rollback()
        return APIResponse.error('Failed to process preferences', 500)


@api_bp.route('/export/<category>')
def export_csv(category: str):
    """导出CSV"""
    try:
        # 验证分类
        if not validate_category(category):
            return APIResponse.error('Invalid category', 400)

        book_service: BookService = api_bp.book_service

        # 收集数据
        if category == 'all':
            all_books = []
            for cat_id in current_app.config['CATEGORIES'].keys():
                all_books.extend(book_service.get_books_by_category(cat_id))
            books = all_books
        else:
            books = book_service.get_books_by_category(category)

        # 生成CSV
        output = StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow([
            '分类', '书名', '作者', '出版社', '当前排名',
            '上周排名', '上榜周数', '出版日期', '页数',
            '语言', 'ISBN-13', '价格'
        ])

        # 写入数据
        for book in books:
            writer.writerow([
                book.category_name,
                book.title,
                book.author,
                book.publisher,
                book.rank,
                book.rank_last_week,
                book.weeks_on_list,
                book.publication_dt,
                book.page_count,
                book.language,
                book.isbn13,
                book.price
            ])

        # 准备响应
        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

        response = make_response(response_data)
        filename = f'纽约时报畅销书_{category}_{datetime.now().strftime("%Y%m%d")}.csv'
        response.headers["Content-Disposition"] = f"attachment; filename={quote(filename)}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"

        return response

    except Exception as e:
        logger.error(f"Export CSV error: {e}", exc_info=True)
        return APIResponse.error('Export failed', 500)


def save_user_categories(session_id: str, category_ids: list):
    """保存用户分类偏好"""
    try:
        # 获取或创建用户偏好
        preference = UserPreference.query.get(session_id)
        if not preference:
            preference = UserPreference(session_id=session_id)
            db.session.add(preference)
        
        # 清除旧分类
        UserCategory.query.filter_by(session_id=session_id).delete()
        
        # 添加新分类
        for cat_id in category_ids:
            user_cat = UserCategory(session_id=session_id, category_id=cat_id)
            db.session.add(user_cat)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save user categories: {e}")
        db.session.rollback()


def save_viewed_books(session_id: str, isbns: list):
    """保存用户浏览记录"""
    try:
        for isbn in isbns:
            # 使用merge避免重复
            viewed = UserViewedBook(session_id=session_id, isbn=isbn)
            db.session.merge(viewed)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save viewed books: {e}")
        db.session.rollback()


def save_search_history(session_id: str, keyword: str, result_count: int):
    """保存搜索历史"""
    try:
        history = SearchHistory(
            session_id=session_id,
            keyword=keyword,
            result_count=result_count
        )
        db.session.add(history)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save search history: {e}")
        db.session.rollback()


@api_bp.route('/book-details/<isbn>')
def get_book_details(isbn: str):
    """从 Google Books API 获取图书详细信息"""
    try:
        # 验证ISBN格式
        if not validate_isbn(isbn):
            return APIResponse.error('Invalid ISBN format', 400)

        from ..services.api_client import GoogleBooksClient

        # 创建 Google Books 客户端
        google_client = GoogleBooksClient(
            api_key=current_app.config.get('GOOGLE_API_KEY'),
            base_url=current_app.config.get('GOOGLE_BOOKS_API_URL', 'https://www.googleapis.com/books/v1/volumes'),
            timeout=10
        )

        # 获取图书详情
        book_data = google_client.fetch_book_details(isbn)

        if not book_data:
            return APIResponse.error('Book not found in Google Books', 404)

        # 构建封面 URL
        cover_url = None
        if book_data.get('cover_url'):
            cover_url = book_data['cover_url']
        elif book_data.get('isbn_13'):
            # 使用 Open Library 封面作为备选
            cover_url = f"https://covers.openlibrary.org/b/isbn/{book_data['isbn_13']}-L.jpg"

        return APIResponse.success(data={
            'description': book_data.get('details', ''),
            'details': book_data.get('details', ''),
            'cover_url': cover_url,
            'page_count': book_data.get('page_count'),
            'language': book_data.get('language'),
            'publisher': book_data.get('publisher'),
            'publication_date': book_data.get('publication_dt'),
            'buy_links': {}
        })

    except Exception as e:
        logger.error(f"Get book details error: {e}", exc_info=True)
        return APIResponse.error('Failed to fetch book details', 500)


# 错误处理器
@api_bp.errorhandler(404)
def not_found(error):
    return APIResponse.error('Resource not found', 404)


@api_bp.errorhandler(405)
def method_not_allowed(error):
    return APIResponse.error('Method not allowed', 405)


@api_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return APIResponse.error('Internal server error', 500)


# ==================== 翻译相关API (暂时下线) ====================

@api_bp.route('/translate', methods=['POST'])
def translate_text():
    """翻译文本 - 暂时下线"""
    return APIResponse.error('翻译功能暂时下线，将在第三阶段重新上线', 503)


@api_bp.route('/translate/book/<isbn>', methods=['POST'])
def translate_book(isbn: str):
    """翻译单本图书 - 暂时下线"""
    return APIResponse.error('翻译功能暂时下线，将在第三阶段重新上线', 503)


@api_bp.route('/translate/cache/stats')
def get_translation_cache_stats():
    """获取翻译服务状态 - 暂时下线"""
    return APIResponse.success(data={
        'service': 'Google Translate',
        'status': 'offline',
        'description': '翻译功能暂时下线，将在第三阶段重新上线'
    })


@api_bp.route('/translate/cache/clear', methods=['POST'])
def clear_translation_cache():
    """清理翻译缓存 - 暂时下线"""
    return APIResponse.error('翻译功能暂时下线，将在第三阶段重新上线', 503)


# ==================== 国际图书奖项API ====================

@api_bp.route('/awards')
def get_awards():
    """获取所有奖项列表"""
    try:
        from app.models.schemas import Award

        awards = Award.query.all()
        return APIResponse.success(data={
            'awards': [award.to_dict() for award in awards]
        })

    except Exception as e:
        logger.error(f"获取奖项列表错误: {e}", exc_info=True)
        return APIResponse.error('获取奖项列表失败', 500)


@api_bp.route('/awards/<int:award_id>/books')
def get_award_books(award_id: int):
    """获取指定奖项的图书列表"""
    try:
        from app.models.schemas import Award, AwardBook

        # 验证奖项存在
        award = Award.query.get(award_id)
        if not award:
            return APIResponse.error('奖项不存在', 404)

        # 获取筛选参数并验证
        year = request.args.get('year', type=int)
        if year and (year < 1900 or year > 2100):
            return APIResponse.error('无效的年份', 400)

        category = request.args.get('category')

        # 验证并规范化分页参数
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        page, limit = validate_pagination_params(page, limit)

        # 构建查询
        query = AwardBook.query.filter_by(award_id=award_id)

        if year:
            query = query.filter_by(year=year)
        if category:
            query = query.filter_by(category=category)

        # 分页
        total = query.count()
        books = query.order_by(AwardBook.year.desc(), AwardBook.rank.asc()).\
            offset((page - 1) * limit).limit(limit).all()

        return APIResponse.success(data={
            'award': award.to_dict(),
            'books': [book.to_dict() for book in books],
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        logger.error(f"获取奖项图书错误: {e}", exc_info=True)
        return APIResponse.error('获取图书列表失败', 500)


@api_bp.route('/award-books')
def get_all_award_books():
    """获取所有获奖图书（支持筛选）"""
    try:
        from app.models.schemas import AwardBook

        # 获取筛选参数并验证
        award_id = request.args.get('award_id', type=int)
        year = request.args.get('year', type=int)
        if year and (year < 1900 or year > 2100):
            return APIResponse.error('无效的年份', 400)

        category = request.args.get('category')
        keyword = request.args.get('keyword')

        # 验证并规范化分页参数
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        page, limit = validate_pagination_params(page, limit)

        # 构建查询
        query = AwardBook.query

        if award_id:
            query = query.filter_by(award_id=award_id)
        if year:
            query = query.filter_by(year=year)
        if category:
            query = query.filter_by(category=category)
        if keyword:
            # 防止 SQL 注入
            escaped_keyword = keyword.replace('%', r'\%').replace('_', r'\_')
            query = query.filter(
                db.or_(
                    AwardBook.title.ilike(f'%{escaped_keyword}%'),
                    AwardBook.author.ilike(f'%{escaped_keyword}%')
                )
            )

        # 分页
        total = query.count()
        books = query.order_by(AwardBook.year.desc()).\
            offset((page - 1) * limit).limit(limit).all()

        return APIResponse.success(data={
            'books': [book.to_dict() for book in books],
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        logger.error(f"获取图书列表错误: {e}", exc_info=True)
        return APIResponse.error('获取图书列表失败', 500)


@api_bp.route('/award-books/<int:book_id>')
def get_award_book_detail(book_id: int):
    """获取图书详情"""
    try:
        from app.models.schemas import AwardBook

        book = AwardBook.query.get(book_id)
        if not book:
            return APIResponse.error('图书不存在', 404)

        return APIResponse.success(data={
            'book': book.to_dict(include_zh=True)
        })

    except Exception as e:
        logger.error(f"获取图书详情错误: {e}", exc_info=True)
        return APIResponse.error('获取图书详情失败', 500)


@api_bp.route('/award-books/search')
def search_award_books():
    """搜索获奖图书"""
    try:
        from app.models.schemas import AwardBook

        keyword = request.args.get('keyword', '').strip()
        if not keyword:
            return APIResponse.error('搜索关键词不能为空', 400)

        if len(keyword) > 100:
            return APIResponse.error('关键词长度不能超过100个字符', 400)

        # 防止 SQL 注入
        escaped_keyword = keyword.replace('%', r'\%').replace('_', r'\_')

        # 验证并规范化分页参数
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        page, limit = validate_pagination_params(page, limit)

        query = AwardBook.query.filter(
            db.or_(
                AwardBook.title.ilike(f'%{escaped_keyword}%'),
                AwardBook.author.ilike(f'%{escaped_keyword}%'),
                AwardBook.title_zh.ilike(f'%{escaped_keyword}%')
            )
        )

        total = query.count()
        books = query.order_by(AwardBook.year.desc()).\
            offset((page - 1) * limit).limit(limit).all()

        return APIResponse.success(data={
            'keyword': keyword,
            'books': [book.to_dict() for book in books],
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        logger.error(f"搜索图书错误: {e}", exc_info=True)
        return APIResponse.error('搜索失败', 500)


# ==================== AI 推荐 API ====================

@api_bp.route('/recommendations')
def get_recommendations():
    """获取个性化推荐"""
    try:
        from app.services.recommendation_service import RecommendationService

        # 获取参数
        session_id = get_session_id()
        limit = request.args.get('limit', 10, type=int)
        strategy = request.args.get('strategy', 'personalized')

        # 限制参数范围
        limit = min(max(1, limit), 50)
        if strategy not in ['personalized', 'similarity', 'smart', 'popular']:
            strategy = 'personalized'

        # 创建推荐服务
        categories = current_app.config.get('CATEGORIES', {})
        recommendation_service = RecommendationService(categories)

        # 根据策略获取推荐
        if strategy == 'personalized':
            result = recommendation_service.get_personalized_recommendations(
                session_id, limit
            )
        elif strategy == 'similarity':
            # 获取相似推荐参数
            book_id = request.args.get('book_id', type=int)
            isbn = request.args.get('isbn')
            award_id = request.args.get('award_id', type=int)
            category = request.args.get('category')

            result = recommendation_service.get_similarity_recommendations(
                book_id=book_id,
                isbn=isbn,
                award_id=award_id,
                category=category,
                limit=limit
            )
        elif strategy == 'smart':
            result = recommendation_service.get_smart_recommendations(
                session_id, limit
            )
        else:  # popular
            result = recommendation_service._get_popular_recommendations(limit)

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"获取推荐失败: {e}", exc_info=True)
        return APIResponse.error('获取推荐失败', 500)


@api_bp.route('/recommendations/similarity')
def get_similarity_recommendations():
    """获取相似图书推荐"""
    try:
        from app.services.recommendation_service import RecommendationService

        # 获取参数
        book_id = request.args.get('book_id', type=int)
        isbn = request.args.get('isbn')
        award_id = request.args.get('award_id', type=int)
        category = request.args.get('category')
        limit = request.args.get('limit', 10, type=int)

        # 验证至少有一个查询条件
        if not any([book_id, isbn, award_id, category]):
            return APIResponse.error('请提供 book_id, isbn, award_id 或 category 参数之一', 400)

        # 限制参数范围
        limit = min(max(1, limit), 50)

        # 创建推荐服务
        categories = current_app.config.get('CATEGORIES', {})
        recommendation_service = RecommendationService(categories)

        result = recommendation_service.get_similarity_recommendations(
            book_id=book_id,
            isbn=isbn,
            award_id=award_id,
            category=category,
            limit=limit
        )

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"获取相似推荐失败: {e}", exc_info=True)
        return APIResponse.error('获取相似推荐失败', 500)


# ==================== 智能搜索 API ====================

@api_bp.route('/search/suggestions')
def get_search_suggestions():
    """获取搜索建议（自动补全）"""
    try:
        from app.services.smart_search_service import SmartSearchService

        # 获取参数
        prefix = request.args.get('prefix', '').strip()
        limit = request.args.get('limit', 10, type=int)

        if not prefix:
            return APIResponse.success(data={
                'suggestions': [],
                'prefix': prefix
            })

        # 限制参数范围
        limit = min(max(1, limit), 20)

        # 创建搜索服务
        categories = current_app.config.get('CATEGORIES', {})
        search_service = SmartSearchService(categories)

        result = search_service.get_suggestions(prefix, limit)

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"获取搜索建议失败: {e}", exc_info=True)
        return APIResponse.error('获取搜索建议失败', 500)


@api_bp.route('/search/smart')
def smart_search():
    """智能搜索（支持多种筛选条件）"""
    try:
        from app.services.smart_search_service import SmartSearchService

        # 获取搜索参数
        keyword = request.args.get('keyword', '').strip()
        search_type = request.args.get('type', 'all')
        year = request.args.get('year', type=int)
        award_id = request.args.get('award_id', type=int)

        # 验证搜索类型
        valid_types = ['all', 'title', 'author', 'publisher']
        if search_type not in valid_types:
            search_type = 'all'

        # 验证并规范化分页参数
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        page, limit = validate_pagination_params(page, limit)

        offset = (page - 1) * limit

        # 创建搜索服务
        categories = current_app.config.get('CATEGORIES', {})
        search_service = SmartSearchService(categories)

        result = search_service.search(
            keyword=keyword,
            search_type=search_type,
            year=year,
            award_id=award_id,
            limit=limit,
            offset=offset
        )

        # 保存搜索历史
        if keyword:
            session_id = get_session_id()
            search_service.save_search_history(
                session_id, keyword, result.get('total', 0)
            )

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"智能搜索失败: {e}", exc_info=True)
        return APIResponse.error('搜索失败', 500)


@api_bp.route('/search/popular')
def get_popular_searches():
    """获取热门搜索词"""
    try:
        from app.services.smart_search_service import SmartSearchService

        limit = request.args.get('limit', 10, type=int)
        limit = min(max(1, limit), 50)

        categories = current_app.config.get('CATEGORIES', {})
        search_service = SmartSearchService(categories)

        result = search_service.get_popular_searches(limit)

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"获取热门搜索失败: {e}", exc_info=True)
        return APIResponse.error('获取热门搜索失败', 500)
