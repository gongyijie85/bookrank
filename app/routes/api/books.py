import csv
import logging
import re
from datetime import datetime
from io import StringIO
from urllib.parse import quote

from flask import current_app, make_response, request

from ...services.user_service import UserService
from ...utils.api_helpers import (
    APIResponse,
    api_rate_limit,
    clean_translation_text,
    validate_isbn,
)
from ...utils.service_helpers import get_book_service, get_translation_service
from . import api_bp, get_session_id, validate_category

logger = logging.getLogger(__name__)

_user_service = UserService()


@api_bp.route('/books/<category>')
@api_rate_limit(max_requests=60, window=60)
def get_books(category: str):
    """获取图书列表"""
    try:
        if not category or not isinstance(category, str):
            return APIResponse.error('Invalid category parameter', 400)

        if not validate_category(category):
            return APIResponse.error(
                f'Invalid category. Available categories: {list(current_app.config["CATEGORIES"].keys())} or "all"', 400
            )

        session_id = get_session_id()
        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('Service unavailable', 503)

        if category == 'all':
            all_books = {}
            for cat_id in current_app.config['CATEGORIES']:
                all_books[cat_id] = [book.to_dict() for book in book_service.get_books_by_category(cat_id)]
            _user_service.save_user_categories(session_id, list(current_app.config['CATEGORIES'].keys()))
            return APIResponse.success(
                data={
                    'books': all_books,
                    'categories': current_app.config['CATEGORIES'],
                    'latest_update': book_service.get_latest_cache_time(),
                }
            )
        else:
            books = book_service.get_books_by_category(category)
            _user_service.save_user_categories(session_id, [category])
            return APIResponse.success(
                data={
                    'books': [book.to_dict() for book in books],
                    'category_name': current_app.config['CATEGORIES'].get(category, category),
                    'latest_update': book_service.get_latest_cache_time(),
                }
            )

    except Exception as e:
        logger.error(f'Unexpected error in get_books: {e}', exc_info=True)
        return APIResponse.error('Internal server error', 500)


@api_bp.route('/search')
@api_rate_limit(max_requests=30, window=60)
def search_books():
    """搜索图书"""
    try:
        keyword = request.args.get('keyword', '').strip()

        if not keyword:
            return APIResponse.error('Search keyword is required', 400)
        if len(keyword) < 2:
            return APIResponse.error('Keyword must be at least 2 characters', 400)
        if len(keyword) > 100:
            return APIResponse.error('Keyword must be at most 100 characters', 400)
        if not re.match(r'^[\w\s\-\u4e00-\u9fff]+$', keyword):
            return APIResponse.error('Invalid keyword format', 400)

        session_id = get_session_id()
        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('Service unavailable', 503)

        results = book_service.search_books(keyword)[:50]

        _user_service.save_search_history(session_id, keyword, len(results))

        if results:
            _user_service.save_viewed_books(session_id, [book.id for book in results[:5]])

        return APIResponse.success(
            data={
                'books': [book.to_dict() for book in results],
                'count': len(results),
                'latest_update': book_service.get_latest_cache_time(),
            }
        )

    except Exception as e:
        logger.error(f'Search error: {e}', exc_info=True)
        return APIResponse.error('Search failed', 500)


@api_bp.route('/search/history')
def get_search_history():
    """获取搜索历史"""
    try:
        session_id = get_session_id()
        limit = min(request.args.get('limit', 5, type=int), 20)

        history = _user_service.get_search_history(session_id, limit)

        return APIResponse.success(data={'history': history})

    except Exception as e:
        logger.error(f'Get search history error: {e}', exc_info=True)
        return APIResponse.error('Failed to get search history', 500)


