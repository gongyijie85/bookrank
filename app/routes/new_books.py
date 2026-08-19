import csv
import logging
import threading
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from flask import Blueprint, current_app, make_response, request
from pydantic import ValidationError

if TYPE_CHECKING:
    from ..services.new_book import NewBookModules

from ..schemas.validators import (
    NewBookExportQuery,
    NewBookListQuery,
    NewBookSearchQuery,
    NewBookSyncQuery,
    parse_query_args,
)
from ..utils.admin_auth import admin_required
from ..utils.api_helpers import APIResponse, csrf_protect
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.service_helpers import (
    get_new_book_modules,
    get_sync_request_gate,
    submit_background_task,
)

logger = logging.getLogger(__name__)

new_books_bp = Blueprint('new_books', __name__, url_prefix='/api/new-books')

_SYNC_COOLDOWN_SECONDS: int = 60
_EXPORT_COOLDOWN_SECONDS: int = 10  # v0.9.68: CSV 导出每 IP 限速
_CSV_INJECTION_PREFIXES: tuple[str, ...] = ('=', '+', '-', '@', '\t', '\r')

# 同步任务状态（进程内单一任务槽）：全量同步含外部爬虫 + LLM 翻译，
# 最坏可达每社 600s x 5 社，不能占住请求线程（Render 免费版网关超时约 100s）。
# POST 触发后立即返回 202，前端/运维轮询 GET /sync/status 获取进度与结果。
_sync_task_lock = threading.Lock()
_sync_task: dict[str, Any] = {'status': 'idle'}


def _sanitize_csv_field(value: object) -> str:
    """v0.9.68: 防止 CSV 公式注入 — 对以 = + - @ \t \r 起始的字段加单引号前缀。"""
    if value is None:
        return ''
    text = str(value)
    if text and text[0] in _CSV_INJECTION_PREFIXES:
        return "'" + text
    return text


def _cooldown_message(verb: str, remaining: float) -> str:
    """冷却期消息的统一格式（同步与导出共用）。"""
    return f'{verb}过于频繁,请 {int(remaining)} 秒后再试'


def _check_export_cooldown() -> str | None:
    """v0.9.68: 每 IP 导出冷却(10 秒)防刷（状态在同步请求闸门内）。"""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'anon').split(',')[0].strip()
    remaining = get_sync_request_gate().export_cooldown_remaining(ip)
    if remaining is not None:
        return _cooldown_message('导出', remaining)
    return None


def _parse_or_422(model_cls):
    """v0.9.63 新增：把当前 request.args 解析为 model_cls；失败返回 (None, response_422)。"""
    try:
        parsed = parse_query_args(model_cls, request.args)
        return parsed, None
    except ValidationError as e:
        msg = '; '.join(f'{".".join(str(p) for p in err["loc"])}: {err["msg"]}' for err in e.errors())
        return None, APIResponse.error(f'参数无效: {msg}', 422)


def _ensure_static_seeded(modules: 'NewBookModules') -> None:
    """静态数据兜底播种（进程内一次性，状态在同步请求闸门内）。"""
    try:
        get_sync_request_gate().seed_static_data(modules.sync_engine)
    except Exception as e:
        logger.warning(f'新书静态数据兜底初始化失败: {e}')


def _acquire_sync_slot() -> str | None:
    """原子地占用同步冷却（检查+记录一步，消除并发双双通过的竞态窗口）。"""
    remaining = get_sync_request_gate().try_acquire_sync()
    if remaining is not None:
        return _cooldown_message('同步操作', remaining)
    return None


def _submit_sync_job(runner) -> tuple[bool, Any]:
    """占用同步任务槽并提交后台执行；已在运行时返回 (False, 409 响应)。"""
    with _sync_task_lock:
        if _sync_task.get('status') == 'running':
            return False, APIResponse.error('已有同步任务在执行中，请先等待完成', 409)
        _sync_task.clear()
        _sync_task.update({'status': 'running', 'started_at': datetime.now(UTC).isoformat()})
    try:
        submit_background_task(runner)
    except Exception:
        with _sync_task_lock:
            _sync_task.update({'status': 'error', 'error': '后台任务提交失败'})
        raise
    return True, None


def _finish_sync_job(**fields: Any) -> None:
    """后台任务结束时落最终状态（success/error）。"""
    with _sync_task_lock:
        _sync_task.update({'finished_at': datetime.now(UTC).isoformat(), **fields})


