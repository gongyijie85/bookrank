import secrets

from flask import Blueprint, current_app, request, session

api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_session_id() -> str:
    """获取或生成安全的会话ID"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return session['session_id']


def validate_category(category: str) -> bool:
    """验证分类ID是否有效"""
    categories = current_app.config.get('CATEGORIES', {})
    return category in categories or category == 'all'


def _verify_bearer(config_key: str) -> bool:
    """验证请求携带的 Bearer token 与指定配置密钥一致"""
    secret = current_app.config.get(config_key) or ''
    if not secret:
        current_app.logger.warning(f'{config_key} 未配置，拒绝请求')
        return False

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False

    token = auth_header[7:]
    return secrets.compare_digest(token, secret)


@api_bp.route('/health')
def health_check():
    """健康检查端点"""
    from ...utils.api_helpers import APIResponse

    return APIResponse.success(data={'status': 'healthy', 'service': 'book-rank-api'})


@api_bp.route('/csrf-token')
def get_csrf_token_endpoint():
    """获取CSRF令牌端点（含速率限制：每 IP 每分钟最多 10 次）"""
    from flask import request

    from ...utils.api_helpers import APIResponse, get_csrf_token
    from ...utils.rate_limiter import get_rate_limiter

    csrf_limiter = get_rate_limiter(max_requests=10, window_seconds=60)
    client_ip = request.remote_addr or 'unknown'
    if not csrf_limiter.is_allowed(client_ip):
        return APIResponse.error('Too many requests', 429)

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
    # 框架级异常回滚：释放可能处于未提交状态的数据库会话，避免连接泄漏
    from ...models.database import db
    from ...utils.api_helpers import APIResponse

    db.session.rollback()
    return APIResponse.error('Internal server error', 500)


from . import awards, batch_import, books, cache, cron, favorites, recommendations, translation

favorites.register_favorite_routes(api_bp)
