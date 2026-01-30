import csv
import logging
import re
from io import StringIO
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, request, make_response, abort
from werkzeug.utils import secure_filename

from ..models.schemas import UserPreference, UserCategory, UserViewedBook, SearchHistory
from ..models.database import db
from ..utils.exceptions import APIRateLimitException, APIException, ValidationException
from ..services import BookService
from ..services.multi_translation_service import MultiTranslationService
from ..services.translation_service import translate_book_info

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/health')
def health_check():
    """健康检查端点"""
    return APIResponse.success(data={
        'status': 'healthy',
        'service': 'book-rank-api',
        'version': '2.0.0'
    })


def get_session_id() -> str:
    """获取或生成会话ID"""
    return request.args.get('session_id') or request.remote_addr or 'anonymous'


def validate_category(category: str) -> bool:
    """验证分类ID是否有效"""
    from flask import current_app
    categories = current_app.config.get('CATEGORIES', {})
    return category in categories or category == 'all'


class APIResponse:
    """统一API响应格式"""
    
    @staticmethod
    def success(data=None, message="Success", status_code=200):
        """成功响应"""
        response = {
            'success': True,
            'data': data,
            'message': message
        }
        return jsonify(response), status_code
    
    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        """错误响应"""
        response = {
            'success': False,
            'message': message
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


@api_bp.route('/books/<category>')
def get_books(category: str):
    """获取图书列表"""
    try:
        # 验证分类
        if not validate_category(category):
            return APIResponse.error('Invalid category', 400)
        
        session_id = get_session_id()
        book_service: BookService = api_bp.book_service
        
        if category == 'all':
            # 获取所有分类
            from flask import current_app
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
            
            from flask import current_app
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
        return APIResponse.error(str(e), e.status_code)
    except Exception as e:
        logger.error(f"Unexpected error in get_books: {e}", exc_info=True)
        return APIResponse.error('Internal server error', 500)


@api_bp.route('/search')
def search_books():
    """搜索图书"""
    try:
        keyword = request.args.get('keyword', '').strip()
        
        if not keyword:
            return APIResponse.error('Search keyword is required', 400)
        
        if len(keyword) < 2:
            return APIResponse.error('Keyword must be at least 2 characters', 400)
        
        # 验证关键词（防止XSS）
        if not re.match(r'^[\w\s\-\u4e00-\u9fff]+$', keyword):
            return APIResponse.error('Invalid keyword format', 400)
        
        session_id = get_session_id()
        book_service: BookService = api_bp.book_service
        
        # 执行搜索
        results = book_service.search_books(keyword)
        
        # 保存搜索历史
        save_search_history(session_id, keyword, len(results))
        
        # 保存浏览记录
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
            data = request.get_json() or {}
            
            # 获取或创建用户偏好
            preference = UserPreference.query.get(session_id)
            if not preference:
                preference = UserPreference(session_id=session_id)
                db.session.add(preference)
            
            # 更新视图模式
            view_mode = data.get('view_mode')
            if view_mode in ['grid', 'list']:
                preference.view_mode = view_mode
            
            # 更新分类偏好
            preferred_categories = data.get('preferred_categories')
            if preferred_categories and isinstance(preferred_categories, list):
                save_user_categories(session_id, preferred_categories)
            
            # 更新浏览记录
            last_viewed_isbns = data.get('last_viewed_isbns')
            if last_viewed_isbns and isinstance(last_viewed_isbns, list):
                save_viewed_books(session_id, last_viewed_isbns)
            
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
            from flask import current_app
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


# ==================== 翻译相关API ====================

@api_bp.route('/translate', methods=['POST'])
def translate_text():
    """翻译文本"""
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error('请求数据不能为空', 400)
        
        text = data.get('text', '').strip()
        source_lang = data.get('source_lang', 'en')
        target_lang = data.get('target_lang', 'zh')
        
        if not text:
            return APIResponse.error('翻译文本不能为空', 400)
        
        # 限制文本长度
        if len(text) > 2000:
            return APIResponse.error('文本长度超过限制（最大2000字符）', 400)
        
        # 执行翻译
        service = MyMemoryTranslationService()
        translated = service.translate(text, source_lang, target_lang)
        
        if translated:
            return APIResponse.success(data={
                'original': text,
                'translated': translated,
                'source_lang': source_lang,
                'target_lang': target_lang
            })
        else:
            return APIResponse.error('翻译失败，请稍后重试', 500)
            
    except Exception as e:
        logger.error(f"翻译错误: {e}", exc_info=True)
        return APIResponse.error('翻译服务暂时不可用', 500)


@api_bp.route('/translate/book/<isbn>', methods=['POST'])
def translate_book(isbn: str):
    """翻译单本图书 - 优先从数据库获取已翻译内容"""
    try:
        data = request.get_json() or {}
        target_lang = data.get('target_lang', 'zh')
        
        # 获取图书数据
        book_service: BookService = api_bp.book_service
        
        # 搜索图书
        from flask import current_app
        books = []
        for cat_id in current_app.config['CATEGORIES'].keys():
            cat_books = book_service.get_books_by_category(cat_id)
            for book in cat_books:
                if book.isbn13 == isbn or book.isbn10 == isbn:
                    books.append(book)
                    break
        
        if not books:
            return APIResponse.error('图书未找到', 404)
        
        book = books[0]
        book_data = book.to_dict()
        
        # 优先使用数据库中的翻译
        if book.description_zh and book.details_zh:
            # 数据库已有翻译，直接返回
            book_data['description_zh'] = book.description_zh
            book_data['details_zh'] = book.details_zh
            logger.info(f"从数据库获取翻译: {isbn}")
        else:
            # 数据库没有翻译，调用翻译服务
            logger.info(f"实时翻译图书: {isbn}")
            translated_data = translate_book_info(book_data, target_lang)
            book_data.update(translated_data)
            
            # 保存翻译到数据库
            if book_data.get('description_zh') or book_data.get('details_zh'):
                book_service.save_book_translation(
                    isbn,
                    description_zh=book_data.get('description_zh'),
                    details_zh=book_data.get('details_zh')
                )
        
        return APIResponse.success(data={
            'book': book_data,
            'translated_fields': ['description', 'details']
        })
        
    except Exception as e:
        logger.error(f"翻译图书错误: {e}", exc_info=True)
        return APIResponse.error('翻译失败', 500)


@api_bp.route('/translate/cache/stats')
def get_translation_cache_stats():
    """获取翻译服务状态"""
    try:
        # 返回多翻译服务状态
        return APIResponse.success(data={
            'services': [
                {'name': 'MyMemory API', 'type': 'primary', 'status': 'active'},
                {'name': 'Baidu Translation', 'type': 'backup', 'status': 'active'}
            ],
            'strategy': 'failover',
            'description': '当主API限流时自动切换到备用API'
        })
        
    except Exception as e:
        logger.error(f"获取缓存统计错误: {e}", exc_info=True)
        return APIResponse.error('获取统计失败', 500)


@api_bp.route('/translate/cache/clear', methods=['POST'])
def clear_translation_cache():
    """清理翻译缓存"""
    try:
        data = request.get_json() or {}
        days = data.get('days', 30)
       # 清理过期缓存
        service = MyMemoryTranslationService()
        deleted = service.clear_cache(days)
        
        return APIResponse.success(data={
            'deleted_entries': deleted,
            'message': f'已清理 {deleted} 条过期缓存'
        })
        
    except Exception as e:
        logger.error(f"清理缓存错误: {e}", exc_info=True)
        return APIResponse.error('清理缓存失败', 500)
