import re
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, request

from .rate_limiter import get_rate_limiter


class APIResponse:
    """统一API响应格式"""

    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message
        }
        return jsonify(response), status_code

    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


class PublicAPIResponse:
    """公开API响应格式（带时间戳）"""

    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        return jsonify(response), status_code

    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


def validate_isbn(isbn: str) -> bool:
    """验证ISBN格式（ISBN-10 或 ISBN-13）"""
    if not isbn:
        return False
    clean_isbn = re.sub(r'[^0-9X]', '', isbn.upper())
    if len(clean_isbn) == 10:
        return bool(re.match(r'^\d{9}[\dX]$', clean_isbn))
    elif len(clean_isbn) == 13:
        return bool(re.match(r'^\d{13}$', clean_isbn))
    return False


def validate_pagination(page: int, limit: int, max_limit: int = 50) -> tuple[int, int]:
    """验证并规范化分页参数"""
    page = min(max(1, page), 10000)
    limit = min(max(1, limit), max_limit)
    return page, limit


def api_rate_limit(max_requests: int = 60, window: int = 60):
    """API限流装饰器"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limiter = get_rate_limiter(max_requests, window)
            client_id = request.remote_addr or 'unknown'

            if not limiter.is_allowed(client_id):
                retry_after = limiter.get_retry_after(client_id)
                return APIResponse.error(
                    f'Rate limit exceeded. Retry after {retry_after}s.',
                    429
                )

            return f(*args, **kwargs)
        return wrapped
    return decorator


def public_rate_limit(max_requests: int = 60, window: int = 60):
    """公开API限流装饰器"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limiter = get_rate_limiter(max_requests, window)
            client_id = request.remote_addr or 'unknown'

            if not limiter.is_allowed(client_id):
                retry_after = limiter.get_retry_after(client_id)
                return PublicAPIResponse.error(
                    f'Rate limit exceeded. Retry after {retry_after}s.',
                    429
                )

            return f(*args, **kwargs)
        return wrapped
    return decorator
