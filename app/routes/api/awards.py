import logging

from flask import request

from ...services.award_book_service import AwardBookService
from ...utils.api_helpers import APIResponse, validate_pagination
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
        logger.error(f'获取奖项列表错误: {e}', exc_info=True)
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
        logger.error(f'获取奖项图书错误: {e}', exc_info=True)
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
        logger.error(f'获取图书列表错误: {e}', exc_info=True)
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
        logger.error(f'获取图书详情错误: {e}', exc_info=True)
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
        logger.error(f'搜索图书错误: {e}', exc_info=True)
        return APIResponse.error('搜索失败', 500)
