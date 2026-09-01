"""限流器：进程内滑动窗口 + 可选 Redis 共享后端。

背景（安全审计 High #2，docs/audits/audit-security-2026-07-02.md）：
原实现基于进程内 dict + threading.Lock，Gunicorn 多 worker 下每个进程独立
计数，实际生效限额 = 配置限额 × worker 数，可被绕过。

本模块在**不改变公开 API** 的前提下叠加共享后端：
- 未配置 RATE_LIMIT_REDIS_URL（默认，含 Render 免费版）→ 行为与改造前完全一致（进程内）。
- 配置后且 Redis 可达 → 跨 worker 共享计数（Lua 脚本保证原子性）。
- Redis 未安装 / 地址不可达 / 调用异常 → **降级为进程内限流并告警**。

降级语义是「回到改造前的行为」而非「完全放行」：即使共享后端失效，
单进程限额仍然生效。生产仍需保持 WEB_CONCURRENCY=1（或接入 Redis），
见 SECURITY.md「速率限制与 Worker 数量（重要）」。
"""

import logging
import os
import time
import uuid
from collections import defaultdict
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

RATE_LIMIT_REDIS_URL_ENV = 'RATE_LIMIT_REDIS_URL'
_KEY_PREFIX = 'bookrank:ratelimit:'
_REDIS_FAILURE_COOLDOWN = 30.0
_REDIS_CONNECT_TIMEOUT = 1.0

# 滑动窗口（ZSET）+ 原子判定。跨 worker 并发下「检查再写入」必须原子，
# 否则多进程会同时通过判定，限额被放大。Lua 在 Redis 单线程内执行，天然原子。
#
# KEYS[1]=窗口 zset 键, KEYS[2]=键索引集合（供 reset 清理）
# ARGV[1]=now(浮点秒), ARGV[2]=window(秒), ARGV[3]=max_requests, ARGV[4]=member
# 返回 {allowed, count, oldest_score}
#
# 注意：Redis 会把 Lua 数字转为整数（截断小数），故 oldest_score 以字符串返回。
# tests/test_rate_limiter_redis.py 中的 Python 参考实现必须与此脚本保持同步。
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local index_key = KEYS[2]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]
local ttl_ms = math.ceil(window * 1000)

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count >= max_requests then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local oldest_score = now
  if oldest[2] then oldest_score = tonumber(oldest[2]) end
  redis.call('PEXPIRE', key, ttl_ms)
  return {0, count, tostring(oldest_score)}
end

