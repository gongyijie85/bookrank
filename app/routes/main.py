import ipaddress
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

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
from ..services.book_detail_service import fetch_google_books_details, merge_or_translate_book
from ..utils import ExternalAPIError
from ..utils.api_helpers import APIResponse, handle_api_errors, quick_clean_translation, validate_isbn
from ..utils.book_filters import (
    filter_books_by_publisher,
    filter_books_by_search,
    filter_books_by_weeks,
    get_category_update_frequency,
    sort_books,
)
from ..utils.date_helpers import parse_report_content, validate_date
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.ranking import classify_listing
from ..utils.security import is_safe_redirect_url
from ..utils.template_resolver import render_adaptive

PROJECT_ROOT = Path(__file__).parent.parent.parent
from ..utils.service_helpers import (
    get_google_books_client,
    get_new_book_modules,
    get_or_create_recommendation_service,
    get_service,
    get_sync_request_gate,
    hash_client_ip,
    submit_background_task,
)

main_bp = Blueprint('main', __name__)


def _get_list_published_date(books_data: list[dict]) -> str | None:
    for book in books_data:
        published_date = book.get('published_date')
        if published_date and published_date != 'Unknown':
            return str(published_date)
    return None


def _get_books_for_category(category: str, **kwargs: Any) -> tuple[list, str | None]:
    """获取指定分类的书籍数据（统一入口）"""
    categories = current_app.config['CATEGORIES']
    default_category = next(iter(categories.keys()))
    if category not in categories:
        category = default_category

    book_service = get_service('book_service')
    if not book_service:
        return [], None

    books_data, update_time = [], None

    try:
        books = book_service.get_books_by_category(category, **kwargs) or []
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


