import logging
import os
import secrets
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import current_app, request

from .api_helpers import APIResponse

logger = logging.getLogger(__name__)

_auth_failures: dict[str, dict[str, float | int]] = {}
_AUTH_MAX_FAILURES = 5
_AUTH_BLOCK_SECONDS = 900
_AUTH_MAX_ENTRIES = 10000


def _cleanup_auth_failures(now: float) -> None:
    """清理已过期的认证失败记录，防止内存无限增长"""
    if len(_auth_failures) <= _AUTH_MAX_ENTRIES:
        return
    expired = [ip for ip, state in _auth_failures.items() if now > float(state.get('blocked_until', 0))]
    for ip in expired:
        _auth_failures.pop(ip, None)


def _get_admin_secret() -> str:
    return current_app.config.get('ADMIN_SECRET') or os.environ.get('ADMIN_SECRET', '')


def admin_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """管理员认证装饰器：通过 X-Admin-Secret 请求头验证，含限流和审计日志。"""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        admin_secret = _get_admin_secret()
        if not admin_secret:
            logger.warning('ADMIN_SECRET 未配置，管理员接口已禁用')
            return APIResponse.error('管理员接口未配置，请设置 ADMIN_SECRET 环境变量', 503)

        client_ip = request.remote_addr or 'unknown'
        now = time.time()

        _cleanup_auth_failures(now)

        if client_ip in _auth_failures:
            state = _auth_failures[client_ip]
            blocked_until = float(state.get('blocked_until', 0))
            if now < blocked_until:
                logger.warning(f'管理员认证被限流 (IP: {client_ip}, 封禁至: {blocked_until})')
                return APIResponse.error('认证失败次数过多，请稍后重试', 429)
            if int(state.get('count', 0)) >= _AUTH_MAX_FAILURES:
                _auth_failures.pop(client_ip, None)

        auth_header = request.headers.get('X-Admin-Secret', '')
        if not secrets.compare_digest(auth_header, admin_secret):
            state = _auth_failures.setdefault(client_ip, {'count': 0, 'blocked_until': 0})
            state['count'] = int(state.get('count', 0)) + 1
            logger.warning(f'管理员认证失败 (IP: {client_ip}, 尝试: {state["count"]}/{_AUTH_MAX_FAILURES})')

            if int(state['count']) >= _AUTH_MAX_FAILURES:
                state['blocked_until'] = now + _AUTH_BLOCK_SECONDS
                logger.warning(f'管理员认证封禁 (IP: {client_ip}, 封禁 {_AUTH_BLOCK_SECONDS}s)')

            return APIResponse.error('需要管理员权限', 403)

        _auth_failures.pop(client_ip, None)
        return f(*args, **kwargs)

    return wrapped
