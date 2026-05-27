import logging

from flask import session

from ...models.database import db
from ...models.schemas import UserFavorite
from ...utils.api_helpers import APIResponse
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

            favorites = (
                UserFavorite.query.filter_by(session_id=sid)
                .order_by(UserFavorite.created_at.desc())
                .all()
            )
            return APIResponse.success(
                data={'favorites': [f.to_dict() for f in favorites], 'total': len(favorites)}
            )
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'获取收藏列表失败: {e}')
            db.session.rollback()
            return APIResponse.error('Internal server error', 500)

    @bp.route('/favorites', methods=['POST'])
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

            existing = UserFavorite.query.filter_by(session_id=sid, isbn=isbn).first()
            if existing:
                return APIResponse.success(data=existing.to_dict(), message='已在收藏中')

            fav = UserFavorite(session_id=sid, isbn=isbn)
            db.session.add(fav)
            db.session.commit()
            return APIResponse.success(data=fav.to_dict(), message='收藏成功', status_code=201)
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'添加收藏失败: {e}')
            db.session.rollback()
            return APIResponse.error('Internal server error', 500)

    @bp.route('/favorites/<isbn>', methods=['DELETE'])
    def remove_favorite(isbn: str):
        try:
            sid = _get_session_id()
            if not sid:
                return APIResponse.error('会话无效', 400)

            fav = UserFavorite.query.filter_by(session_id=sid, isbn=isbn).first()
            if not fav:
                return APIResponse.error('收藏不存在', 404)

            db.session.delete(fav)
            db.session.commit()
            return APIResponse.success(message='已取消收藏')
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'删除收藏失败: {e}')
            db.session.rollback()
            return APIResponse.error('Internal server error', 500)

    @bp.route('/favorites/check/<isbn>', methods=['GET'])
    def check_favorite(isbn: str):
        try:
            sid = _get_session_id()
            if not sid:
                return APIResponse.success(data={'is_favorited': False})

            fav = UserFavorite.query.filter_by(session_id=sid, isbn=isbn).first()
            return APIResponse.success(data={'is_favorited': fav is not None})
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'检查收藏状态失败: {e}')
            return APIResponse.error('Internal server error', 500)