def _fetch_all_category_books(categories: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """抓取全部分类的当前榜；单个分类失败时跳过该分类，不影响其余数据。"""
    result: dict[str, list[dict[str, Any]]] = {}
    for key in categories:
        try:
            books_data, _ = _get_books_for_category(key, auto_translate=False, notify_refresh=False)
        except ExternalAPIError as e:
            e.log()
            continue
        result[key] = books_data
    return result


def _search_all_categories(search_query: str, categories: dict[str, str]) -> list[dict[str, Any]]:
    """跨全部分类抓取并标注来源分类（#66）；过滤由调用方的 filter_books_by_search 完成"""
    merged: list[dict[str, Any]] = []
    for key, books_data in _fetch_all_category_books(categories).items():
        for idx, book in enumerate(books_data):
            book['source_category'] = key
            book['source_index'] = (book.get('rank') or (idx + 1)) - 1
            merged.append(book)
    return merged


@main_bp.route('/')
def index():
    """首页 - 畅销书榜单（支持多维度筛选和排序）"""
    categories = current_app.config['CATEGORIES']
    default_category = next(iter(categories.keys()))

    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category

    search_query = request.args.get('search', '').strip()[:100]
    # 默认网格视图：15 本 4-5 列 × 3 行（用户期望；list 视图仍可切换）
    view_mode = request.args.get('view', 'grid')
    if view_mode not in ['grid', 'list']:
        view_mode = 'grid'

    publisher_filter = request.args.get('publisher', '').strip()
    weeks_filter = request.args.get('weeks', '')
    sort_by = request.args.get('sort', '')

    books_data: list[dict[str, Any]] = []
    update_time: str | None = None
    if search_query:
        # 跨全部分类搜索（#66）：不再受当前选中分类限制，结果标注来源分类
        books_data = _search_all_categories(search_query, categories)
        update_time = None
    else:
        try:
            books_data, update_time = _get_books_for_category(category)
        except ExternalAPIError as e:
            e.log()
            # 降级：用空列表渲染页面，不崩溃

    update_frequency = get_category_update_frequency(category)
    list_published_date = _get_list_published_date(books_data)

    if search_query:
        books_data = filter_books_by_search(books_data, search_query)
    if publisher_filter:
        books_data = filter_books_by_publisher(books_data, publisher_filter)
    if weeks_filter:
        books_data = filter_books_by_weeks(books_data, weeks_filter)

    if sort_by:
        books_data = sort_books(books_data, sort_by)

    for book in books_data:
        listing_status = classify_listing(book.get('rank_last_week'), book.get('weeks_on_list'))
        book['previous_rank'] = listing_status.previous_rank
        book['is_new'] = listing_status.is_new
        book['is_returning'] = listing_status.is_returning

    publishers = sorted(
        set(
            b.get('publisher', '')
            for b in books_data
            if b.get('publisher') and b.get('publisher') not in ('Unknown', 'Unknown Publisher')
        )
    )

    return render_adaptive(
        'index.html',
        categories=categories,
        category_names_en=current_app.config.get('CATEGORY_NAMES_EN', {}),
        category_groups=current_app.config.get('CATEGORY_GROUPS', {}),
        group_labels={
            'fiction': '小说',
            'nonfiction': '非虚构',
            'children-ya': '儿童与青少年',
            'business': '商业',
            'lifestyle': '生活方式与杂项',
            'comics': '漫画与绘本',
        },
        books=books_data,
        current_category=category,
        search_query=search_query,
        view_mode=view_mode,
        update_time=update_time,
        publishers=publishers,
        publisher_filter=publisher_filter,
        weeks_filter=weeks_filter,
        sort_by=sort_by,
        update_frequency=update_frequency,
        list_published_date=list_published_date,
        monthly_categories=sorted(
            category_id
            for category_id, frequency in current_app.config['NYT_CATEGORY_UPDATE_FREQUENCIES'].items()
            if frequency == 'monthly'
        ),
        active_tab='home',
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
    from ..services.award_book_service import AwardBookService
    from ..services.award_cover_sync_service import AwardCoverSyncService

    book = AwardBookService().get_award_book_by_id(book_id)
    if not book:
        abort(404)
    sync_service = AwardCoverSyncService(
        get_google_books_client(),
        image_cache=get_service('image_cache_service'),
    )

    try:
        cover_url = sync_service._resolver.resolve(book)
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
    context['active_tab'] = 'awards'
    return render_adaptive('awards.html', **context)


def _parse_awards_params(args) -> dict:
    """从请求参数中提取并校验 awards() 所需的查询条件"""
    selected_award = args.get('award', '')
    selected_year = args.get('year', '')
    selected_category = args.get('category', '')
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
        'selected_category': selected_category,
        'search_query': search_query,
        'view_mode': view_mode,
        'page': page,
        'per_page': per_page,
    }


def _shape_award_book(book) -> dict:
    """将 AwardBook ORM 对象塑形为 awards 模板所需的 dict。

    title_en 取原始 DB title 供前端 data-en 使用；若原始 title 是 ISBN 脏数据
    则退回 display_title。title_zh 同理，ISBN 脏数据直接清空。
    """
    from ..models.schemas import AwardBook

    raw_title = (book.title or '').strip()
    title_en = (
        book.display_title or '' if AwardBook._looks_like_isbn(raw_title) else (raw_title or book.display_title or '')
    )

    raw_zh = quick_clean_translation(book.title_zh, 'title')
    title_zh = '' if AwardBook._looks_like_isbn(raw_zh or '') else (raw_zh or '')

    return {
        'id': book.id,
        'title': book.display_title,
        'title_en': title_en,
        'title_zh': title_zh,
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


def _build_award_sections(award_service, awards_list: list, limit: int = 12) -> list:
    """按奖项分组的精选书列（亚马逊获奖图书页的横向书列区块）。

    仅在无任何筛选条件时调用；每个奖项一次带 limit 的查询，次数受奖项数约束。
    """
    sections: list = []
    for award in awards_list:
        try:
            books, _total = award_service.get_award_books(
                award_id=award.id,
                include_displayable_only=True,
                page=1,
                limit=limit,
            )
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'奖项书列查询失败 award={award.name}: {e}', level='warning')
            continue
        if books:
            sections.append({'award': award, 'books': [_shape_award_book(b) for b in books]})
    return sections


def _load_awards_data(award_service, params: dict) -> dict:
    """加载 awards() 渲染所需的所有数据，返回模板上下文 dict（含分页元信息）"""
    awards_list: list = []
    years: list = []
    categories: list = []
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
        categories = award_service.get_distinct_categories()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'类别列表查询失败: {e}', level='warning')
        categories = []

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
            category=params['selected_category'] or None,
            keyword=params['search_query'] or None,
            include_displayable_only=True,
            page=params['page'],
            limit=params['per_page'],
        )

        for book in books:
            books_data.append(_shape_award_book(book))

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

    is_browsing = not (
        params['selected_award'] or params['selected_year'] or params['selected_category'] or params['search_query']
    )
    award_sections = _build_award_sections(award_service, awards_list) if is_browsing else []

    return {
        'awards': awards_list,
        'books': books_data,
        'award_sections': award_sections,
        'years': years,
        'categories': categories,
        'selected_award': params['selected_award'],
        'selected_year': params['selected_year'] if params['selected_year'] else None,
        'selected_category': params['selected_category'] if params['selected_category'] else None,
        'search_query': params['search_query'],
        'view_mode': params['view_mode'],
        'total_books': total_books,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
    }


