import logging

from flask import session

from ...services.user_service import UserService
from ...utils.api_helpers import APIResponse, csrf_protect
from ...utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


def _get_session_id() -> str:
    return session.get('session_id', '')


def register_favorite_routes(bp):
    """注册收藏相关路由到指定 Blueprint"""

    @bp.route('/favorites', methods=['GET'])
    def get_favorites():
        try:
            sid = _get_session_id()
            if not sid:
                return APIResponse.success(data={'favorites': [], 'total': 0})

            _user_svc = UserService()
            favorites = _user_svc.get_favorites(sid)
            return APIResponse.success(data={'favorites': favorites, 'total': len(favorites)})
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'获取收藏列表失败: {e}')
            return APIResponse.error('Internal server error', 500)

    @bp.route('/favorites', methods=['POST'])
    @csrf_protect
    def add_favorite():
        try:
            from flask import request

            data = request.get_json(silent=True) or {}
            isbn = (data.get('isbn') or '').strip()
            if not isbn or len(isbn) not in (10, 13):
                return APIResponse.error('ISBN格式无效', 400)

            sid = _get_session_id()
            if not sid:
                return APIResponse.error('会话无效', 400)

            _user_svc = UserService()
            result, is_new = _user_svc.add_favorite(sid, isbn)
            if is_new:
                return APIResponse.success(data=result, message='收藏成功', status_code=201)
            return APIResponse.success(data=result, message='已在收藏中')
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'添加收藏失败: {e}')
            return APIResponse.error('Internal server error', 500)

    @bp.route('/favorites/<isbn>', methods=['DELETE'])
    @csrf_protect
    def remove_favorite(isbn: str):
        try:
            sid = _get_session_id()
            if not sid:
                return APIResponse.error('会话无效', 400)

            _user_svc = UserService()
            removed = _user_svc.remove_favorite(sid, isbn)
            if not removed:
                return APIResponse.error('收藏不存在', 404)
            return APIResponse.success(message='已取消收藏')
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'删除收藏失败: {e}')
            return APIResponse.error('Internal server error', 500)

    @bp.route('/favorites/check/<isbn>', methods=['GET'])
    def check_favorite(isbn: str):
        try:
            sid = _get_session_id()
            if not sid:
                return APIResponse.success(data={'is_favorited': False})

            _user_svc = UserService()
            is_fav = _user_svc.check_favorite(sid, isbn)
            return APIResponse.success(data={'is_favorited': is_fav})
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'检查收藏状态失败: {e}')
            return APIResponse.error('Internal server error', 500)