@new_books_bp.route('/publishers')
def get_publishers():
    """获取出版社列表（批量查询书籍数量，避免N+1）"""
    try:
        modules = get_new_book_modules()
        _ensure_static_seeded(modules)
        publishers = modules.publisher_manager.get_publishers(active_only=True)
        book_counts = modules.publisher_manager.get_publisher_book_counts()

        result = []
        for pub in publishers:
            result.append(
                {
                    'id': pub.id,
                    'name': pub.name,
                    'name_en': pub.name_en,
                    'website': pub.website,
                    'is_active': pub.is_active,
                    'book_count': book_counts.get(pub.id, 0),
                    'last_sync_at': pub.last_sync_at.isoformat() if pub.last_sync_at else None,
                }
            )
        return APIResponse.success(data={'publishers': result})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取出版社列表失败: {e}', exc_info=True)
        return APIResponse.error('获取出版社列表失败', 500)


@new_books_bp.route('/publishers/<int:publisher_id>')
def get_publisher(publisher_id: int):
    """获取单个出版社详情"""
    try:
        modules = get_new_book_modules()
        publisher = modules.publisher_manager.get_publisher(publisher_id)
        if not publisher:
            return APIResponse.error('出版社不存在', 404)
        return APIResponse.success(data={'publisher': publisher.to_dict(include_book_count=True)})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取出版社详情失败: {e}', exc_info=True)
        return APIResponse.error('获取出版社详情失败', 500)


@new_books_bp.route('/publishers/<int:publisher_id>/status', methods=['POST'])
@csrf_protect
@admin_required
def update_publisher_status(publisher_id: int):
    """更新出版社状态"""
    try:
        if not request.is_json:
            return APIResponse.error('Content-Type must be application/json', 400)

        data = request.get_json() or {}
        is_active = data.get('is_active')
        if is_active is None:
            return APIResponse.error('缺少 is_active 参数', 400)

        modules = get_new_book_modules()
        success = modules.publisher_manager.update_publisher_status(publisher_id, is_active)
        if not success:
            return APIResponse.error('出版社不存在', 404)

        return APIResponse.success(message=f'出版社已{"启用" if is_active else "禁用"}')
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'更新出版社状态失败: {e}', exc_info=True)
        return APIResponse.error('更新出版社状态失败', 500)


@new_books_bp.route('')
def get_new_books():
    """获取新书列表"""
    query, err = _parse_or_422(NewBookListQuery)
    if err is not None:
        return err
    assert query is not None
    publisher_id = query.publisher_id
    category = query.category
    days = query.days
    search_query = query.search
    page, per_page = query.page, query.per_page

    try:
        modules = get_new_book_modules()
        _ensure_static_seeded(modules)
        if search_query:
            books, total = modules.query_service.search_books(
                search_query,
                page,
                per_page,
                publisher_id=publisher_id,
                category=category,
                days=days,
            )
        else:
            books, total = modules.query_service.get_new_books(
                publisher_id=publisher_id, category=category, days=days, page=page, per_page=per_page
            )

        return APIResponse.success(
            data={
                'books': [b.to_dict() for b in books],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page,
                },
                'update_time': datetime.now(UTC).isoformat(),
            }
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取新书列表失败: {e}', exc_info=True)
        return APIResponse.error('获取新书列表失败', 500)


@new_books_bp.route('/<int:book_id>')
def get_book_detail(book_id: int):
    """获取新书详情"""
    try:
        modules = get_new_book_modules()
        book = modules.query_service.get_book(book_id)
        if not book:
            return APIResponse.error('图书不存在', 404)
        return APIResponse.success(data={'book': book.to_dict()})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取图书详情失败: {e}', exc_info=True)
        return APIResponse.error('获取图书详情失败', 500)


@new_books_bp.route('/search')
def search_new_books():
    """搜索新书"""
    query, err = _parse_or_422(NewBookSearchQuery)
    if err is not None:
        return err
    assert query is not None
    keyword = query.keyword
    page, per_page = query.page, query.per_page

    try:
        modules = get_new_book_modules()
        _ensure_static_seeded(modules)
        books, total = modules.query_service.search_books(
            keyword,
            page,
            per_page,
            publisher_id=query.publisher_id,
            category=query.category,
            days=query.days,
        )

        return APIResponse.success(
            data={
                'keyword': keyword,
                # 独立搜索端点不驱动新书速递卡片徽章,不携带"刚上市"判定字段
                'books': [b.to_dict(include_freshness=False) for b in books],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page,
                },
            }
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'搜索新书失败: {e}', exc_info=True)
        return APIResponse.error('搜索失败', 500)


