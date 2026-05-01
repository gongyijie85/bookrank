import re
import logging
from pathlib import Path
from typing import Optional, Tuple

from flask import Blueprint, render_template, send_from_directory, abort, request, current_app
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload

from ..utils import clean_translation_text
from ..utils.service_helpers import get_book_service
from ..data.publishers import PUBLISHERS_DATA

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


def _get_books_for_category(category: str) -> Tuple[list, Optional[str]]:
    """获取指定分类的书籍数据（统一入口）"""
    categories = current_app.config['CATEGORIES']
    default_category = list(categories.keys())[0]

    if category not in categories:
        category = default_category

    books_data = []
    update_time = None

    try:
        book_service = get_book_service()
        if book_service:
            books = book_service.get_books_by_category(category)
            if books:
                books_data = [book.to_dict() for book in books]
    except Exception as e:
        logger.warning(f"Failed to get cached books: {e}")

    try:
        if book_service:
            update_time = book_service._cache.get_cache_time(f"books_{category}")
    except Exception:
        update_time = None

    return books_data, update_time


def _filter_books_by_search(books_data: list, search_query: str) -> list:
    """根据搜索词过滤书籍列表"""
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
        def rank_change_key(b):
            try:
                last_week = int(b.get('rank_last_week', '0') or '0')
                current = b.get('rank', 999)
                return abs(last_week - current) if last_week > 0 else 0
            except (ValueError, TypeError):
                return 0
        return sorted(books_data, key=rank_change_key, reverse=True)

    elif sort_by == 'weeks_desc':
        return sorted(books_data, key=lambda b: b.get('weeks_on_list', 0), reverse=True)

    elif sort_by == 'weeks_asc':
        return sorted(books_data, key=lambda b: b.get('weeks_on_list', 999))

    return books_data


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单（支持多维度筛选和排序）"""
    categories = current_app.config['CATEGORIES']
    default_category = list(categories.keys())[0]

    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category

    search_query = request.args.get('search', '').strip()[:100]
    view_mode = request.args.get('view', 'list')
    if view_mode not in ['grid', 'list']:
        view_mode = 'list'

    publisher_filter = request.args.get('publisher', '').strip()
    weeks_filter = request.args.get('weeks', '')
    sort_by = request.args.get('sort', '')

    books_data, update_time = _get_books_for_category(category)

    if search_query:
        books_data = _filter_books_by_search(books_data, search_query)
    if publisher_filter:
        books_data = _filter_books_by_publisher(books_data, publisher_filter)
    if weeks_filter:
        books_data = _filter_books_by_weeks(books_data, weeks_filter)

    if sort_by:
        books_data = _sort_books(books_data, sort_by)

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
    """提供缓存的图片文件（安全验证文件名格式，防止路径遍历攻击）"""
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

        if search_query:
            search_lower = search_query.lower()
            books = [
                b for b in books
                if search_lower in b.title.lower() or search_lower in b.author.lower()
            ]

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
    selected_publisher = request.args.get('publisher', '', type=int)
    selected_category = request.args.get('category', '')
    selected_days = min(max(1, request.args.get('days', 30, type=int)), 365)
    search_query = request.args.get('search', '').strip()[:100]
    page = min(max(1, request.args.get('page', 1, type=int)), 10000)
    per_page = 20
    view_mode = request.args.get('view', 'grid')
    if view_mode not in ['grid', 'list']:
        view_mode = 'grid'

    from ..services.new_book_service import NewBookService
    service = NewBookService()

    try:
        publishers = service.get_publishers(active_only=True)
    except Exception as e:
        logger.warning(f"获取出版社列表失败: {e}")
        publishers = []

    publisher_book_counts = {}
    try:
        from sqlalchemy import func
        from ..models.new_book import NewBook
        counts_result = db.session.query(
            NewBook.publisher_id, func.count(NewBook.id)
        ).group_by(NewBook.publisher_id).all()
        publisher_book_counts = dict(counts_result)
    except Exception:
        publisher_book_counts = {}

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
    """出版社导航页面"""
    total_publishers = sum(len(cat["publishers"]) for cat in PUBLISHERS_DATA)

    return render_template('publishers.html',
                          publishers_data=PUBLISHERS_DATA,
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

    book = db.session.get(NewBook, book_id)

    if not book:
        return render_template('error.html',
                           message="书籍不存在",
                           back_url=request.referrer or '/new-books')

    if not book.title_zh or not book.description_zh:
        def translate_book_async():
            try:
                translation_service = current_app.extensions.get('translation_service')
                if translation_service:
                    with current_app.app_context():
                        fresh_book = db.session.get(NewBook, book_id)
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

        submit_background_task(translate_book_async)

    return render_template('new_book_detail.html',
                          book=book,
                          back_url=request.referrer or '/new-books')


@main_bp.route('/award-book/<int:book_id>')
def award_book_detail(book_id):
    """获奖图书详情页"""
    from ..models.schemas import AwardBook

    book = db.session.get(AwardBook, book_id)

    if book:
        return render_template('award_book_detail.html',
                              book=book,
                              back_url=request.referrer or '/awards')
    else:
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

    books_data, _ = _get_books_for_category(category)

    if book_index < 0 or book_index >= len(books_data):
        return render_template('error.html',
                           message="书籍不存在",
                           back_url=request.referrer or '/')

    book = books_data[book_index]

    isbn = book.get('isbn13') or book.get('isbn10')
    if isbn:
        _fetch_google_books_details(book, isbn)
        _merge_or_translate_book(book, isbn)

    return render_template('book_detail.html',
                          book=book,
                          book_index=book_index,
                          category=category,
                          back_url=request.referrer or '/?category=' + category)


def get_google_books_client():
    book_service = get_book_service()
    if book_service and hasattr(book_service, '_google_client'):
        return book_service._google_client
    return None


def _fetch_google_books_details(book: dict, isbn: str) -> None:
    """从 Google Books API 获取详细信息并更新 book 字典（带缓存）"""
    cache_key = f"google_books_detail:{isbn}"
    cache_service = None

    try:
        book_service = get_book_service()
        if book_service and hasattr(book_service, '_cache'):
            cache_service = book_service._cache
    except Exception:
        pass

    if cache_service:
        try:
            cached = cache_service.get(cache_key)
            if cached:
                _update_book_from_google_books(book, cached)
                return
        except Exception:
            pass

    google_client = get_google_books_client()
    if not google_client:
        return

    try:
        details = google_client.fetch_book_details(isbn)
        if not details:
            return

        _update_book_from_google_books(book, details)

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

    submit_background_task(_do_translate)


def _update_book_from_google_books(book: dict, details: dict) -> None:
    """使用 Google Books 数据更新 book 字典，并异步翻译中文"""
    if details.get('details') and details['details'] != 'No detailed description available.':
        book['details'] = details['details']
        _translate_field_async(book, 'details', 'details_zh')

    if details.get('page_count') and details['page_count'] != 'Unknown':
        book['page_count'] = str(details['page_count'])

    if details.get('publication_dt') and details['publication_dt'] != 'Unknown':
        book['publication_dt'] = details['publication_dt']

    if details.get('language') and details['language'] != 'Unknown':
        book['language'] = details['language']

    if details.get('publisher') and details['publisher'] not in ('Unknown', 'Unknown Publisher'):
        current_publisher = book.get('publisher', '')
        if not current_publisher or current_publisher in ('Unknown', 'Unknown Publisher'):
            book['publisher'] = details['publisher']

    if details.get('cover_url') and not book.get('cover'):
        book['cover'] = details['cover_url']

    if details.get('isbn_13') and not book.get('isbn13'):
        book['isbn13'] = details['isbn_13']
    if details.get('isbn_10') and not book.get('isbn10'):
        book['isbn10'] = details['isbn_10']

    if book.get('description') and not book.get('description_zh'):
        _translate_field_async(book, 'description', 'description_zh')


def _merge_or_translate_book(book: dict, isbn: str) -> None:
    """从数据库合并中文翻译，未翻译的启动后台线程异步翻译"""
    try:
        from ..models.schemas import BookMetadata, db

        meta = db.session.get(BookMetadata, isbn)
        if meta:
            if meta.description_zh and not book.get('description_zh'):
                book['description_zh'] = clean_translation_text(meta.description_zh, 'description')
            if meta.details_zh and not book.get('details_zh'):
                book['details_zh'] = clean_translation_text(meta.details_zh, 'details')
            if meta.title_zh and not book.get('title_zh'):
                book['title_zh'] = clean_translation_text(meta.title_zh, 'title')

            if meta.title_zh and meta.description_zh and meta.details_zh:
                return

        needs_title = bool(book.get('title') and not book.get('title_zh'))
        needs_desc = bool(book.get('description') and book.get('description') != 'No summary available.' and not book.get('description_zh'))
        needs_details = bool(book.get('details') and book.get('details') != 'No detailed description available.' and not book.get('details_zh'))

        if not needs_title and not needs_desc and not needs_details:
            return

        translation_service = current_app.extensions.get('translation_service')
        if not translation_service:
            return

        def _translate_async():
            try:
                app = current_app._get_current_object()
            except RuntimeError:
                return

            with app.app_context():
                try:
                    meta_obj = db.session.get(BookMetadata, isbn)
                    if not meta_obj:
                        meta_obj = BookMetadata(
                            isbn=isbn,
                            title=book.get('title', ''),
                            author=book.get('author', '')
                        )
                        db.session.add(meta_obj)

                    if needs_title:
                        try:
                            t = translation_service.translate(book.get('title', ''), 'en', 'zh', field_type='title')
                            if t:
                                meta_obj.title_zh = t
                        except Exception as e:
                            logger.warning(f"异步书名翻译失败: {e}")

                    if needs_desc:
                        try:
                            t = translation_service.translate(book.get('description', ''), 'en', 'zh', field_type='description')
                            if t:
                                meta_obj.description_zh = t
                        except Exception as e:
                            logger.warning(f"异步简介翻译失败: {e}")

                    if needs_details:
                        try:
                            t = translation_service.translate(book.get('details', ''), 'en', 'zh', field_type='details')
                            if t:
                                meta_obj.details_zh = t
                        except Exception as e:
                            logger.warning(f"异步详情翻译失败: {e}")

                    from datetime import datetime, timezone
                    meta_obj.translated_at = datetime.now(timezone.utc)
                    db.session.commit()
                    logger.info(f"异步翻译完成: {isbn}")
                except Exception as e:
                    logger.warning(f"异步翻译失败 {isbn}: {e}")
                    try:
                        db.session.rollback()
                    except Exception:
                        pass

        submit_background_task(_translate_async)

    except Exception as e:
        logger.warning(f"合并图书翻译失败 {isbn}: {e}")


@main_bp.route('/api/book-details')
def book_details_api():
    """获取书籍详细信息 API"""
    try:
        book_index = request.args.get('book_index', type=int)
        isbn = request.args.get('isbn')
        category = request.args.get('category')

        if book_index is None or not isbn:
            return {'success': False, 'error': 'Missing parameters'}

        books_data, _ = _get_books_for_category(category or '')

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
        book_service = get_book_service()
        if book_service:
            books = book_service.get_books_by_category(category)
            if books:
                books_data = [book.to_dict() for book in books]
                update_time = book_service._cache.get_cache_time(f"books_{category}")
    except Exception as e:
        logger.warning(f"Failed to get cached books: {e}")

    return jsonify({
        'success': True,
        'books': books_data,
        'category': category,
        'update_time': update_time
    })


@main_bp.route('/reports/weekly')
def weekly_reports():
    """周报列表页"""
    from ..services.weekly_report_service import WeeklyReportService

    book_service = get_book_service()
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
    from ..services.weekly_report_service import WeeklyReportService
    from ..models.schemas import ReportView, UserBehavior
    from ..models.database import db

    book_service = get_book_service()
    if not book_service:
        return render_template('error.html', message="服务不可用", back_url='/reports/weekly')

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
    from flask import send_file
    from ..services.weekly_report_service import WeeklyReportService
    from ..services.export_service import ExportService
    from ..models.schemas import UserBehavior
    from ..models.database import db

    book_service = get_book_service()
    if not book_service:
        return render_template('error.html', message="服务不可用", back_url='/reports/weekly')

    is_valid, error_msg, report_date = _validate_date(date)
    if not is_valid:
        return render_template('error.html', message=error_msg, back_url='/reports/weekly')

    report_service = WeeklyReportService(book_service)
    export_service = ExportService()

    try:
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_template('error.html', message="周报不存在", back_url='/reports/weekly')

        format_type = request.args.get('format', 'pdf').lower()
        if format_type not in ['pdf', 'excel']:
            return render_template('error.html', message="不支持的导出格式", back_url=f'/reports/weekly/{date}')

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

        config = export_config[format_type]
        buffer = config['export_method'](report)
        if not buffer:
            return render_template('error.html', message=config['error_message'], back_url=f'/reports/weekly/{date}')

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

        return send_file(buffer, as_attachment=True, download_name=config['filename'], mimetype=config['mimetype'])

    except Exception as e:
        current_app.logger.error(f"导出周报时出错: {str(e)}")
        return render_template('error.html', message="导出失败", back_url=f'/reports/weekly/{date}')