@api_bp.route('/user/preferences', methods=['GET', 'POST'])
def user_preferences():
    """获取或更新用户偏好（通过 UserService 层操作数据库）"""
    try:
        session_id = get_session_id()

        if request.method == 'POST':
            if not request.is_json:
                return APIResponse.error('Content-Type must be application/json', 400)

            data = request.get_json() or {}

            # 通过 Service 层更新 view_mode
            _user_service.update_preferences(session_id, data)

            preferred_categories = data.get('preferred_categories')
            if preferred_categories and isinstance(preferred_categories, list):
                valid_categories = list(current_app.config.get('CATEGORIES', {}).keys())
                valid_prefs = [c for c in preferred_categories if c in valid_categories]
                if valid_prefs:
                    _user_service.save_user_categories(session_id, valid_prefs)

            last_viewed_isbns = data.get('last_viewed_isbns')
            if last_viewed_isbns and isinstance(last_viewed_isbns, list):
                valid_isbns = [isbn for isbn in last_viewed_isbns if validate_isbn(isbn)]
                if valid_isbns:
                    _user_service.save_viewed_books(session_id, valid_isbns)

            return APIResponse.success(message='Preferences saved')

        else:
            preferences = _user_service.get_preferences(session_id)
            return APIResponse.success(data={'preferences': preferences})

    except Exception as e:
        logger.error(f'User preferences error: {e}', exc_info=True)
        return APIResponse.error('Failed to process preferences', 500)


@api_bp.route('/export/<category>')
def export_csv(category: str):
    """导出CSV"""
    try:
        if not validate_category(category):
            return APIResponse.error('Invalid category', 400)

        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('Service unavailable', 503)

        if category == 'all':
            all_books = []
            for cat_id in current_app.config['CATEGORIES']:
                all_books.extend(book_service.get_books_by_category(cat_id))
            books = all_books
        else:
            books = book_service.get_books_by_category(category)

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                '分类',
                '书名',
                '作者',
                '出版社',
                '当前排名',
                '上周排名',
                '上榜周数',
                '出版日期',
                '页数',
                '语言',
                'ISBN-13',
                '价格',
            ]
        )

        for book in books:
            writer.writerow(
                [
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
                    book.price,
                ]
            )

        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

        response = make_response(response_data)
        filename = f'纽约时报畅销书_{category}_{datetime.now().strftime("%Y%m%d")}.csv'
        response.headers['Content-Disposition'] = f'attachment; filename={quote(filename)}'
        response.headers['Content-type'] = 'text/csv; charset=utf-8'
        return response

    except Exception as e:
        logger.error(f'Export CSV error: {e}', exc_info=True)
        return APIResponse.error('Export failed', 500)


@api_bp.route('/book-details/<isbn>')
def get_book_details(isbn: str):
    """从 Google Books API 获取图书详细信息（含中文翻译）"""
    try:
        if not validate_isbn(isbn):
            return APIResponse.error('Invalid ISBN format', 400)

        book_service = get_book_service()
        google_client = book_service._google_client if book_service else None

        if not google_client:
            from ...services.api_client import GoogleBooksClient

            google_client = GoogleBooksClient(
                api_key=current_app.config.get('GOOGLE_API_KEY'),
                base_url=current_app.config.get('GOOGLE_BOOKS_API_URL', 'https://www.googleapis.com/books/v1/volumes'),
                timeout=10,
            )

        try:
            book_data = google_client.fetch_book_details(isbn)
        except Exception as e:
            if 'no such table' in str(e):
                return APIResponse.error('Book not found', 404)
            raise

        if not book_data:
            return APIResponse.error('Book not found in Google Books', 404)

        cover_url = book_data.get('cover_url')
        if not cover_url and book_data.get('isbn_13'):
            cover_url = f'https://covers.openlibrary.org/b/isbn/{book_data["isbn_13"]}-L.jpg'

        details_en = book_data.get('details', '')
        details_zh = ''

        # 通过 Service 层获取翻译缓存（不直接访问 db.session）
        try:
            meta = _user_service.get_book_metadata(isbn)
            if meta and meta.details_zh:
                details_zh = clean_translation_text(meta.details_zh, 'details')
        except Exception as e:
            logger.debug(f'查询翻译缓存失败: {e}')

        # 如果没有翻译，尝试同步翻译
        if details_en and not details_zh:
            try:
                translation_service = get_translation_service()
                if translation_service:
                    details_zh = translation_service.translate(details_en, 'en', 'zh', field_type='details')
            except Exception as e:
                logger.debug(f'详情翻译失败: {e}')

        return APIResponse.success(
            data={
                'description': details_zh or details_en,
                'details': details_en,
                'details_zh': details_zh,
                'cover_url': cover_url,
                'page_count': book_data.get('page_count'),
                'language': book_data.get('language'),
                'publisher': book_data.get('publisher'),
                'publication_date': book_data.get('publication_dt'),
                'buy_links': {},
            }
        )

    except Exception as e:
        logger.error(f'Get book details error: {e}', exc_info=True)
        return APIResponse.error('Failed to fetch book details', 500)
