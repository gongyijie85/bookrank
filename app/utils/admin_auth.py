import json
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
_PERSIST_KEY = 'admin_auth_failures'
_persist_loaded = False


def _cleanup_auth_failures(now: float) -> None:
    """清理已过期的认证失败记录，防止内存无限增长"""
    if len(_auth_failures) <= _AUTH_MAX_ENTRIES:
        return
    expired = [ip for ip, state in _auth_failures.items() if now > float(state.get('blocked_until', 0))]
    for ip in expired:
        _auth_failures.pop(ip, None)


def _load_persisted_failures() -> None:
    """从 SystemConfig 加载之前持久化的认证失败状态（启动后惰性触发一次）"""
    global _persist_loaded
    if _persist_loaded:
        return
    _persist_loaded = True
    try:
        from ..models.schemas import SystemConfig

        raw = SystemConfig.get_value(_PERSIST_KEY)
        if not raw:
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        now = time.time()
        for ip, state in data.items():
            if not isinstance(state, dict):
                continue
            blocked_until = float(state.get('blocked_until', 0))
            count = int(state.get('count', 0))
            # 只保留仍在封禁窗口内或最近的失败记录
            if blocked_until > now or count > 0:
                _auth_failures[str(ip)] = {'count': count, 'blocked_until': blocked_until}
        logger.info(f'已从持久化存储恢复 {len(_auth_failures)} 条认证失败记录')
    except Exception as e:
        logger.warning(f'加载持久化认证失败记录出错: {e}')


def _persist_failures() -> None:
    """将当前认证失败状态写回 SystemConfig，仅保留仍在封禁中的条目以控制体积"""
    try:
        from ..models import db
        from ..models.schemas import SystemConfig

        now = time.time()
        snapshot = {
            ip: {'count': int(state.get('count', 0)), 'blocked_until': float(state.get('blocked_until', 0))}
            for ip, state in _auth_failures.items()
            if float(state.get('blocked_until', 0)) > now
        }
        # 体积保护：最多持久化 1000 条
        if len(snapshot) > 1000:
            sorted_items = sorted(snapshot.items(), key=lambda kv: kv[1]['blocked_until'], reverse=True)[:1000]
            snapshot = dict(sorted_items)

        SystemConfig.set_value(_PERSIST_KEY, json.dumps(snapshot), description='Admin auth failure state')
        db.session.commit()
    except Exception as e:
        logger.warning(f'持久化认证失败记录出错: {e}')


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

        # 首次进入时加载持久化的封禁状态（启动后只触发一次）
        if not _persist_loaded:
            _load_persisted_failures()

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
                # 触发封禁时立即持久化，避免重启清零
                _persist_failures()

            return APIResponse.error('需要管理员权限', 403)

        _auth_failures.pop(client_ip, None)
        # 成功后异步式持久化（同步即可，行为简单且不频繁）
        if not _auth_failures:
            try:
                from ..models import db
                from ..models.schemas import SystemConfig

                SystemConfig.set_value(_PERSIST_KEY, '{}', description='Admin auth failure state')
                db.session.commit()
            except Exception as e:
                logger.debug(f'清空持久化认证状态失败: {e}')
        return f(*args, **kwargs)

    return wrapped