RANKING_TABS = ('cross', 'longevity', 'overlooked', 'publishers')
# 遗珠榜只看最近若干个年度的获奖记录：更早的获奖书早已离开畅销榜是常态，不构成"遗珠"
OVERLOOKED_YEAR_SPAN = 3
OVERLOOKED_AWARD_BOOKS_PER_YEAR = 300
PUBLISHER_LEADERBOARD_LIMIT = 30
LONGEVITY_LIMIT = 20


def _load_recent_award_books(award_service, years: list[int]) -> list[dict]:
    """逐年取可展示的获奖图书；不改 AwardBookService，避免影响其查询数回归测试。"""
    from ..models.schemas import AwardBook

    records: list[dict] = []
    for year in years:
        try:
            books, _total = award_service.get_award_books(
                year=year,
                include_displayable_only=True,
                page=1,
                limit=OVERLOOKED_AWARD_BOOKS_PER_YEAR,
            )
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'遗珠榜获奖数据加载失败 year={year}: {e}', level='warning')
            continue
        for book in books:
            raw_zh = quick_clean_translation(book.title_zh, 'title')
            records.append(
                {
                    'id': book.id,
                    'title': book.display_title,
                    'title_zh': '' if AwardBook._looks_like_isbn(raw_zh or '') else (raw_zh or ''),
                    'author': book.author,
                    'publisher': book.publisher,
                    'isbn13': book.isbn13,
                    'year': book.year,
                    'category': book.category,
                    'cover_local_path': book.cover_local_path,
                    'cover_original_url': book.cover_original_url,
                    'award_name': book.award.name if book.award else '',
                    'award_name_en': book.award.name_en if book.award else '',
                }
            )
    return records


@main_bp.route('/rankings')
def rankings():
    """派生榜单：跨榜现象级 / 长销常青榜 / 遗珠榜 / 厂牌榜，全部由现有数据二次加工"""
    from datetime import UTC, datetime

    from ..services.award_book_service import AwardBookService
    from ..services.derived_lists_service import (
        build_cross_list_entries,
        build_longevity_entries,
        build_overlooked_entries,
        build_publisher_entries,
    )

    tab = request.args.get('tab', 'cross')
    if tab not in RANKING_TABS:
        tab = 'cross'

    categories = current_app.config['CATEGORIES']
    books_by_category = _fetch_all_category_books(categories)

    cross_entries = [entry.to_dict() for entry in build_cross_list_entries(books_by_category)]
    longevity_entries = [entry.to_dict() for entry in build_longevity_entries(books_by_category, limit=LONGEVITY_LIMIT)]
    publisher_entries = [
        entry.to_dict() for entry in build_publisher_entries(books_by_category, limit=PUBLISHER_LEADERBOARD_LIMIT)
    ]

    current_year = datetime.now(UTC).year
    award_years = list(range(current_year, current_year - OVERLOOKED_YEAR_SPAN, -1))
    award_books = _load_recent_award_books(AwardBookService(), award_years)
    overlooked_entries = [entry.to_dict() for entry in build_overlooked_entries(award_books, books_by_category)]

    book_service = get_service('book_service')
    update_time = book_service.get_latest_cache_time() if book_service else None

    return render_adaptive(
        'rankings.html',
        tab=tab,
        cross_entries=cross_entries,
        longevity_entries=longevity_entries,
        overlooked_entries=overlooked_entries,
        publisher_entries=publisher_entries,
        award_years=award_years,
        category_count=len(categories),
        category_names_en=current_app.config.get('CATEGORY_NAMES_EN', {}),
        update_time=update_time,
        active_tab='rankings',
    )


