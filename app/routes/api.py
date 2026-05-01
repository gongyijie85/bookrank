import csv
import logging
import re
import secrets
from io import StringIO
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, request, make_response, session, current_app

from ..models.schemas import UserPreference, UserCategory, UserViewedBook, SearchHistory
from ..models.database import db
from ..utils.exceptions import APIRateLimitException, APIException, ValidationException
from ..utils.api_helpers import APIResponse, validate_isbn, validate_pagination, api_rate_limit, csrf_protect, get_csrf_token
from ..utils.service_helpers import get_book_service

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_session_id() -> str:
    """鑾峰彇鎴栫敓鎴愬畨鍏ㄧ殑浼氳瘽ID"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return session['session_id']


def validate_category(category: str) -> bool:
    """楠岃瘉鍒嗙被ID鏄惁鏈夋晥"""
    categories = current_app.config.get('CATEGORIES', {})
    return category in categories or category == 'all'


# ==================== 鍋ュ悍妫€鏌?====================

@api_bp.route('/health')
def health_check():
    """鍋ュ悍妫€鏌ョ鐐?""
    return APIResponse.success(data={
        'status': 'healthy',
        'service': 'book-rank-api'
    })


@api_bp.route('/csrf-token')
def get_csrf_token_endpoint():
    """鑾峰彇CSRF浠ょ墝绔偣"""
    token = get_csrf_token()
    return APIResponse.success(data={'csrf_token': token})


# ==================== 鍥句功API ====================

