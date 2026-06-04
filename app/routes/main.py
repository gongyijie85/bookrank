import logging
import re
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from ..data.publishers import PUBLISHERS_DATA
from ..services.book_detail_service import fetch_google_books_details, is_valid_isbn, merge_or_translate_book
from ..utils import ExternalAPIError
from ..utils.api_helpers import APIResponse, handle_api_errors, quick_clean_translation
from ..utils.book_filters import filter_books_by_publisher, filter_books_by_search, filter_books_by_weeks, sort_books
from ..utils.date_helpers import parse_report_content, validate_date
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.security import is_safe_redirect_url

PROJECT_ROOT = Path(__file__).parent.parent.parent
from ..utils.service_helpers import (
    get_book_service,
    get_google_books_client,
    get_image_cache_service,
    get_translation_service,
    hash_client_ip,
    submit_background_task,
)

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


def _get_books_for_category(category: str) -> tuple[list, str | None]:
    """获取指定分类的书籍数据（统一入口）"""
    categories = current_app.config['CATEGORIES']
    default_category = next(iter(categories.keys()))
    if category not in categories:
        category = default_category

    book_service = get_book_service()
    if not book_service:
        return [], None

    books_data, update_time = [], None

    try:
        books = book_service.get_books_by_category(category) or []
        books_data = [book.to_dict() for book in books]
    except Exception as e:
        raise ExternalAPIError(
            f"获取分类 '{category}' 数据失败", api_name='book_service', details={'category': category}
        ) from e

    try:
        update_time = book_service.get_cache_time(category)
    except Exception as e:
        log_error(ErrorCategory.CACHE, f'获取缓存时间失败: {e}')
        update_time = None

    return books_data, update_time


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单（支持多维度筛选和排序）"""
    categories = current_app.config['CATEGORIES']
    default_category = next(iter(categories.keys()))

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

    books_data, update_time = [], None
    try:
        books_data, update_time = _get_books_for_category(category)
    except ExternalAPIError as e:
        e.log()
        # 降级：用空列表渲染页面，不崩溃

    if search_query:
        books_data = filter_books_by_search(books_data, search_query)
    if publisher_filter:
        books_data = filter_books_by_publisher(books_data, publisher_filter)
    if weeks_filter:
        books_data = filter_books_by_weeks(books_data, weeks_filter)

    if sort_by:
        books_data = sort_books(books_data, sort_by)

    publishers = sorted(
        set(
            b.get('publisher', '')
            for b in books_data
            if b.get('publisher') and b.get('publisher') not in ('Unknown', 'Unknown Publisher')
        )
    )

    return render_template(
        'index.html',
        categories=categories,
        books=books_data,
        current_category=category,
        search_query=search_query,
        view_mode=view_mode,
        update_time=update_time,
        publishers=publishers,
        publisher_filter=publisher_filter,
        weeks_filter=weeks_filter,
        sort_by=sort_by,
    )


@main_bp.route('/cache/images/<filename>')
def cached_image(filename: str):
    """提供缓存的图片文件（安全验证文件名格式，防止路径遍历攻击）"""
    if not re.match(r'^[a-f0-9]{32}\.jpg$', filename):
        abort(404)

    safe_filename = secure_filename(filename)
    cache_dir = current_app.config.get('IMAGE_CACHE_DIR', Path('cache/images'))

    return send_from_directory(cache_dir, safe_filename)


@main_bp.route('/award-book/<int:book_id>/cover')
def award_book_cover(book_id: int):
    """解析获奖图书封面，缺失时按 ISBN/书名补全并回写。"""
    from ..models.schemas import AwardBook
    from ..services.award_cover_sync_service import AwardCoverSyncService

    book = AwardBook.query.get_or_404(book_id)
    sync_service = AwardCoverSyncService(
        get_google_books_client(),
        image_cache=get_image_cache_service(),
    )

    try:
        cover_url = sync_service.resolve_cover_for_book(book)
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获奖图书封面解析失败 book_id={book_id}: {e}', level='warning')
        cover_url = (book.cover_original_url or '').strip()

    response = redirect(cover_url or url_for('static', filename='default-cover.png'), code=302)
    response.headers['Cache-Control'] = 'public, max-age=3600' if cover_url else 'no-store'
    return response


@main_bp.route('/awards')
def awards():
    """图书奖项榜单页面（通过 Service 层，含服务端分页）"""
    from ..services.award_book_service import AwardBookService

    award_service = AwardBookService()
    params = _parse_awards_params(request.args)
    context = _load_awards_data(award_service, params)
    return render_template('awards.html', **context)


def _parse_awards_params(args) -> dict:
    """从请求参数中提取并校验 awards() 所需的查询条件"""
    selected_award = args.get('award', '')
    selected_year = args.get('year', '')
    search_query = args.get('search', '').strip()[:100]
    view_mode = args.get('view', 'grid')
    if view_mode not in ['grid', 'list']:
        view_mode = 'grid'

    try:
        page = max(1, int(args.get('page', '1')))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(max(10, int(args.get('per_page', '24'))), 100)
    except (ValueError, TypeError):
        per_page = 24

    if selected_year:
        try:
            year_int = int(selected_year)
            if year_int < 1900 or year_int > 2100:
                selected_year = ''
        except (ValueError, TypeError):
            selected_year = ''

    return {
        'selected_award': selected_award,
        'selected_year': selected_year,
        'search_query': search_query,
        'view_mode': view_mode,
        'page': page,
        'per_page': per_page,
    }


def _load_awards_data(award_service, params: dict) -> dict:
    """加载 awards() 渲染所需的所有数据，返回模板上下文 dict（含分页元信息）"""
    awards_list: list = []
    years: list = []
    books_data: list = []
    total_books = 0

    try:
        awards_list = award_service.get_all_awards()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'奖项列表查询失败: {e}', exc_info=True)
        awards_list = []

    try:
        years = award_service.get_distinct_years()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'年份列表查询失败: {e}', level='warning')
        years = []

    try:
        award_id = None
        if params['selected_award']:
            award = award_service.get_award_by_name(params['selected_award'])
            if award:
                award_id = award.id

        year = int(params['selected_year']) if params['selected_year'] else None
        books, total_books = award_service.get_award_books(
            award_id=award_id,
            year=year,
            keyword=params['search_query'] or None,
            include_displayable_only=True,
            page=params['page'],
            limit=params['per_page'],
        )

        for book in books:
            books_data.append(
                {
                    'id': book.id,
                    'title': book.display_title,
                    'title_zh': quick_clean_translation(book.title_zh, 'title'),
                    'description': book.description,
                    'description_zh': quick_clean_translation(book.description_zh, 'description'),
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
                    'buy_links': book.buy_links,
                }
            )

        book_counts = award_service.get_book_counts_by_award(displayable_only=True)
        for award_item in awards_list:
            award_item.book_count = book_counts.get(award_item.id, 0)

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获奖图书数据加载失败: {e}', exc_info=True)
        books_data = []
        total_books = 0

    per_page = params['per_page']
    page = params['page']
    total_pages = max(1, (total_books + per_page - 1) // per_page) if total_books else 1

    return {
        'awards': awards_list,
        'books': books_data,
        'years': years,
        'selected_award': params['selected_award'],
        'selected_year': params['selected_year'] if params['selected_year'] else None,
        'search_query': params['search_query'],
        'view_mode': params['view_mode'],
        'total_books': total_books,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
    }


@main_bp.route('/new-books')
def new_books():
    """新书速递页面"""
    from ..services.new_book_service import NewBookService

    params = _parse_new_books_params(request.args)
    service = NewBookService()
    context = _load_new_books_data(service, params)
    return render_template('new_books.html', **context)


def _parse_new_books_params(args) -> dict:
    """解析 new_books() 的查询参数（含安全的数值钳制）"""
    selected_publisher_raw = args.get('publisher', '')
    selected_publisher = (
        int(selected_publisher_raw) if selected_publisher_raw and selected_publisher_raw.isdigit() else None
    )
    selected_category = args.get('category', '')

    try:
        selected_days = min(max(1, int(args.get('days', '30'))), 365)
    except (ValueError, TypeError):
        selected_days = 30

    search_query = args.get('search', '').strip()[:100]

    try:
        page = min(max(1, int(args.get('page', '1'))), 10000)
    except (ValueError, TypeError):
        page = 1

    view_mode = args.get('view', 'grid')
    if view_mode not in ['grid', 'list']:
        view_mode = 'grid'

    return {
        'selected_publisher': selected_publisher,
        'selected_category': selected_category,
        'selected_days': selected_days,
        'search_query': search_query,
        'page': page,
        'per_page': 20,
        'view_mode': view_mode,
    }


def _load_new_books_data(service, params: dict) -> dict:
    """加载 new_books() 渲染所需数据，每段查询独立降级"""
    try:
        service.ensure_static_data_seeded()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'新书静态数据兜底初始化失败: {e}', level='warning')

    try:
        publishers = service.get_publishers(active_only=True)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取出版社列表失败: {e}', level='warning')
        publishers = []

    try:
        publisher_book_counts = service.get_publisher_book_counts()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取出版社图书计数失败: {e}')
        publisher_book_counts = {}

    try:
        categories = service.get_categories()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取分类列表失败: {e}', level='warning')
        categories = []

    try:
        stats = service.get_statistics()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取统计数据失败: {e}', level='warning')
        stats = {
            'total_books': 0,
            'total_publishers': 0,
            'active_publishers': 0,
            'recent_books_7d': 0,
            'top_categories': [],
        }

    page = params['page']
    per_page = params['per_page']
    selected_publisher = params['selected_publisher']
    selected_category = params['selected_category']
    selected_days = params['selected_days']
    search_query = params['search_query']

    try:
        if search_query:
            books, total = service.search_books(
                search_query,
                page,
                per_page,
                publisher_id=selected_publisher,
                category=selected_category if selected_category else None,
                days=selected_days,
            )
        else:
            books, total = service.get_new_books(
                publisher_id=selected_publisher,
                category=selected_category if selected_category else None,
                days=selected_days,
                page=page,
                per_page=per_page,
            )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取书籍数据失败: {e}', level='warning')
        books, total = [], 0

    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    return {
        'publishers': publishers,
        'publisher_book_counts': publisher_book_counts,
        'categories': categories,
        'books': books,
        'stats': stats,
        'selected_publisher': selected_publisher,
        'selected_category': selected_category,
        'selected_days': selected_days,
        'search_query': search_query,
        'view_mode': params['view_mode'],
        'page': page,
        'total': total,
        'total_pages': total_pages,
        'per_page': per_page,
    }


@main_bp.route('/favicon.ico')
def favicon():
    """为浏览器根路径 favicon 请求提供重定向"""
    return send_from_directory(
        current_app.static_folder or current_app.root_path + '/static',
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon',
    )


@main_bp.route('/about')
def about():
    """关于我们页面"""
    return render_template('about.html')


@main_bp.route('/publishers')
def publishers():
    """出版社导航页面"""
    total_publishers = sum(len(cat['publishers']) for cat in PUBLISHERS_DATA)

    return render_template('publishers.html', publishers_data=PUBLISHERS_DATA, total_publishers=total_publishers)


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
    from ..services.new_book_service import NewBookService

    service = NewBookService()
    book = service.get_book(book_id)

    if not book:
        return render_template('error.html', message='书籍不存在', back_url=request.referrer or '/new-books')

    if not book.title_zh or not book.description_zh:
        translation_service = get_translation_service()
        if translation_service:

            def translate_book_async():
                service.translate_book_background(book_id, translation_service)

            submit_background_task(translate_book_async)

    return render_template('new_book_detail.html', book=book, back_url=request.referrer or '/new-books')


@main_bp.route('/award-book/<int:book_id>')
def award_book_detail(book_id):
    """获奖图书详情（通过 Service 层）"""
    from ..services.award_book_service import AwardBookService

    award_service = AwardBookService()
    book = award_service.get_award_book_by_id(book_id)

    if book:
        if not book.is_displayable:
            return render_template(
                'error.html',
                message='该获奖图书已下架',
                back_url=request.referrer or '/awards',
            )
        return render_template('award_book_detail.html', book=book, back_url=request.referrer or '/awards')
    else:
        return render_template('error.html', message='书籍不存在', back_url=request.referrer or '/awards')


@main_bp.route('/book/<int:book_index>')
def book_detail(book_index):
    """书籍详情页（集成 Google Books API 获取详细信息）"""
    categories = current_app.config['CATEGORIES']
    default_category = next(iter(categories.keys()))

    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category

    books_data, _ = _get_books_for_category(category)

    if book_index < 0 or book_index >= len(books_data):
        return render_template('error.html', message='书籍不存在', back_url=request.referrer or '/')

    book = books_data[book_index]

    isbn = book.get('isbn13') or book.get('isbn10')
    if isbn and is_valid_isbn(isbn):
        fetch_google_books_details(book, isbn)
        merge_or_translate_book(book, isbn)

    return render_template(
        'book_detail.html',
        book=book,
        book_index=book_index,
        category=category,
        back_url=request.referrer or '/?category=' + category,
    )


@main_bp.route('/api/book-details')
@handle_api_errors
def book_details_api():
    """获取书籍详细信息 API"""
    book_index = request.args.get('book_index', type=int)
    isbn = request.args.get('isbn')
    category = request.args.get('category')

    if book_index is None or not isbn:
        return APIResponse.error('缺少必要参数: book_index 和 isbn', 400)

    books_data, _ = _get_books_for_category(category or '')

    if book_index < 0 or book_index >= len(books_data):
        return APIResponse.error('书籍不存在', 404)

    book = books_data[book_index]
    details = book.get('description', '暂无详细介绍')

    return APIResponse.success(data={'details': details})


@main_bp.route('/api/category-books')
@handle_api_errors
def api_category_books():
    """AJAX获取分类图书列表"""
    categories = current_app.config['CATEGORIES']
    category = request.args.get('category', next(iter(categories.keys())))

    if category not in categories:
        return APIResponse.error('无效的分类', 400)

    books_data = []
    update_time = None

    try:
        book_service = get_book_service()
        if book_service:
            try:
                books = book_service.get_books_by_category(category)
                if books:
                    books_data = [book.to_dict() for book in books]
                    update_time = book_service.get_cache_time(category)
            except Exception as e:
                log_error(ErrorCategory.API_CALL, f'获取分类 {category} 图书失败: {e}', exc_info=True)
                # 降级返回空列表，前端会显示空状态
                books_data = []
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'图书服务不可用: {e}', exc_info=True)

    return APIResponse.success(data={'books': books_data, 'category': category, 'update_time': update_time})


@main_bp.route('/reports/weekly')
def weekly_reports():
    """周报列表

    v0.9.46 自愈机制：调用 service.get_or_trigger_current_week_report()
    检查 expected week 是否存在，缺失时后台线程异步补生成。
    页面继续展示最新已有周报 + 顶部黄色横幅 + 30s 轮询状态。
    """
    from ..services.weekly_report_service import WeeklyReportService

    book_service = get_book_service()
    if not book_service:
        return render_template('error.html', message='服务不可用', back_url='/')

    report_service = WeeklyReportService(book_service)
    latest_report, is_generating = report_service.get_or_trigger_current_week_report()
    reports = report_service.get_reports()

    for report in reports:
        report.content_data = parse_report_content(report) or {}

    return render_template(
        'weekly_reports.html',
        reports=reports,
        latest_report=latest_report,
        is_generating=is_generating,
    )


@main_bp.route('/api/weekly-report/status')
def weekly_report_status():
    """周报状态轮询端点（v0.9.46 新增）

    供前端 30s 轮询检查 expected week 周报是否已生成。
    仅查 DB，不调 NYT API，对 Render 免费版几乎无压力。
    """
    from datetime import date

    from ..services.weekly_report_service import WeeklyReportService
    from ..tasks.weekly_report_task_helpers import compute_expected_week_range

    book_service = get_book_service()
    if not book_service:
        return jsonify({'error': '服务不可用'}), 503

    report_service = WeeklyReportService(book_service)
    today = date.today()
    week_start, week_end = compute_expected_week_range(today)
    has_current = report_service.is_current_week_report_ready()
    latest = report_service.get_latest_report()

    return jsonify(
        {
            'has_current_week': has_current,
            'expected_week_start': week_start.isoformat(),
            'expected_week_end': week_end.isoformat(),
            'latest_week_end': latest.week_end.isoformat() if latest else None,
        }
    )


@main_bp.route('/reports/weekly/<date>')
def weekly_report_detail(date):
    """周报详情（通过 Service 层）"""

    from ..services.weekly_report_service import WeeklyReportService

    book_service = get_book_service()
    if not book_service:
        return render_template('error.html', message='服务不可用', back_url='/reports/weekly')

    is_valid, error_msg, report_date = validate_date(date)
    if not is_valid:
        return render_template('error.html', message=error_msg, back_url='/reports/weekly')

    report_service = WeeklyReportService(book_service)

    try:
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_template('error.html', message='周报不存在', back_url='/reports/weekly')

        session_id = request.cookies.get('session_id', 'anonymous')
        user_agent = request.user_agent.string[:500]
        ip_address = hash_client_ip()

        report_service.record_report_view(
            report_id=report.id,
            session_id=session_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        content_data = parse_report_content(report)
        return render_template('weekly_report_detail.html', report=report, content=content_data)

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'周报详情渲染错误: {e!s}', exc_info=True)
        return render_template('error.html', message='周报加载失败，请稍后再试', back_url='/reports/weekly'), 500


@main_bp.route('/reports/weekly/<date>/export')
def export_weekly_report(date):
    """导出周报（PDF/Markdown）"""

    from flask import send_file

    from ..services.export_service import ExportService
    from ..services.weekly_report_service import WeeklyReportService

    book_service = get_book_service()
    if not book_service:
        return render_template('error.html', message='服务不可用', back_url='/reports/weekly')

    is_valid, error_msg, report_date = validate_date(date)
    if not is_valid:
        return render_template('error.html', message=error_msg, back_url='/reports/weekly')

    report_service = WeeklyReportService(book_service)
    export_service = ExportService()

    try:
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_template('error.html', message='周报不存在', back_url='/reports/weekly')

        format_type = request.args.get('format', 'pdf').lower()
        if format_type not in ['pdf', 'excel']:
            return render_template('error.html', message='不支持的导出格式', back_url=f'/reports/weekly/{date}')

        export_config = {
            'pdf': {
                'export_method': export_service.export_weekly_report_pdf,
                'error_message': 'PDF导出失败',
                'filename': f'bookrank-weekly-report-{date}.pdf',
                'mimetype': 'application/pdf',
            },
            'excel': {
                'export_method': export_service.export_weekly_report_excel,
                'error_message': 'Excel导出失败',
                'filename': f'bookrank-weekly-report-{date}.xlsx',
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            },
        }

        config = export_config[format_type]
        buffer = config['export_method'](report)
        if not buffer:
            return render_template('error.html', message=config['error_message'], back_url=f'/reports/weekly/{date}')

        session_id = request.cookies.get('session_id', 'anonymous')
        user_agent = request.user_agent.string[:500]
        ip_address = hash_client_ip()

        # 通过 Service 层记录导出行为
        report_service.record_report_export(
            session_id=session_id,
            date=date,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return send_file(buffer, as_attachment=True, download_name=config['filename'], mimetype=config['mimetype'])

    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'导出周报时出错: {e!s}')
        return render_template('error.html', message='导出失败', back_url=f'/reports/weekly/{date}')


@main_bp.route('/robots.txt')
def robots_txt():
    """Serve robots.txt for search engine crawlers"""
    return send_from_directory(str(PROJECT_ROOT / 'static'), 'robots.txt', mimetype='text/plain')


@main_bp.route('/sitemap.xml')
def sitemap_xml():
    """Serve sitemap.xml for search engine crawlers"""
    return send_from_directory(str(PROJECT_ROOT / 'static'), 'sitemap.xml', mimetype='application/xml')


@main_bp.route('/set-language')
def set_language():
    """设置语言偏好，写入 cookie 后重定向"""
    lang = request.args.get('lang', 'en')
    if lang not in ('en', 'zh'):
        lang = 'en'
    next_url = request.args.get('next', '/')
    if not is_safe_redirect_url(next_url, allowed_hosts={request.host}):
        next_url = '/'
    response = make_response(redirect(next_url))
    # 获取当前请求的域名用于设置 cookie domain
    host = request.host.split(':')[0]  # 去掉端口号
    # 对于 Render 等部署平台，需要设置正确的 domain
    cookie_domain = host if '.' in host else None
    response.set_cookie('lang', lang, max_age=60 * 60 * 24 * 365, samesite='Lax', domain=cookie_domain, path='/')
    return response
