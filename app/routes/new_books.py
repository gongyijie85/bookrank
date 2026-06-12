import csv
import logging
import time
from datetime import UTC, datetime
from io import StringIO
from urllib.parse import quote

from flask import Blueprint, make_response, request
from pydantic import ValidationError

from ..models.database import db
from ..schemas.validators import (
    NewBookExportQuery,
    NewBookListQuery,
    NewBookSearchQuery,
    NewBookSyncQuery,
    parse_query_args,
)
from ..services.new_book_service import NewBookService
from ..utils.admin_auth import admin_required
from ..utils.api_helpers import APIResponse, csrf_protect
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.service_helpers import get_translation_service

logger = logging.getLogger(__name__)

new_books_bp = Blueprint('new_books', __name__, url_prefix='/api/new-books')

_last_sync_time: float = 0.0
_SYNC_COOLDOWN_SECONDS: int = 60


def _parse_or_422(model_cls):
    """v0.9.63 新增：把当前 request.args 解析为 model_cls；失败返回 (None, response_422)。"""
    try:
        parsed = parse_query_args(model_cls, request.args)
        return parsed, None
    except ValidationError as e:
        msg = '; '.join(f'{".".join(str(p) for p in err["loc"])}: {err["msg"]}' for err in e.errors())
        return None, APIResponse.error(f'参数无效: {msg}', 422)


def get_new_book_service() -> NewBookService:
    """获取新书服务单例"""
    return NewBookService(translation_service=get_translation_service())


def _ensure_static_seeded(service: NewBookService) -> None:
    try:
        service.ensure_static_data_seeded()
    except Exception as e:
        logger.warning(f'新书静态数据兜底初始化失败: {e}')


def _check_sync_cooldown() -> str | None:
    """检查同步冷却时间，返回错误消息或None"""
    global _last_sync_time
    elapsed = time.time() - _last_sync_time
    if elapsed < _SYNC_COOLDOWN_SECONDS:
        remaining = int(_SYNC_COOLDOWN_SECONDS - elapsed)
        return f'同步操作过于频繁，请 {remaining} 秒后再试'
    return None


@new_books_bp.route('/publishers')
def get_publishers():
    """获取出版社列表（批量查询书籍数量，避免N+1）"""
    try:
        service = get_new_book_service()
        _ensure_static_seeded(service)
        publishers = service.get_publishers(active_only=True)
        book_counts = service.get_publisher_book_counts()

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
        service = get_new_book_service()
        publisher = service.get_publisher(publisher_id)
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

        service = get_new_book_service()
        success = service.update_publisher_status(publisher_id, is_active)
        if not success:
            return APIResponse.error('出版社不存在', 404)

        return APIResponse.success(message=f'出版社已{"启用" if is_active else "禁用"}')
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'更新出版社状态失败: {e}', exc_info=True)
        db.session.rollback()
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
        service = get_new_book_service()
        _ensure_static_seeded(service)
        if search_query:
            books, total = service.search_books(
                search_query,
                page,
                per_page,
                publisher_id=publisher_id,
                category=category,
                days=days,
            )
        else:
            books, total = service.get_new_books(
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
        service = get_new_book_service()
        book = service.get_book(book_id)
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
        service = get_new_book_service()
        _ensure_static_seeded(service)
        books, total = service.search_books(keyword, page, per_page)

        return APIResponse.success(
            data={
                'keyword': keyword,
                'books': [b.to_dict() for b in books],
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
        service = get_new_book_service()
        _ensure_static_seeded(service)
        categories = service.get_categories()
        return APIResponse.success(data={'categories': categories})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取分类列表失败: {e}', exc_info=True)
        return APIResponse.error('获取分类列表失败', 500)


@new_books_bp.route('/sync', methods=['POST'])
@csrf_protect
@admin_required
def sync_all_publishers():
    """同步所有出版社新书（含冷却时间限制）"""
    global _last_sync_time

    cooldown_error = _check_sync_cooldown()
    if cooldown_error:
        return APIResponse.error(cooldown_error, 429)

    try:
        service = get_new_book_service()
        service.init_publishers()

        max_books = min(max(1, request.args.get('max_books', 30, type=int)), 100)
        results = service.sync_all_publishers(max_books_per_publisher=max_books)

        _last_sync_time = time.time()

        total_added = sum(r.get('added', 0) for r in results)
        total_updated = sum(r.get('updated', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)

        return APIResponse.success(
            data={
                'results': results,
                'summary': {
                    'total_publishers': len(results),
                    'total_added': total_added,
                    'total_updated': total_updated,
                    'total_errors': total_errors,
                },
            }
        )
    except Exception as e:
        log_error(ErrorCategory.CRAWLER, f'同步新书失败: {e}', exc_info=True)
        return APIResponse.error(f'同步失败: {e!s}', 500)


@new_books_bp.route('/sync/<int:publisher_id>', methods=['POST'])
@csrf_protect
@admin_required
def sync_publisher(publisher_id: int):
    """同步指定出版社新书（含冷却时间限制）"""
    global _last_sync_time

    cooldown_error = _check_sync_cooldown()
    if cooldown_error:
        return APIResponse.error(cooldown_error, 429)

    try:
        service = get_new_book_service()
        sync_q, err = _parse_or_422(NewBookSyncQuery)
        if err is not None:
            return err
        assert sync_q is not None
        result = service.sync_publisher_books(publisher_id, max_books=sync_q.max_books)

        if not result.get('success'):
            return APIResponse.error(result.get('error', '同步失败'), 400)

        _last_sync_time = time.time()

        return APIResponse.success(data=result)
    except Exception as e:
        log_error(ErrorCategory.CRAWLER, f'同步出版社新书失败: {e}', exc_info=True)
        return APIResponse.error(f'同步失败: {e!s}', 500)


@new_books_bp.route('/statistics')
def get_statistics():
    """获取统计数据"""
    try:
        service = get_new_book_service()
        _ensure_static_seeded(service)
        stats = service.get_statistics()
        return APIResponse.success(data=stats)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取统计数据失败: {e}', exc_info=True)
        return APIResponse.error('获取统计数据失败', 500)


@new_books_bp.route('/export/csv')
def export_csv():
    """导出CSV格式（限制最大导出数量）"""
    query, err = _parse_or_422(NewBookExportQuery)
    if err is not None:
        return err
    assert query is not None
    try:
        service = get_new_book_service()
        _ensure_static_seeded(service)

        books, _ = service.get_new_books(
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
                    book.title,
                    book.title_zh or '',
                    book.author,
                    book.publisher.name if book.publisher else '',
                    book.category or '',
                    book.publication_date.isoformat() if book.publication_date else '',
                    book.isbn13 or '',
                    book.isbn10 or '',
                    book.price or '',
                    book.page_count or '',
                    book.language or '',
                    book.description or '',
                    book.description_zh or '',
                    book.source_url or '',
                ]
            )

        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

        response = make_response(response_data)
        filename = f'新书速递_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response.headers['Content-Disposition'] = f'attachment; filename={quote(filename)}'
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
        service = get_new_book_service()
        count = service.init_publishers()
        return APIResponse.success(data={'created_count': count}, message=f'成功初始化 {count} 个出版社')
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'初始化出版社失败: {e}', exc_info=True)
        db.session.rollback()
        return APIResponse.error('初始化失败', 500)


@new_books_bp.errorhandler(404)
def not_found(error):
    return APIResponse.error('Resource not found', 404)


@new_books_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return APIResponse.error('Internal server error', 500)