@main_bp.route('/new-books')
def new_books():
    """新书速递页面"""
    params = _parse_new_books_params(request.args)
    modules = get_new_book_modules()
    context = _load_new_books_data(modules, params)
    return render_adaptive('new_books.html', **context)


def _parse_new_books_params(args) -> dict:
    """解析 new_books() 的查询参数（含安全的数值钳制）"""
    selected_publisher_raw = args.get('publisher', '')
    selected_publisher = (
        int(selected_publisher_raw) if selected_publisher_raw and selected_publisher_raw.isdigit() else None
    )
    selected_category = args.get('category', '')

    try:
        # 默认 30 天：维护者决议的"新书"标准（出版 30 天内），与 API 默认一致
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


def _load_new_books_data(modules, params: dict) -> dict:
    """加载 new_books() 渲染所需数据，每段查询独立降级"""
    try:
        get_sync_request_gate().seed_static_data(modules.sync_engine)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'新书静态数据兜底初始化失败: {e}', level='warning')

    try:
        publishers = modules.publisher_manager.get_publishers(active_only=True)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取出版社列表失败: {e}', level='warning')
        publishers = []

    try:
        publisher_book_counts = modules.publisher_manager.get_publisher_book_counts()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取出版社图书计数失败: {e}')
        publisher_book_counts = {}

    try:
        categories = modules.query_service.get_categories()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取分类列表失败: {e}', level='warning')
        categories = []

    try:
        stats = modules.query_service.get_statistics()
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
            books, total = modules.query_service.search_books(
                search_query,
                page,
                per_page,
                publisher_id=selected_publisher,
                category=selected_category if selected_category else None,
                days=selected_days,
            )
        else:
            books, total = modules.query_service.get_new_books(
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

    publisher_sections: list = []
    is_browsing = not (selected_publisher or selected_category or search_query)
    if is_browsing:
        try:
            publisher_sections = _build_new_book_publisher_sections(
                modules, publishers, publisher_book_counts, selected_days
            )
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'新书出版社书列加载失败: {e}', level='warning')

    return {
        'publishers': publishers,
        'publisher_book_counts': publisher_book_counts,
        'publisher_sections': publisher_sections,
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


@main_bp.route('/openapi.json')
def openapi_spec():
    """机器可读 OpenAPI 3.1 规范（ROADMAP #1）"""
    return send_from_directory(
        current_app.static_folder or current_app.root_path + '/static',
        'openapi.json',
        mimetype='application/json',
    )


@main_bp.route('/about')
def about():
    """关于我们页面"""
    return render_adaptive('about.html')


def _resolve_new_books_publisher_ids(publishers_data: list[dict], db_publishers: list) -> dict[str, int]:
    """把出版社目录条目映射到新书速递数据库对应出版社的 id（仅对已抓取入库的出版社生效）。

    目录条目可用可选字段 sync_name_en 声明与 DB 出版社的关联键（名称写法不一致时），
    缺省回退到 name_en 精确匹配。
    """
    id_by_db_name_en = {pub.name_en: pub.id for pub in db_publishers}
    result: dict[str, int] = {}
    for cat in publishers_data:
        for pub in cat['publishers']:
            name_en = pub.get('name_en', '')
            db_name_en = pub.get('sync_name_en', name_en)
            pub_id = id_by_db_name_en.get(db_name_en)
            if pub_id is not None:
                result[name_en] = pub_id
    return result


def _build_publisher_sections(publishers_data: list, publisher_ids: dict, modules, limit: int = 8) -> list:
    """按出版社分类聚合的最近新书书列。

    一次 get_new_books 查询 + Python 侧按 publisher_id 分桶，避免逐出版社发查询；
    窗口沿用新书链路统一的 30 天口径，某分类 30 天内无新书则不出该栏。
    """
    category_index_by_id: dict[int, int] = {}
    for idx, cat in enumerate(publishers_data):
        for pub in cat['publishers']:
            pid = publisher_ids.get(pub['name_en'])
            if pid is not None:
                category_index_by_id[pid] = idx
    if not category_index_by_id:
        return []

    books, _total = modules.query_service.get_new_books(days=30, page=1, per_page=200)

    buckets: dict[int, list] = defaultdict(list)
    for book in books:
        cat_idx = category_index_by_id.get(book.publisher_id)
        if cat_idx is None or len(buckets[cat_idx]) >= limit:
            continue
        buckets[cat_idx].append(book)

    return [
        {'category': cat['category'], 'index': i + 1, 'books': buckets[i]}
        for i, cat in enumerate(publishers_data)
        if buckets.get(i)
    ]


def _build_new_book_publisher_sections(
    modules, publishers: list, publisher_book_counts: dict, days: int, limit: int = 8, max_sections: int = 6
) -> list:
    """按出版社聚合的新书书列。

    沿用页面当前时间窗口，一次 get_new_books 查询 + Python 侧按 publisher_id 分桶，
    避免逐出版社发查询；按各出版社新书数降序取前若干栏，窗口内无新书的出版社不出栏。
    """
    ranked = sorted(
        (p for p in publishers if publisher_book_counts.get(p.id)),
        key=lambda p: publisher_book_counts.get(p.id, 0),
        reverse=True,
    )[:max_sections]
    wanted = {p.id: p for p in ranked}
    if not wanted:
        return []

    books, _total = modules.query_service.get_new_books(days=days, page=1, per_page=300)

    buckets: dict[int, list] = defaultdict(list)
    for book in books:
        if book.publisher_id in wanted and len(buckets[book.publisher_id]) < limit:
            buckets[book.publisher_id].append(book)

    return [{'publisher': wanted[pid], 'books': buckets[pid]} for pid in wanted if buckets.get(pid)]


@main_bp.route('/publishers')
def publishers():
    """出版社导航页面"""
    total_publishers = sum(len(cat['publishers']) for cat in PUBLISHERS_DATA)
    publisher_sections: list = []

    try:
        modules = get_new_book_modules()
        new_books_publisher_ids = _resolve_new_books_publisher_ids(
            PUBLISHERS_DATA, modules.publisher_manager.get_publishers(active_only=True)
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'出版社跳转链接匹配失败: {e}', level='warning')
        new_books_publisher_ids = {}
        modules = None

    if modules and new_books_publisher_ids:
        try:
            publisher_sections = _build_publisher_sections(PUBLISHERS_DATA, new_books_publisher_ids, modules)
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'出版社新书书列加载失败: {e}', level='warning')

    return render_adaptive(
        'publishers.html',
        publishers_data=PUBLISHERS_DATA,
        publisher_sections=publisher_sections,
        total_publishers=total_publishers,
        new_books_publisher_ids=new_books_publisher_ids,
        active_tab='publisher',
    )


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
    modules = get_new_book_modules()
    book = modules.query_service.get_book(book_id)

    if not book:
        return render_adaptive('error.html', message='书籍不存在', back_url=request.referrer or '/new-books')

    if not book.title_zh or not book.description_zh:
        translation_service = get_service('translation_service')
        if translation_service:

            def translate_book_async():
                modules.translation_pipeline.translate_book_background(book_id, translation_service)

            submit_background_task(translate_book_async)

    return render_adaptive('new_book_detail.html', book=book, back_url=request.referrer or '/new-books')