@api_bp.route('/books/<category>')
@api_rate_limit(max_requests=60, window=60)
def get_books(category: str):
    """鑾峰彇鍥句功鍒楄〃"""
    try:
        if not category or not isinstance(category, str):
            return APIResponse.error('Invalid category parameter', 400)

        if not validate_category(category):
            return APIResponse.error(
                f'Invalid category. Available categories: {list(current_app.config["CATEGORIES"].keys())} or "all"',
                400
            )

        session_id = get_session_id()
        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('Service unavailable', 503)

        if category == 'all':
            all_books = {}
            for cat_id in current_app.config['CATEGORIES'].keys():
                all_books[cat_id] = [
                    book.to_dict()
                    for book in book_service.get_books_by_category(cat_id)
                ]
            save_user_categories(session_id, list(current_app.config['CATEGORIES'].keys()))
            return APIResponse.success(data={
                'books': all_books,
                'categories': current_app.config['CATEGORIES'],
                'latest_update': book_service.get_latest_cache_time()
            })
        else:
            books = book_service.get_books_by_category(category)
            save_user_categories(session_id, [category])
            return APIResponse.success(data={
                'books': [book.to_dict() for book in books],
                'category_name': current_app.config['CATEGORIES'].get(category, category),
                'latest_update': book_service.get_latest_cache_time()
            })

    except APIRateLimitException as e:
        logger.warning(f"Rate limit exceeded: {e}")
        return APIResponse.error(
            f'Rate limit exceeded. Retry after {e.retry_after}s', 429
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
    """鎼滅储鍥句功"""
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

        save_search_history(session_id, keyword, len(results))

        if results:
            save_viewed_books(session_id, [book.id for book in results[:5]])

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
    """鑾峰彇鎼滅储鍘嗗彶"""
    try:
        session_id = get_session_id()
        limit = min(request.args.get('limit', 5, type=int), 20)

        history = SearchHistory.query.filter_by(
            session_id=session_id
        ).order_by(
            SearchHistory.created_at.desc()
        ).limit(limit).all()

        return APIResponse.success(data={'history': [h.to_dict() for h in history]})

    except Exception as e:
        logger.error(f"Get search history error: {e}", exc_info=True)
        return APIResponse.error('Failed to get search history', 500)


@api_bp.route('/user/preferences', methods=['GET', 'POST'])
def user_preferences():
    """鑾峰彇鎴栨洿鏂扮敤鎴峰亸濂?""
    try:
        session_id = get_session_id()

        if request.method == 'POST':
            if not request.is_json:
                return APIResponse.error('Content-Type must be application/json', 400)

            data = request.get_json() or {}

            preference = db.session.get(UserPreference, session_id)
            if not preference:
                preference = UserPreference(session_id=session_id)
                db.session.add(preference)

            view_mode = data.get('view_mode')
            if view_mode in ['grid', 'list']:
                preference.view_mode = view_mode

            preferred_categories = data.get('preferred_categories')
            if preferred_categories and isinstance(preferred_categories, list):
                valid_categories = list(current_app.config.get('CATEGORIES', {}).keys())
                valid_prefs = [c for c in preferred_categories if c in valid_categories]
                if valid_prefs:
                    save_user_categories(session_id, valid_prefs)

            last_viewed_isbns = data.get('last_viewed_isbns')
            if last_viewed_isbns and isinstance(last_viewed_isbns, list):
                valid_isbns = [isbn for isbn in last_viewed_isbns if validate_isbn(isbn)]
                if valid_isbns:
                    save_viewed_books(session_id, valid_isbns)

            db.session.commit()
            return APIResponse.success(message='Preferences saved')

        else:
            preference = db.session.get(UserPreference, session_id)
            if preference:
                return APIResponse.success(data={'preferences': preference.to_dict()})
            return APIResponse.success(data={'preferences': {}})

    except Exception as e:
        logger.error(f"User preferences error: {e}", exc_info=True)
        db.session.rollback()
        return APIResponse.error('Failed to process preferences', 500)


@api_bp.route('/export/<category>')
def export_csv(category: str):
    """瀵煎嚭CSV"""
    try:
        if not validate_category(category):
            return APIResponse.error('Invalid category', 400)

        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('Service unavailable', 503)

        if category == 'all':
            all_books = []
            for cat_id in current_app.config['CATEGORIES'].keys():
                all_books.extend(book_service.get_books_by_category(cat_id))
            books = all_books
        else:
            books = book_service.get_books_by_category(category)

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            '鍒嗙被', '涔﹀悕', '浣滆€?, '鍑虹増绀?, '褰撳墠鎺掑悕',
            '涓婂懆鎺掑悕', '涓婃鍛ㄦ暟', '鍑虹増鏃ユ湡', '椤垫暟',
            '璇█', 'ISBN-13', '浠锋牸'
        ])

        for book in books:
            writer.writerow([
                book.category_name, book.title, book.author, book.publisher,
                book.rank, book.rank_last_week, book.weeks_on_list,
                book.publication_dt, book.page_count, book.language,
                book.isbn13, book.price
            ])

        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

        response = make_response(response_data)
        filename = f'绾界害鏃舵姤鐣呴攢涔{category}_{datetime.now().strftime("%Y%m%d")}.csv'
        response.headers["Content-Disposition"] = f"attachment; filename={quote(filename)}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"
        return response

    except Exception as e:
        logger.error(f"Export CSV error: {e}", exc_info=True)
        return APIResponse.error('Export failed', 500)


def save_user_categories(session_id: str, category_ids: list):
    """淇濆瓨鐢ㄦ埛鍒嗙被鍋忓ソ"""
    try:
        preference = db.session.get(UserPreference, session_id)
        if not preference:
            preference = UserPreference(session_id=session_id)
            db.session.add(preference)

        UserCategory.query.filter_by(session_id=session_id).delete()

        for cat_id in category_ids:
            db.session.add(UserCategory(session_id=session_id, category_id=cat_id))

        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save user categories: {e}")
        db.session.rollback()


def save_viewed_books(session_id: str, isbns: list):
    """淇濆瓨鐢ㄦ埛娴忚璁板綍"""
    try:
        for isbn in isbns:
            db.session.merge(UserViewedBook(session_id=session_id, isbn=isbn))
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save viewed books: {e}")
        db.session.rollback()


def save_search_history(session_id: str, keyword: str, result_count: int):
    """淇濆瓨鎼滅储鍘嗗彶"""
    try:
        db.session.add(SearchHistory(
            session_id=session_id, keyword=keyword, result_count=result_count
        ))
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save search history: {e}")
        db.session.rollback()


@api_bp.route('/book-details/<isbn>')
def get_book_details(isbn: str):
    """浠?Google Books API 鑾峰彇鍥句功璇︾粏淇℃伅锛堝惈涓枃缈昏瘧锛?""
    try:
        if not validate_isbn(isbn):
            return APIResponse.error('Invalid ISBN format', 400)

        book_service = get_book_service()
        google_client = book_service._google_client if book_service else None

        if not google_client:
            from ..services.api_client import GoogleBooksClient
            google_client = GoogleBooksClient(
                api_key=current_app.config.get('GOOGLE_API_KEY'),
                base_url=current_app.config.get('GOOGLE_BOOKS_API_URL', 'https://www.googleapis.com/books/v1/volumes'),
                timeout=10
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
            cover_url = f"https://covers.openlibrary.org/b/isbn/{book_data['isbn_13']}-L.jpg"

        details_en = book_data.get('details', '')
        details_zh = ''

        # 浠庢暟鎹簱鑾峰彇宸叉湁鐨勪腑鏂囩炕璇?
        try:
            from ..models.schemas import BookMetadata
            meta = db.session.get(BookMetadata, isbn)
            if meta and meta.details_zh:
                details_zh = clean_translation_text(meta.details_zh, 'details')
        except Exception as e:
            logger.debug(f"鏌ヨ缈昏瘧缂撳瓨澶辫触: {e}")

        # 濡傛灉娌℃湁缈昏瘧锛屽皾璇曞悓姝ョ炕璇?
        if details_en and not details_zh:
            try:
                translation_service = current_app.extensions.get('translation_service')
                if translation_service:
                    details_zh = translation_service.translate(details_en, 'en', 'zh', field_type='details')
            except Exception as e:
                logger.debug(f"璇︽儏缈昏瘧澶辫触: {e}")

        return APIResponse.success(data={
            'description': details_zh or details_en,
            'details': details_en,
            'details_zh': details_zh,
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


# ==================== 閿欒澶勭悊鍣?====================

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


# ==================== 缈昏瘧鐩稿叧API ====================

@api_bp.route('/translate', methods=['POST'])
@csrf_protect
def translate_text():
    """缈昏瘧鏂囨湰"""
    try:
        if not request.is_json:
            return APIResponse.error('Content-Type must be application/json', 400)

        data = request.get_json() or {}
        text = data.get('text', '').strip()
        source_lang = data.get('source_lang', 'en')
        target_lang = data.get('target_lang', 'zh')
        field_type = data.get('field_type', 'text')

        if not text:
            return APIResponse.error('缂哄皯瑕佺炕璇戠殑鏂囨湰', 400)
        if len(text) > 10000:
            return APIResponse.error('鏂囨湰闀垮害瓒呰繃闄愬埗锛堟渶澶?0000瀛楃锛?, 400)

        from ..services.zhipu_translation_service import get_translation_service

        service = get_translation_service()
        result = service.translate(text, source_lang, target_lang, field_type=field_type)

        if result:
            return APIResponse.success(data={
                'original': text,
                'translated': result,
                'source_lang': source_lang,
                'target_lang': target_lang
            })
        return APIResponse.error('缈昏瘧澶辫触锛岃绋嶅悗閲嶈瘯', 500)

    except Exception as e:
        logger.error(f"缈昏瘧閿欒: {e}", exc_info=True)
        return APIResponse.error('缈昏瘧鏈嶅姟鏆傛椂涓嶅彲鐢?, 503)


@api_bp.route('/translate/book/<isbn>', methods=['POST'])
@csrf_protect
def translate_book(isbn: str):
    """缈昏瘧鍥句功淇℃伅"""
    try:
        if not validate_isbn(isbn):
            return APIResponse.error('鏃犳晥鐨処SBN鏍煎紡', 400)

        from ..services.zhipu_translation_service import get_translation_service

        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('鍥句功鏈嶅姟涓嶅彲鐢?, 503)

        book_data = book_service.get_book_by_isbn(isbn)
        if not book_data:
            return APIResponse.error('鍥句功涓嶅瓨鍦?, 404)

        service = get_translation_service()
        translated_data = service.translate_book_info(book_data)

        return APIResponse.success(data={'book': translated_data})

    except Exception as e:
        logger.error(f"缈昏瘧鍥句功閿欒: {e}", exc_info=True)
        return APIResponse.error('缈昏瘧鏈嶅姟鏆傛椂涓嶅彲鐢?, 503)


@api_bp.route('/translate/cache/stats')
def get_translation_cache_stats():
    """鑾峰彇缈昏瘧缂撳瓨缁熻淇℃伅"""
    try:
        from ..services.zhipu_translation_service import get_translation_service

        service = get_translation_service()
        zhipu_available = service.zhipu.is_available()

        try:
            cache_stats = service.get_cache_stats()
        except Exception as e:
            if 'no such table' in str(e):
                return APIResponse.success(data={
                    'service': 'ZhipuAI GLM-4.7-Flash',
                    'status': 'offline',
                    'model': 'glm-4.7-flash',
                    'description': '浣跨敤鏅鸿氨AI鍏嶈垂妯″瀷杩涜楂樿川閲忕炕璇?,
                    'message': 'Database not initialized'
                })
            raise

        return APIResponse.success(data={
            'service': 'ZhipuAI GLM-4.7-Flash',
            'status': 'online' if zhipu_available else 'offline',
            'model': 'glm-4.7-flash',
            'description': '浣跨敤鏅鸿氨AI鍏嶈垂妯″瀷杩涜楂樿川閲忕炕璇?,
            'cache': cache_stats
        })

    except Exception as e:
        logger.error(f"鑾峰彇缈昏瘧鐘舵€侀敊璇? {e}", exc_info=True)
        return APIResponse.success(data={
            'service': 'ZhipuAI GLM-4.7-Flash',
            'status': 'error',
            'description': str(e)
        })


@api_bp.route('/translate/cache/recent')
def get_translation_cache_recent():
    """鑾峰彇鏈€杩戠殑缈昏瘧缂撳瓨璁板綍"""
    try:
        from ..services.translation_cache_service import get_translation_cache_service

        limit = min(max(1, request.args.get('limit', 20, type=int)), 100)
        source_lang = request.args.get('source_lang')
        target_lang = request.args.get('target_lang')

        cache_service = get_translation_cache_service()
        recent = cache_service.get_recent(limit, source_lang, target_lang)

        return APIResponse.success(data={
            'records': [
                {
                    'id': r.id,
                    'source_text': r.source_text[:100] + '...' if len(r.source_text) > 100 else r.source_text,
                    'translated_text': r.translated_text[:100] + '...' if len(r.translated_text) > 100 else r.translated_text,
                    'source_lang': r.source_lang,
                    'target_lang': r.target_lang,
                    'usage_count': r.usage_count,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'last_used_at': r.last_used_at.isoformat() if r.last_used_at else None
                }
                for r in recent
            ],
            'count': len(recent)
        })

    except Exception as e:
        logger.error(f"鑾峰彇缂撳瓨璁板綍閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇缂撳瓨璁板綍澶辫触', 500)


@api_bp.route('/translate/cache/clear', methods=['POST'])
@csrf_protect
def clear_translation_cache():
    """娓呯悊缈昏瘧缂撳瓨"""
    try:
        from ..services.translation_cache_service import get_translation_cache_service

        data = request.get_json() or {}
        cache_id = data.get('cache_id')
        older_than_days = data.get('older_than_days')
        min_usage = data.get('min_usage')

        cache_service = get_translation_cache_service()

        if older_than_days or min_usage is not None:
            deleted = cache_service.delete(older_than_days=older_than_days, min_usage=min_usage)
            message = f'宸叉竻鐞?{deleted} 鏉＄炕璇戠紦瀛?
        elif cache_id:
            deleted = cache_service.delete(cache_id=cache_id)
            message = f'宸插垹闄ょ紦瀛樿褰?#{cache_id}'
        else:
            deleted = cache_service.clear_all()
            message = f'宸叉竻绌烘墍鏈夌炕璇戠紦瀛橈紙{deleted}鏉★級'

        return APIResponse.success(message=message)

    except Exception as e:
        logger.error(f"娓呯悊缂撳瓨閿欒: {e}", exc_info=True)
        return APIResponse.error('娓呯悊缂撳瓨澶辫触', 500)


# ==================== API缂撳瓨绠＄悊 ====================

@api_bp.route('/cache/stats')
def get_api_cache_stats():
    """鑾峰彇API缂撳瓨缁熻淇℃伅"""
    try:
        from ..services.api_cache_service import get_api_cache_service

        cache_service = get_api_cache_service()
        stats = cache_service.get_stats()

        return APIResponse.success(data=stats)

    except Exception as e:
        logger.error(f"鑾峰彇API缂撳瓨缁熻閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇缁熻澶辫触', 500)


@api_bp.route('/cache/recent')
def get_api_cache_recent():
    """鑾峰彇鏈€杩戠殑API缂撳瓨璁板綍"""
    try:
        from ..services.api_cache_service import get_api_cache_service
        from ..models.schemas import APICache

        limit = min(max(1, request.args.get('limit', 20, type=int)), 100)
        api_source = request.args.get('api_source')

        cache_service = get_api_cache_service()
        query = APICache.query

        if api_source:
            query = query.filter_by(api_source=api_source)

        records = query.order_by(APICache.last_used_at.desc()).limit(limit).all()

        return APIResponse.success(data={
            'records': [
                {
                    'id': r.id,
                    'api_source': r.api_source,
                    'request_key': r.request_key,
                    'status_code': r.status_code,
                    'usage_count': r.usage_count,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'expires_at': r.expires_at.isoformat() if r.expires_at else None
                }
                for r in records
            ],
            'count': len(records)
        })

    except Exception as e:
        logger.error(f"鑾峰彇API缂撳瓨璁板綍閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇缂撳瓨璁板綍澶辫触', 500)


@api_bp.route('/cache/clear', methods=['POST'])
@csrf_protect
def clear_api_cache():
    """娓呯悊API缂撳瓨"""
    try:
        from ..services.api_cache_service import get_api_cache_service

        data = request.get_json() or {}
        older_than_days = data.get('older_than_days')

        cache_service = get_api_cache_service()
        deleted = cache_service.delete(older_than_days=older_than_days)

        return APIResponse.success(message=f'宸叉竻鐞?{deleted} 鏉PI缂撳瓨')

    except Exception as e:
        logger.error(f"娓呯悊API缂撳瓨閿欒: {e}", exc_info=True)
        return APIResponse.error('娓呯悊缂撳瓨澶辫触', 500)


@api_bp.route('/cache/clear-expired', methods=['POST'])
@csrf_protect
def clear_expired_api_cache():
    """娓呯悊杩囨湡API缂撳瓨"""
    try:
        from ..services.api_cache_service import get_api_cache_service

        cache_service = get_api_cache_service()
        deleted = cache_service.clear_expired()

        return APIResponse.success(message=f'宸叉竻鐞?{deleted} 鏉¤繃鏈熺紦瀛?)

    except Exception as e:
        logger.error(f"娓呯悊杩囨湡缂撳瓨閿欒: {e}", exc_info=True)
        return APIResponse.error('娓呯悊缂撳瓨澶辫触', 500)


# ==================== 鍥介檯鍥句功濂栭」API ====================

@api_bp.route('/awards')
def get_awards():
    """鑾峰彇鎵€鏈夊椤瑰垪琛?""
    try:
        from app.models.schemas import Award

        awards = Award.query.all()
        return APIResponse.success(data={'awards': [award.to_dict() for award in awards]})

    except Exception as e:
        logger.error(f"鑾峰彇濂栭」鍒楄〃閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇濂栭」鍒楄〃澶辫触', 500)


@api_bp.route('/awards/<int:award_id>/books')
def get_award_books(award_id: int):
    """鑾峰彇鎸囧畾濂栭」鐨勫浘涔﹀垪琛?""
    try:
        from app.models.schemas import Award, AwardBook

        award = db.session.get(Award, award_id)
        if not award:
            return APIResponse.error('濂栭」涓嶅瓨鍦?, 404)

        year = request.args.get('year', type=int)
        if year and (year < 1900 or year > 2100):
            return APIResponse.error('鏃犳晥鐨勫勾浠?, 400)

        category = request.args.get('category')
        page, limit = validate_pagination(
            request.args.get('page', 1, type=int),
            request.args.get('limit', 20, type=int)
        )

        query = AwardBook.query.filter_by(award_id=award_id)
        if year:
            query = query.filter_by(year=year)
        if category:
            query = query.filter_by(category=category)

        total = query.count()
        books = query.order_by(AwardBook.year.desc(), AwardBook.rank.asc())\
            .offset((page - 1) * limit).limit(limit).all()

        return APIResponse.success(data={
            'award': award.to_dict(),
            'books': [book.to_dict() for book in books],
            'pagination': {
                'page': page, 'limit': limit,
                'total': total, 'pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        logger.error(f"鑾峰彇濂栭」鍥句功閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鍥句功鍒楄〃澶辫触', 500)


@api_bp.route('/award-books')
def get_all_award_books():
    """鑾峰彇鎵€鏈夎幏濂栧浘涔︼紙鏀寔绛涢€夛級"""
    try:
        from app.models.schemas import AwardBook

        award_id = request.args.get('award_id', type=int)
        year = request.args.get('year', type=int)
        if year and (year < 1900 or year > 2100):
            return APIResponse.error('鏃犳晥鐨勫勾浠?, 400)

        category = request.args.get('category')
        keyword = request.args.get('keyword')
        page, limit = validate_pagination(
            request.args.get('page', 1, type=int),
            request.args.get('limit', 20, type=int)
        )

        query = AwardBook.query
        if award_id:
            query = query.filter_by(award_id=award_id)
        if year:
            query = query.filter_by(year=year)
        if category:
            query = query.filter_by(category=category)
        if keyword:
            escaped = keyword.replace('%', r'\%').replace('_', r'\_')
            query = query.filter(db.or_(
                AwardBook.title.ilike(f'%{escaped}%', escape='\\'),
                AwardBook.author.ilike(f'%{escaped}%', escape='\\')
            ))

        total = query.count()
        books = query.order_by(AwardBook.year.desc())\
            .offset((page - 1) * limit).limit(limit).all()

        return APIResponse.success(data={
            'books': [book.to_dict() for book in books],
            'pagination': {
                'page': page, 'limit': limit,
                'total': total, 'pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        logger.error(f"鑾峰彇鍥句功鍒楄〃閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鍥句功鍒楄〃澶辫触', 500)


@api_bp.route('/award-books/<int:book_id>')
def get_award_book_detail(book_id: int):
    """鑾峰彇鍥句功璇︽儏"""
    try:
        from app.models.schemas import AwardBook

        book = db.session.get(AwardBook, book_id)
        if not book:
            return APIResponse.error('鍥句功涓嶅瓨鍦?, 404)

        return APIResponse.success(data={'book': book.to_dict(include_zh=True)})

    except Exception as e:
        logger.error(f"鑾峰彇鍥句功璇︽儏閿欒: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鍥句功璇︽儏澶辫触', 500)


@api_bp.route('/award-books/search')
def search_award_books():
    """鎼滅储鑾峰鍥句功"""
    try:
        from app.models.schemas import AwardBook

        keyword = request.args.get('keyword', '').strip()
        if not keyword:
            return APIResponse.error('鎼滅储鍏抽敭璇嶄笉鑳戒负绌?, 400)
        if len(keyword) > 100:
            return APIResponse.error('鍏抽敭璇嶉暱搴︿笉鑳借秴杩?00涓瓧绗?, 400)

        escaped = keyword.replace('%', r'\%').replace('_', r'\_')
        page, limit = validate_pagination(
            request.args.get('page', 1, type=int),
            request.args.get('limit', 20, type=int)
        )

        query = AwardBook.query.filter(db.or_(
            AwardBook.title.ilike(f'%{escaped}%', escape='\\'),
            AwardBook.author.ilike(f'%{escaped}%', escape='\\'),
            AwardBook.title_zh.ilike(f'%{escaped}%', escape='\\')
        ))

        total = query.count()
        books = query.order_by(AwardBook.year.desc())\
            .offset((page - 1) * limit).limit(limit).all()

        return APIResponse.success(data={
            'keyword': keyword,
            'books': [book.to_dict() for book in books],
            'pagination': {
                'page': page, 'limit': limit,
                'total': total, 'pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        logger.error(f"鎼滅储鍥句功閿欒: {e}", exc_info=True)
        return APIResponse.error('鎼滅储澶辫触', 500)


# ==================== AI 鎺ㄨ崘 API ====================

@api_bp.route('/recommendations')
def get_recommendations():
    """鑾峰彇涓€у寲鎺ㄨ崘"""
    try:
        from app.services.recommendation_service import RecommendationService

        session_id = get_session_id()
        limit = min(max(1, request.args.get('limit', 10, type=int)), 50)
        strategy = request.args.get('strategy', 'personalized')
        if strategy not in ['personalized', 'similarity', 'smart', 'popular']:
            strategy = 'personalized'

        categories = current_app.config.get('CATEGORIES', {})
        recommendation_service = RecommendationService(categories)

        if strategy == 'personalized':
            result = recommendation_service.get_personalized_recommendations(session_id, limit)
        elif strategy == 'similarity':
            result = recommendation_service.get_similarity_recommendations(
                book_id=request.args.get('book_id', type=int),
                isbn=request.args.get('isbn'),
                award_id=request.args.get('award_id', type=int),
                category=request.args.get('category'),
                limit=limit
            )
        elif strategy == 'smart':
            result = recommendation_service.get_smart_recommendations(session_id, limit)
        else:
            result = recommendation_service._get_popular_recommendations(limit)

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"鑾峰彇鎺ㄨ崘澶辫触: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鎺ㄨ崘澶辫触', 500)


@api_bp.route('/recommendations/similarity')
def get_similarity_recommendations():
    """鑾峰彇鐩镐技鍥句功鎺ㄨ崘"""
    try:
        from app.services.recommendation_service import RecommendationService

        book_id = request.args.get('book_id', type=int)
        isbn = request.args.get('isbn')
        award_id = request.args.get('award_id', type=int)
        category = request.args.get('category')
        limit = min(max(1, request.args.get('limit', 10, type=int)), 50)

        if not any([book_id, isbn, award_id, category]):
            return APIResponse.error('璇锋彁渚?book_id, isbn, award_id 鎴?category 鍙傛暟涔嬩竴', 400)

        categories = current_app.config.get('CATEGORIES', {})
        recommendation_service = RecommendationService(categories)

        result = recommendation_service.get_similarity_recommendations(
            book_id=book_id, isbn=isbn, award_id=award_id, category=category, limit=limit
        )

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"鑾峰彇鐩镐技鎺ㄨ崘澶辫触: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鐩镐技鎺ㄨ崘澶辫触', 500)


# ==================== 鏅鸿兘鎼滅储 API ====================

@api_bp.route('/search/suggestions')
def get_search_suggestions():
    """鑾峰彇鎼滅储寤鸿锛堣嚜鍔ㄨˉ鍏級"""
    try:
        from app.services.smart_search_service import SmartSearchService

        prefix = request.args.get('prefix', '').strip()
        limit = min(max(1, request.args.get('limit', 10, type=int)), 20)

        if not prefix:
            return APIResponse.success(data={'suggestions': [], 'prefix': prefix})

        categories = current_app.config.get('CATEGORIES', {})
        search_service = SmartSearchService(categories)
        result = search_service.get_suggestions(prefix, limit)

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"鑾峰彇鎼滅储寤鸿澶辫触: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鎼滅储寤鸿澶辫触', 500)


@api_bp.route('/search/smart')
def smart_search():
    """鏅鸿兘鎼滅储锛堟敮鎸佸绉嶇瓫閫夋潯浠讹級"""
    try:
        from app.services.smart_search_service import SmartSearchService

        keyword = request.args.get('keyword', '').strip()
        search_type = request.args.get('type', 'all')
        year = request.args.get('year', type=int)
        award_id = request.args.get('award_id', type=int)

        valid_types = ['all', 'title', 'author', 'publisher']
        if search_type not in valid_types:
            search_type = 'all'

        page, limit = validate_pagination(
            request.args.get('page', 1, type=int),
            request.args.get('limit', 20, type=int)
        )
        offset = (page - 1) * limit

        categories = current_app.config.get('CATEGORIES', {})
        search_service = SmartSearchService(categories)

        result = search_service.search(
            keyword=keyword, search_type=search_type,
            year=year, award_id=award_id, limit=limit, offset=offset
        )

        if keyword:
            session_id = get_session_id()
            search_service.save_search_history(session_id, keyword, result.get('total', 0))

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"鏅鸿兘鎼滅储澶辫触: {e}", exc_info=True)
        return APIResponse.error('鎼滅储澶辫触', 500)


@api_bp.route('/search/popular')
def get_popular_searches():
    """鑾峰彇鐑棬鎼滅储璇?""
    try:
        from app.services.smart_search_service import SmartSearchService

        limit = min(max(1, request.args.get('limit', 10, type=int)), 50)
        categories = current_app.config.get('CATEGORIES', {})
        search_service = SmartSearchService(categories)
        result = search_service.get_popular_searches(limit)

        return APIResponse.success(data=result)

    except Exception as e:
        logger.error(f"鑾峰彇鐑棬鎼滅储澶辫触: {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鐑棬鎼滅储澶辫触', 500)

