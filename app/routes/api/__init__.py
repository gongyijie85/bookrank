import logging
import secrets

from flask import Blueprint, current_app, session

from ...services.user_service import UserService

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

_user_service = UserService()


def get_session_id() -> str:
    """获取或生成安全的会话ID"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return session['session_id']


def validate_category(category: str) -> bool:
    """验证分类ID是否有效"""
    categories = current_app.config.get('CATEGORIES', {})
    return category in categories or category == 'all'


@api_bp.route('/health')
def health_check():
    """健康检查端点"""
    from ...utils.api_helpers import APIResponse

    return APIResponse.success(data={'status': 'healthy', 'service': 'book-rank-api'})


@api_bp.route('/csrf-token')
def get_csrf_token_endpoint():
    """获取CSRF令牌端点"""
    from ...utils.api_helpers import APIResponse, get_csrf_token

    token = get_csrf_token()
    return APIResponse.success(data={'csrf_token': token})


@api_bp.errorhandler(404)
def not_found(error):
    from ...utils.api_helpers import APIResponse

    return APIResponse.error('Resource not found', 404)


@api_bp.errorhandler(405)
def method_not_allowed(error):
    from ...utils.api_helpers import APIResponse

    return APIResponse.error('Method not allowed', 405)


@api_bp.errorhandler(500)
def internal_error(error):
    from ...models.database import db
    from ...utils.api_helpers import APIResponse

    db.session.rollback()
    return APIResponse.error('Internal server error', 500)


from . import awards, books, cache, recommendations, translation