@main_bp.route('/award-book/<int:book_id>')
def award_book_detail(book_id):
    """获奖图书详情（通过 Service 层）"""
    from ..models.schemas import AwardBook
    from ..services.award_book_service import AwardBookService

    award_service = AwardBookService()
    book = award_service.get_award_book_by_id(book_id)

    if book:
        if not book.is_displayable:
            return render_adaptive(
                'error.html',
                message='该获奖图书已下架',
                back_url=request.referrer or '/awards',
            )

        # 清理 title 字段中的 ISBN 脏数据
        raw_title = (book.title or '').strip()
        safe_title_en = '' if AwardBook._looks_like_isbn(raw_title) else raw_title

        raw_zh = quick_clean_translation(book.title_zh, 'title')
        safe_title_zh = '' if AwardBook._looks_like_isbn(raw_zh or '') else (raw_zh or '')

        # 兜底：如果两个字段都是 ISBN，使用 display_title
        display_title = book.display_title
        if not safe_title_en and not safe_title_zh:
            safe_title_en = display_title
            safe_title_zh = display_title

        try:
            recommendation_service = get_or_create_recommendation_service()
            related_books = recommendation_service.get_similarity_recommendations(book_id=book.id).get(
                'recommendations', []
            )
        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'相关获奖图书推荐加载失败 book_id={book_id}: {e}', level='warning')
            related_books = []

        return render_adaptive(
            'award_book_detail.html',
            book=book,
            safe_title_en=safe_title_en or display_title,
            safe_title_zh=safe_title_zh or safe_title_en,
            related_books=related_books,
            back_url=request.referrer or '/awards',
        )
    else:
        return render_adaptive('error.html', message='书籍不存在', back_url=request.referrer or '/awards')