redis.call('ZADD', key, now, member)
redis.call('SADD', index_key, key)
redis.call('PEXPIRE', index_key, ttl_ms)
redis.call('PEXPIRE', key, ttl_ms)
return {1, count + 1, '0'}
"""


class RateLimiter:
    """滑动窗口限流器（单进程，无 client 维度）"""

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.call_times: list[float] = []
        self._lock = Lock()

    def is_allowed(self) -> bool:
        with self._lock:
            now = time.time()
            self.call_times = [t for t in self.call_times if now - t < self.window_seconds]

            if len(self.call_times) >= self.max_calls:
                logger.warning(f'Rate limit exceeded: {len(self.call_times)} calls in {self.window_seconds}s')
                return False

            self.call_times.append(now)
            return True

    def get_retry_after(self) -> int:
        with self._lock:
            if len(self.call_times) < self.max_calls:
                return 0

            now = time.time()
            oldest_call = min(self.call_times)
            wait_time = int(self.window_seconds - (now - oldest_call)) + 1
            return max(0, wait_time)

    def reset(self):
        with self._lock:
            self.call_times.clear()


class RedisRateLimitBackend:
    """Redis 共享限流后端（ZSET 滑动窗口）。

    相同 (max_requests, window_seconds) 的限流器共享同一命名空间，
    因此不同 worker 进程会对同一 client_id 累计计数。
    """

    def __init__(self, client: Any, max_requests: int, window_seconds: int, key_prefix: str = _KEY_PREFIX):
        self._client = client
        self._namespace = f'{key_prefix}{max_requests}:{window_seconds}'
        self._index_key = f'{self._namespace}:__keys__'
        self._script = client.register_script(_SLIDING_WINDOW_LUA)

    def _key(self, client_id: str) -> str:
        return f'{self._namespace}:{client_id}'

    def is_allowed(self, client_id: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        member = f'{now:.6f}-{uuid.uuid4().hex}'
        result = self._script(
            keys=[self._key(client_id), self._index_key],
            args=[now, window_seconds, max_requests, member],
        )
        return int(result[0]) == 1, int(result[1])

    def retry_after(self, client_id: str, max_requests: int, window_seconds: int) -> int:
        key = self._key(client_id)
        now = time.time()
        self._client.zremrangebyscore(key, 0, now - window_seconds)

        if int(self._client.zcard(key) or 0) < max_requests:
            return 0

        items = self._client.zrange(key, 0, 0, withscores=True)
        if not items:
            return 0

        oldest = float(items[0][1])
        return max(0, int(window_seconds - (now - oldest)) + 1)

    def reset(self) -> None:
        members = list(self._client.smembers(self._index_key) or [])
        if members:
            self._client.delete(*members)
        self._client.delete(self._index_key)


# 模块级 Redis 单例：避免每请求重连；失败后进入冷却期，避免每请求重试放大故障。
_redis_client: Any = None
_redis_unavailable_until: float = 0.0


def _get_redis_url() -> str:
    """取 Redis 地址：Flask 配置优先，其次环境变量；均未配置返回 ''（走进程内限流）。"""
    try:
        from flask import current_app

        url = current_app.config.get(RATE_LIMIT_REDIS_URL_ENV)
        if url:
            return str(url)
    except Exception:  # 无应用上下文等情况
        pass
    return os.environ.get(RATE_LIMIT_REDIS_URL_ENV, '') or ''


def _get_redis_client() -> Any | None:
    """返回可用的 Redis 客户端；未配置/不可达时返回 None（调用方降级为进程内限流）。"""
    global _redis_client, _redis_unavailable_until

    if not _get_redis_url():
        return None
    if _redis_client is not None:
        return _redis_client

    now = time.time()
    if now < _redis_unavailable_until:
        return None

    try:
        import redis  # 可选依赖：仅启用共享限流时需要

        client = redis.Redis.from_url(
            _get_redis_url(),
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
            socket_timeout=_REDIS_CONNECT_TIMEOUT,
            decode_responses=True,
        )
        client.ping()
        _redis_client = client
        logger.info('限流器已启用 Redis 共享后端（跨 worker 计数生效）')
        return client
    except Exception as exc:
        _redis_unavailable_until = now + _REDIS_FAILURE_COOLDOWN
        logger.warning('限流器 Redis 后端不可用，降级为进程内限流: %s', exc)
        return None


def _resolve_backend(max_requests: int, window_seconds: int) -> RedisRateLimitBackend | None:
    """按当前配置解析共享后端；未启用时返回 None。"""
    client = _get_redis_client()
    if client is None:
        return None
    return RedisRateLimitBackend(client, max_requests, window_seconds)


def _reset_shared_state() -> None:
    """清空模块级 Redis 单例与冷却计时（仅供测试使用）。"""
    global _redis_client, _redis_unavailable_until
    _redis_client = None
    _redis_unavailable_until = 0.0


class IPRateLimiter:
    """
    基于 IP 的限流器

    为每个 IP 地址维护独立的限流窗口。
    默认进程内计数；配置 RATE_LIMIT_REDIS_URL 且 Redis 可达时，
    自动切换为跨进程（多 worker）共享计数（安全审计 High #2 根因修复）。
    共享后端异常时降级为进程内限流，不阻断请求。
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60, backend: Any | None = None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        self._last_cleanup: float = 0.0
        # 后端为鸭子类型（is_allowed/retry_after/reset），测试可注入替身，故标注 Any
        self._backend: Any = backend if backend is not None else _resolve_backend(max_requests, window_seconds)
        self._backend_down_until: float = 0.0

    def _shared_active(self) -> bool:
        return self._backend is not None and time.time() >= self._backend_down_until

    def is_allowed(self, client_id: str) -> bool:
        """
        检查指定客户端是否允许请求

        Args:
            client_id: 客户端标识（通常是 IP 地址）

        Returns:
            是否允许请求
        """
        if self._shared_active():
            try:
                allowed, _count = self._backend.is_allowed(client_id, self.max_requests, self.window_seconds)
                if not allowed:
                    logger.warning(f'Rate limit exceeded for {client_id} (shared backend)')
                return bool(allowed)
            except Exception as exc:
                self._backend_down_until = time.time() + _REDIS_FAILURE_COOLDOWN
                logger.warning('限流器共享后端异常，本窗口降级为进程内限流: %s', exc)

        with self._lock:
            now = time.time()

            self._requests[client_id] = [t for t in self._requests[client_id] if now - t < self.window_seconds]

            if len(self._requests[client_id]) >= self.max_requests:
                logger.warning(f'Rate limit exceeded for {client_id}')
                return False

            self._requests[client_id].append(now)

            # 每 60 秒清理一次过期条目，避免 O(n*m) 的实时清理
            if now - self._last_cleanup > 60:
                self._last_cleanup = now
                expired = [k for k, v in self._requests.items() if not v or (now - max(v)) > self.window_seconds * 2]
                for k in expired:
                    del self._requests[k]

            return True

    def get_retry_after(self, client_id: str) -> int:
        """获取指定客户端需要等待的秒数"""
        if self._shared_active():
            try:
                return int(self._backend.retry_after(client_id, self.max_requests, self.window_seconds))
            except Exception as exc:
                self._backend_down_until = time.time() + _REDIS_FAILURE_COOLDOWN
                logger.warning('限流器共享后端异常（retry_after），降级为进程内限流: %s', exc)

        with self._lock:
            if client_id not in self._requests:
                return 0

            requests = self._requests[client_id]
            if len(requests) < self.max_requests:
                return 0

            now = time.time()
            oldest = min(requests)
            wait_time = int(self.window_seconds - (now - oldest)) + 1
            return max(0, wait_time)

    def cleanup_expired(self, max_age: int = 3600):
        """清理过期的客户端记录

        仅作用于进程内记录；Redis 后端由键 TTL 自动过期，无需清理。
        """
        with self._lock:
            now = time.time()
            expired_clients = [
                client_id for client_id, times in self._requests.items() if not times or (now - max(times)) > max_age
            ]
            for client_id in expired_clients:
                del self._requests[client_id]

    def reset(self):
        """清空所有客户端的调用历史（主要用于测试隔离）"""
        if self._backend is not None:
            try:
                self._backend.reset()
            except Exception as exc:
                logger.warning('限流器共享后端 reset 失败（已忽略）: %s', exc)

        with self._lock:
            self._requests.clear()


_global_rate_limiters: dict[str, IPRateLimiter] = {}


def get_rate_limiter(max_requests: int = 60, window_seconds: int = 60) -> IPRateLimiter:
    """获取限流器实例（按参数组合缓存）"""
    cache_key = f'{max_requests}_{window_seconds}'
    if cache_key not in _global_rate_limiters:
        _global_rate_limiters[cache_key] = IPRateLimiter(max_requests, window_seconds)
    return _global_rate_limiters[cache_key]
