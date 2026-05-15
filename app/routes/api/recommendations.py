import logging

from flask import current_app, request

from ...utils.api_helpers import APIResponse, handle_api_errors, validate_pagination
from . import api_bp, get_session_id

logger = logging.getLogger(__name__)


@api_bp.route('/recommendations')
@handle_api_errors
def get_recommendations():
    """获取个性化推荐"""
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
            limit=limit,
        )
    elif strategy == 'smart':
        result = recommendation_service.get_smart_recommendations(session_id, limit)
    else:
        result = recommendation_service._get_popular_recommendations(limit)

    return APIResponse.success(data=result)


@api_bp.route('/recommendations/similarity')
@handle_api_errors
def get_similarity_recommendations():
    """获取相似图书推荐"""
    from app.services.recommendation_service import RecommendationService

    book_id = request.args.get('book_id', type=int)
    isbn = request.args.get('isbn')
    award_id = request.args.get('award_id', type=int)
    category = request.args.get('category')
    limit = min(max(1, request.args.get('limit', 10, type=int)), 50)

    if not any([book_id, isbn, award_id, category]):
        return APIResponse.error('请提供 book_id, isbn, award_id 或 category 参数之一', 400)

    categories = current_app.config.get('CATEGORIES', {})
    recommendation_service = RecommendationService(categories)

    result = recommendation_service.get_similarity_recommendations(
        book_id=book_id, isbn=isbn, award_id=award_id, category=category, limit=limit
    )

    return APIResponse.success(data=result)


@api_bp.route('/search/suggestions')
@handle_api_errors
def get_search_suggestions():
    """获取搜索建议（自动补全）"""
    from app.services.smart_search_service import SmartSearchService

    prefix = request.args.get('prefix', '').strip()
    limit = min(max(1, request.args.get('limit', 10, type=int)), 20)

    if not prefix:
        return APIResponse.success(data={'suggestions': [], 'prefix': prefix})

    categories = current_app.config.get('CATEGORIES', {})
    search_service = SmartSearchService(categories)
    result = search_service.get_suggestions(prefix, limit)

    return APIResponse.success(data=result)


@api_bp.route('/search/smart')
@handle_api_errors
def smart_search():
    """智能搜索（支持多种筛选条件）"""
    from app.services.smart_search_service import SmartSearchService

    keyword = request.args.get('keyword', '').strip()
    search_type = request.args.get('type', 'all')
    year = request.args.get('year', type=int)
    award_id = request.args.get('award_id', type=int)

    valid_types = ['all', 'title', 'author', 'publisher']
    if search_type not in valid_types:
        search_type = 'all'

    page, limit = validate_pagination(
        request.args.get('page', 1, type=int), request.args.get('limit', 20, type=int)
    )
    offset = (page - 1) * limit

    categories = current_app.config.get('CATEGORIES', {})
    search_service = SmartSearchService(categories)

    result = search_service.search(
        keyword=keyword, search_type=search_type, year=year, award_id=award_id, limit=limit, offset=offset
    )

    if keyword:
        session_id = get_session_id()
        search_service.save_search_history(session_id, keyword, result.get('total', 0))

    return APIResponse.success(data=result)


@api_bp.route('/search/popular')
@handle_api_errors
def get_popular_searches():
    """获取热门搜索词"""
    from app.services.smart_search_service import SmartSearchService

    limit = min(max(1, request.args.get('limit', 10, type=int)), 50)
    categories = current_app.config.get('CATEGORIES', {})
    search_service = SmartSearchService(categories)
    result = search_service.get_popular_searches(limit)

    return APIResponse.success(data=result)