@main_bp.route('/book/<int:book_index>')
def book_detail(book_index):
    """书籍详情页（集成 Google Books API 获取详细信息）"""
    categories = current_app.config['CATEGORIES']
    default_category = next(iter(categories.keys()))

    category = request.args.get('category', default_category)
    if category not in categories:
        category = default_category

    try:
        books_data, _ = _get_books_for_category(category)
    except ExternalAPIError as e:
        e.log()
        books_data = []

    if book_index < 0 or book_index >= len(books_data):
        return render_adaptive('error.html', message='书籍不存在', back_url=request.referrer or '/')

    book = books_data[book_index]

    isbn = book.get('isbn13') or book.get('isbn10')
    if isbn and validate_isbn(isbn):
        fetch_google_books_details(book, isbn)
        merge_or_translate_book(book, isbn)

    return render_adaptive(
        'book_detail.html',
        book=book,
        book_index=book_index,
        category=category,
        categories=categories,
        back_url=request.referrer or '/?category=' + category,
        active_tab='home',
    )


@main_bp.route('/profile')
def profile():
    """个人中心 - 收藏与搜索历史（移动端优先，匿名会话）"""
    from ..services.user_service import UserService

    session_id = request.cookies.get('session_id', 'anonymous')
    service = UserService()
    favorites = service.get_favorites(session_id)
    search_history = service.get_search_history(session_id, limit=10)

    # 用 BookMetadata 富化收藏列表（补全书名/作者）
    for fav in favorites:
        isbn = fav.get('isbn', '')
        if isbn:
            meta = service.get_book_metadata(isbn)
            if meta:
                fav['title'] = meta.title_zh or meta.title
                fav['author'] = meta.author
            else:
                fav['title'] = isbn
                fav['author'] = ''

    return render_adaptive(
        'profile.html',
        favorites=favorites,
        search_history=search_history,
        session_id=session_id,
        active_tab='profile',
    )


@main_bp.route('/search')
def search_page():
    """移动端搜索入口页（桌面端重定向到首页）"""
    from ..utils.device_detect import is_mobile

    if not is_mobile():
        return redirect('/')
    return render_template('mobile/search.html', active_tab='search')


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
    details = book.get('details') or book.get('description') or '暂无详细介绍'

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
        book_service = get_service('book_service')
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

    return APIResponse.success(
        data={
            'books': books_data,
            'category': category,
            'update_time': update_time,
            'update_frequency': get_category_update_frequency(category),
            'list_published_date': _get_list_published_date(books_data),
        }
    )