@new_books_bp.route('/categories')
def get_categories():
    """获取分类列表"""
    try:
        modules = get_new_book_modules()
        _ensure_static_seeded(modules)
        categories = modules.query_service.get_categories()
        return APIResponse.success(data={'categories': categories})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取分类列表失败: {e}', exc_info=True)
        return APIResponse.error('获取分类列表失败', 500)


@new_books_bp.route('/sync', methods=['POST'])
@csrf_protect
@admin_required
def sync_all_publishers():
    """同步所有出版社新书（后台任务，立即返回 202；含冷却与单任务限制）"""
    cooldown_error = _acquire_sync_slot()
    if cooldown_error:
        return APIResponse.error(cooldown_error, 429)

    try:
        max_books = min(max(1, request.args.get('max_books', 30, type=int)), 100)
        app_obj = current_app._get_current_object()

        def _run_sync_all() -> None:
            with app_obj.app_context():
                try:
                    modules = get_new_book_modules()
                    modules.publisher_manager.init_publishers()
                    results = modules.sync_engine.sync_all_publishers(max_books_per_publisher=max_books)

                    total_added = sum(r.get('added', 0) for r in results)
                    total_updated = sum(r.get('updated', 0) for r in results)
                    total_errors = sum(r.get('errors', 0) for r in results)
                    summary = {
                        'total_publishers': len(results),
                        'total_added': total_added,
                        'total_updated': total_updated,
                        'total_errors': total_errors,
                    }
                    _finish_sync_job(status='success', kind='all', summary=summary, results=results)
                except Exception as e:
                    log_error(ErrorCategory.CRAWLER, f'后台同步新书失败: {e}', exc_info=True)
                    _finish_sync_job(status='error', kind='all', error=str(e))

        # 冷却已在 _acquire_sync_slot 原子占用；任务期间由单一任务槽互斥
        submitted, conflict = _submit_sync_job(_run_sync_all)
        if not submitted:
            return conflict

        return APIResponse.success(
            data={'status': 'submitted', 'max_books': max_books},
            message='同步已提交后台执行，可通过 /api/new-books/sync/status 查询进度',
            status_code=202,
        )
    except Exception as e:
        log_error(ErrorCategory.CRAWLER, f'提交同步任务失败: {e}', exc_info=True)
        return APIResponse.error(f'提交同步任务失败: {e!s}', 500)


@new_books_bp.route('/sync/<int:publisher_id>', methods=['POST'])
@csrf_protect
@admin_required
def sync_publisher(publisher_id: int):
    """同步指定出版社新书（后台任务，立即返回 202；含冷却与单任务限制）"""
    cooldown_error = _acquire_sync_slot()
    if cooldown_error:
        return APIResponse.error(cooldown_error, 429)

    try:
        sync_q, err = _parse_or_422(NewBookSyncQuery)
        if err is not None:
            return err
        assert sync_q is not None
        app_obj = current_app._get_current_object()

        def _run_sync_publisher() -> None:
            with app_obj.app_context():
                try:
                    modules = get_new_book_modules()
                    result = modules.sync_engine.sync_publisher_books(publisher_id, max_books=sync_q.max_books)
                    if result.get('success'):
                        _finish_sync_job(status='success', kind='publisher', publisher_id=publisher_id, result=result)
                    else:
                        _finish_sync_job(
                            status='error',
                            kind='publisher',
                            publisher_id=publisher_id,
                            error=result.get('error', '同步失败'),
                            result=result,
                        )
                except Exception as e:
                    log_error(ErrorCategory.CRAWLER, f'后台同步出版社新书失败: {e}', exc_info=True)
                    _finish_sync_job(status='error', kind='publisher', publisher_id=publisher_id, error=str(e))

        # 冷却已在 _acquire_sync_slot 原子占用；任务期间由单一任务槽互斥
        submitted, conflict = _submit_sync_job(_run_sync_publisher)
        if not submitted:
            return conflict

        return APIResponse.success(
            data={'status': 'submitted', 'publisher_id': publisher_id, 'max_books': sync_q.max_books},
            message='同步已提交后台执行，可通过 /api/new-books/sync/status 查询进度',
            status_code=202,
        )
    except Exception as e:
        log_error(ErrorCategory.CRAWLER, f'提交同步任务失败: {e}', exc_info=True)
        return APIResponse.error(f'提交同步任务失败: {e!s}', 500)


