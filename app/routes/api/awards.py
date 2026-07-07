import logging

from flask import request

from ...services.award_book_service import AwardBookService
from ...utils.admin_auth import admin_required
from ...utils.api_helpers import APIResponse, csrf_protect, validate_pagination
from ...utils.error_handler import ErrorCategory, log_error
from . import api_bp

logger = logging.getLogger(__name__)

_award_service = AwardBookService()


@api_bp.route('/awards')
def get_awards():
    """获取所有奖项列表（通过 Service 层）"""
    try:
        awards = _award_service.get_all_awards()
        return APIResponse.success(data={'awards': [award.to_dict() for award in awards]})

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获取奖项列表错误: {e}', exc_info=True)
        return APIResponse.error('获取奖项列表失败', 500)


@api_bp.route('/awards/<int:award_id>/books')
def get_award_books(award_id: int):
    """获取指定奖项的图书列表（通过 Service 层）"""
    try:
        year = request.args.get('year', type=int)
        if year and (year < 1900 or year > 2100):
            return APIResponse.error('无效的年份', 400)

        award = _award_service.get_award_by_id(award_id)
        if not award:
            return APIResponse.error('奖项不存在', 404)

        category = request.args.get('category')
        page, limit = validate_pagination(
            request.args.get('page', 1, type=int), request.args.get('limit', 20, type=int)
        )

        books, total = _award_service.get_award_books(
            award_id=award_id, year=year, category=category, page=page, limit=limit
        )

        return APIResponse.success(
            data={
                'award': award.to_dict(),
                'books': [book.to_dict() for book in books],
                'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': (total + limit - 1) // limit},
            }
        )

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获取奖项图书错误: {e}', exc_info=True)
        return APIResponse.error('获取图书列表失败', 500)


@api_bp.route('/award-books')
def get_all_award_books():
    """获取所有获奖图书（支持筛选，通过 Service 层）"""
    try:
        award_id = request.args.get('award_id', type=int)
        year = request.args.get('year', type=int)
        if year and (year < 1900 or year > 2100):
            return APIResponse.error('无效的年份', 400)

        category = request.args.get('category')
        keyword = request.args.get('keyword')
        page, limit = validate_pagination(
            request.args.get('page', 1, type=int), request.args.get('limit', 20, type=int)
        )

        books, total = _award_service.get_award_books(
            award_id=award_id, year=year, category=category, keyword=keyword, page=page, limit=limit
        )

        return APIResponse.success(
            data={
                'books': [book.to_dict() for book in books],
                'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': (total + limit - 1) // limit},
            }
        )

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获取图书列表错误: {e}', exc_info=True)
        return APIResponse.error('获取图书列表失败', 500)


@api_bp.route('/award-books/<int:book_id>')
def get_award_book_detail(book_id: int):
    """获取图书详情（通过 Service 层）"""
    try:
        book = _award_service.get_award_book_by_id(book_id)
        if not book:
            return APIResponse.error('图书不存在', 404)

        return APIResponse.success(data={'book': book.to_dict(include_zh=True)})

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获取图书详情错误: {e}', exc_info=True)
        return APIResponse.error('获取图书详情失败', 500)


@api_bp.route('/award-books/search')
def search_award_books():
    """搜索获奖图书（通过 Service 层）"""
    try:
        keyword = request.args.get('keyword', '').strip()
        if not keyword:
            return APIResponse.error('搜索关键词不能为空', 400)
        if len(keyword) > 100:
            return APIResponse.error('关键词长度不能超过100个字符', 400)

        page, limit = validate_pagination(
            request.args.get('page', 1, type=int), request.args.get('limit', 20, type=int)
        )

        books, total = _award_service.search_award_books(keyword=keyword, page=page, limit=limit)

        return APIResponse.success(
            data={
                'keyword': keyword,
                'books': [book.to_dict() for book in books],
                'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': (total + limit - 1) // limit},
            }
        )

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'搜索图书错误: {e}', exc_info=True)
        return APIResponse.error('搜索失败', 500)


@api_bp.route('/admin/fix-award-book-titles', methods=['POST'])
@admin_required
@csrf_protect
def fix_award_book_titles():
    """修复历史脏数据：把 title 字段为 ISBN 的 AwardBook 记录用种子数据修正

    触发方式：POST /api/admin/fix-award-book-titles
    鉴权：需要请求头 X-Admin-Secret 匹配 ADMIN_SECRET（由 @admin_required 装饰器统一处理，含失败计数 / IP 封禁 / SystemConfig 持久化）
    """
    try:
        result = _award_service.fix_award_book_titles()
        fixed_entries = result['fixed_entries']
        debug_entries = result['debug_entries']
        logger.info(f'🔧 admin fix-award-book-titles: 修复 {len(fixed_entries)} 项')
        return APIResponse.success(
            data={
                'fixed_count': len(fixed_entries),
                'fixed': fixed_entries[:50],
                'debug_count': len(debug_entries),
                'debug_sample': debug_entries[:10],
            }
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'修复 AwardBook 标题失败: {e}', exc_info=True)
        return APIResponse.error(f'修复失败: {e}', 500)


@api_bp.route('/admin/fix-award-book-titles-by-ids', methods=['POST'])
@admin_required
@csrf_protect
def fix_award_book_titles_by_ids():
    """按 ID 批量修复 AwardBook.title_zh（处理非种子的脏数据）

    触发方式：POST /api/admin/fix-award-book-titles-by-ids
    鉴权：需要请求头 X-Admin-Secret 匹配 ADMIN_SECRET（由 @admin_required 装饰器统一处理）
    请求体：{"items": [{"id": 1, "title_zh": "詹姆斯"}, ...]}
    """

    if not request.is_json:
        return APIResponse.error('Content-Type must be application/json', 400)

    data = request.get_json() or {}
    items = data.get('items', [])
    if not isinstance(items, list) or not items:
        return APIResponse.error('items 必须是非空数组', 400)

    try:
        result = _award_service.fix_award_book_titles_by_ids(items)
        fixed_entries = result['fixed_entries']
        skipped = result['skipped']
        logger.info(f'🔧 admin fix-award-book-titles-by-ids: 修复 {len(fixed_entries)} 项')
        return APIResponse.success(
            data={
                'fixed_count': len(fixed_entries),
                'fixed': fixed_entries,
                'skipped': skipped,
            }
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'按 ID 修复 AwardBook 中文标题失败: {e}', exc_info=True)
        return APIResponse.error(f'修复失败: {e}', 500)