def _group_reports_by_month(reports: list) -> list:
    """按月份倒序分组周报，供列表页的月度书列区块使用。

    report_date 为空的脏记录直接跳过，避免分组时抛异常拖垮整页。
    """
    groups: dict[tuple[int, int], list] = {}
    for report in reports:
        report_date = getattr(report, 'report_date', None)
        if not report_date:
            continue
        groups.setdefault((report_date.year, report_date.month), []).append(report)

    return [{'year': y, 'month': m, 'reports': rs} for (y, m), rs in sorted(groups.items(), reverse=True)]


@main_bp.route('/reports/weekly')
def weekly_reports():
    """周报列表

    v0.9.46 自愈机制：调用 service.get_or_trigger_current_week_report()
    检查 expected week 是否存在，缺失时后台线程异步补生成。
    页面继续展示最新已有周报 + 顶部黄色横幅 + 30s 轮询状态。
    """
    from ..services.weekly_report_service import WeeklyReportService

    book_service = get_service('book_service')
    if not book_service:
        return render_adaptive('error.html', message='服务不可用', back_url='/')

    report_service = WeeklyReportService(book_service)
    latest_report, is_generating = report_service.get_or_trigger_current_week_report()
    reports = report_service.get_reports()

    for report in reports:
        report.content_data = parse_report_content(report) or {}

    return render_adaptive(
        'weekly_reports.html',
        reports=reports,
        report_sections=_group_reports_by_month(reports),
        latest_report=latest_report,
        is_generating=is_generating,
        active_tab='weekly',
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

    book_service = get_service('book_service')
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

    book_service = get_service('book_service')
    if not book_service:
        return render_adaptive('error.html', message='服务不可用', back_url='/reports/weekly')

    is_valid, error_msg, report_date = validate_date(date)
    if not is_valid:
        return render_adaptive('error.html', message=error_msg, back_url='/reports/weekly')

    report_service = WeeklyReportService(book_service)

    try:
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_adaptive('error.html', message='周报不存在', back_url='/reports/weekly')

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
        return render_adaptive(
            'weekly_report_detail.html',
            report=report,
            content=content_data,
            active_tab='weekly',
        )

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'周报详情渲染错误: {e!s}', exc_info=True)
        return render_adaptive('error.html', message='周报加载失败，请稍后再试', back_url='/reports/weekly'), 500


@main_bp.route('/reports/weekly/<date>/export')
def export_weekly_report(date):
    """导出周报（PDF/Markdown）"""

    from flask import send_file

    from ..services.export_service import ExportService
    from ..services.weekly_report_service import WeeklyReportService

    book_service = get_service('book_service')
    if not book_service:
        return render_adaptive('error.html', message='服务不可用', back_url='/reports/weekly')

    is_valid, error_msg, report_date = validate_date(date)
    if not is_valid:
        return render_adaptive('error.html', message=error_msg, back_url='/reports/weekly')

    report_service = WeeklyReportService(book_service)
    export_service = ExportService()

    try:
        report = report_service.get_report_by_week_end(report_date)
        if not report:
            report = report_service.get_report_by_date(report_date)
            if not report:
                return render_adaptive('error.html', message='周报不存在', back_url='/reports/weekly')

        format_type = request.args.get('format', 'pdf').lower()
        if format_type not in ['pdf', 'excel']:
            return render_adaptive('error.html', message='不支持的导出格式', back_url=f'/reports/weekly/{date}')

        export_config: dict[str, dict[str, Any]] = {
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
            return render_adaptive('error.html', message=config['error_message'], back_url=f'/reports/weekly/{date}')

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
        return render_adaptive('error.html', message='导出失败', back_url=f'/reports/weekly/{date}')


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
    # IP/localhost 不能带 Domain，否则移动端局域网访问时浏览器会拒收 cookie。
    host = request.host.rsplit(':', 1)[0].strip('[]')
    try:
        ipaddress.ip_address(host)
        cookie_domain = None
    except ValueError:
        cookie_domain = host if host and host != 'localhost' and '.' in host else None
    response.set_cookie('lang', lang, max_age=60 * 60 * 24 * 365, samesite='Lax', domain=cookie_domain, path='/')
    return response