@new_books_bp.route('/sync/status')
@admin_required
def get_sync_status():
    """查询最近一次同步任务的执行状态（idle/running/success/error）"""
    with _sync_task_lock:
        snapshot = dict(_sync_task)
    return APIResponse.success(data=snapshot)


@new_books_bp.route('/statistics')
def get_statistics():
    """获取统计数据"""
    try:
        modules = get_new_book_modules()
        _ensure_static_seeded(modules)
        stats = modules.query_service.get_statistics()
        return APIResponse.success(data=stats)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取统计数据失败: {e}', exc_info=True)
        return APIResponse.error('获取统计数据失败', 500)


@new_books_bp.route('/export/csv')
def export_csv():
    """导出CSV格式(限制最大导出数量 + 速率限制 + 公式注入防护)"""
    cooldown_error = _check_export_cooldown()
    if cooldown_error:
        return APIResponse.error(cooldown_error, 429)

    query, err = _parse_or_422(NewBookExportQuery)
    if err is not None:
        return err
    assert query is not None
    try:
        modules = get_new_book_modules()
        _ensure_static_seeded(modules)

        books, _ = modules.query_service.get_new_books(
            publisher_id=query.publisher_id,
            category=query.category,
            days=query.days,
            page=1,
            per_page=500,
        )

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                '书名',
                '中文书名',
                '作者',
                '出版社',
                '分类',
                '出版日期',
                'ISBN-13',
                'ISBN-10',
                '价格',
                '页数',
                '语言',
                '简介',
                '中文简介',
                '来源链接',
            ]
        )

        for book in books:
            writer.writerow(
                [
                    _sanitize_csv_field(book.title),
                    _sanitize_csv_field(book.title_zh or ''),
                    _sanitize_csv_field(book.author),
                    _sanitize_csv_field(book.publisher.name if book.publisher else ''),
                    _sanitize_csv_field(book.category or ''),
                    book.publication_date.isoformat() if book.publication_date else '',
                    _sanitize_csv_field(book.isbn13 or ''),
                    _sanitize_csv_field(book.isbn10 or ''),
                    _sanitize_csv_field(book.price or ''),
                    book.page_count or '',
                    _sanitize_csv_field(book.language or ''),
                    _sanitize_csv_field(book.description or ''),
                    _sanitize_csv_field(book.description_zh or ''),
                    _sanitize_csv_field(book.source_url or ''),
                ]
            )

        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

        response = make_response(response_data)
        # v0.9.64 L2: RFC 5987 国际化文件名（支持 UTF-8 编码）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_ascii = f'NewBooks_{timestamp}.csv'  # ASCII 备用名（旧浏览器）
        filename_utf8 = f'新书速递_{timestamp}.csv'  # UTF-8 编码（现代浏览器）
        response.headers['Content-Disposition'] = (
            f'attachment; filename="{filename_ascii}"; filename*=UTF-8\'\'{quote(filename_utf8)}'
        )
        response.headers['Content-type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'导出CSV失败: {e}', exc_info=True)
        return APIResponse.error('导出失败', 500)


@new_books_bp.route('/init', methods=['POST'])
@csrf_protect
@admin_required
def init_publishers():
    """初始化出版社数据"""
    try:
        modules = get_new_book_modules()
        count = modules.publisher_manager.init_publishers()
        return APIResponse.success(data={'created_count': count}, message=f'成功初始化 {count} 个出版社')
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'初始化出版社失败: {e}', exc_info=True)
        return APIResponse.error('初始化失败', 500)


@new_books_bp.route('/migrate-categories', methods=['POST'])
@csrf_protect
@admin_required
def migrate_categories():
    """迁移已有书籍分类数据（英文分类统一为中文），走分类清洗模块"""
    try:
        from ..services.category_cleanup_service import apply_cleanup

        result = apply_cleanup(dry_run=False)

        return APIResponse.success(
            data={
                'migrated_count': result.updated,
                'total_checked': result.total_checked,
            },
            message=f'成功迁移 {result.updated} 本书籍分类',
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'迁移分类数据失败: {e}', exc_info=True)
        return APIResponse.error('迁移分类失败', 500)


@new_books_bp.errorhandler(404)
def not_found(error):
    return APIResponse.error('Resource not found', 404)


@new_books_bp.errorhandler(500)
def internal_error(error):
    # 框架级异常回滚：释放可能处于未提交状态的数据库会话，避免连接泄漏
    # 注：errorhandler 属于框架级钩子，非业务路由，允许直接操作 db.session
    from ..models.database import db

    db.session.rollback()
    return APIResponse.error('Internal server error', 500)
