"""共享限流后端（Redis）测试 —— 安全审计 High #2 根因修复。

约束：CI 无 Redis 服务，故用内存版 FakeRedis 验证后端接线与判定语义；
Lua 脚本的原子性本身由 Redis 单线程执行保证，这里用等价的 Python 参考
实现（_lua_sliding_window）驱动，二者必须保持同步。

默认（未配置 RATE_LIMIT_REDIS_URL）仍走进程内限流，行为与改造前一致，
由 tests/test_rate_limiter.py 覆盖。
"""

from __future__ import annotations

import time
from collections import defaultdict

import pytest

from app.utils.rate_limiter import (
    _KEY_PREFIX,
    IPRateLimiter,
    RedisRateLimitBackend,
    _reset_shared_state,
    _resolve_backend,
)


class FakeRedis:
    """内存版 Redis 子集（zset / set / ttl），仅供测试，无网络依赖。"""

    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = defaultdict(dict)
        self.sets: dict[str, set[str]] = defaultdict(set)
        self.expiries: dict[str, int] = {}

    def register_script(self, script: str):
        def run(keys=None, args=None):
            now = float(args[0])
            window = float(args[1])
            max_requests = int(args[2])
            member = args[3]
            return _lua_sliding_window(self, keys[0], keys[1], now, window, max_requests, member)

        return run

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.zsets[key].update(mapping)
        return len(mapping)

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        bucket = self.zsets.setdefault(key, {})
        stale = [m for m, score in bucket.items() if min_score <= score <= max_score]
        for member in stale:
            del bucket[member]
        return len(stale)

    def zrange(self, key: str, start: int, end: int, withscores: bool = False):
        ordered = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        if withscores:
            return [(member, score) for member, score in ordered]
        return [member for member, _ in ordered]

    def sadd(self, key: str, *members: str) -> int:
        self.sets[key].update(members)
        return len(members)

    def smembers(self, key: str) -> set[str]:
        return self.sets.get(key, set())

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.zsets.pop(key, None) is not None:
                removed += 1
            if self.sets.pop(key, None) is not None:
                removed += 1
            self.expiries.pop(key, None)
        return removed

    def pexpire(self, key: str, ttl_ms: int) -> None:
        self.expiries[key] = ttl_ms


def _lua_sliding_window(
    store: FakeRedis,
    key: str,
    index_key: str,
    now: float,
    window: float,
    max_requests: int,
    member: str,
):
    """app/utils/rate_limiter.py 中 _SLIDING_WINDOW_LUA 的等价实现（须同步）。"""
    ttl_ms = int(window * 1000)
    store.zremrangebyscore(key, 0, now - window)
    count = store.zcard(key)

    if count >= max_requests:
        items = store.zrange(key, 0, 0, withscores=True)
        oldest_score = float(items[0][1]) if items else now
        store.pexpire(key, ttl_ms)
        return [0, count, str(oldest_score)]

    store.zadd(key, {member: now})
    store.sadd(index_key, key)
    store.pexpire(index_key, ttl_ms)
    store.pexpire(key, ttl_ms)
    return [1, count + 1, '0']


class ExplodingBackend:
    """模拟 Redis 不可用：所有操作抛异常。"""

    def is_allowed(self, *args, **kwargs):
        raise RuntimeError('redis down')

    def retry_after(self, *args, **kwargs):
        raise RuntimeError('redis down')

    def reset(self, *args, **kwargs):
        raise RuntimeError('redis down')


def _limiter(fake: FakeRedis, max_requests: int = 3, window: int = 60) -> IPRateLimiter:
    return IPRateLimiter(max_requests, window, backend=RedisRateLimitBackend(fake, max_requests, window))


class TestSharedBackend:
    def test_counts_are_shared_across_instances(self):
        """核心回归：多 worker（此处用多实例模拟）必须共享同一计数。

        进程内实现下 a 只会看到自己的 2 次调用，第 4 次仍放行；
        共享后端下第 4 次必须被拒——这正是 High #2 的绕过场景。
        """
        fake = FakeRedis()
        worker_a = _limiter(fake)
        worker_b = _limiter(fake)

        assert worker_a.is_allowed('1.2.3.4') is True
        assert worker_a.is_allowed('1.2.3.4') is True
        assert worker_b.is_allowed('1.2.3.4') is True
        assert worker_a.is_allowed('1.2.3.4') is False
        assert worker_b.is_allowed('1.2.3.4') is False

    def test_allows_within_limit(self):
        limiter = _limiter(FakeRedis(), max_requests=2)
        assert limiter.is_allowed('1.2.3.4') is True
        assert limiter.is_allowed('1.2.3.4') is True
        assert limiter.is_allowed('1.2.3.4') is False

    def test_different_clients_are_isolated(self):
        limiter = _limiter(FakeRedis(), max_requests=1)
        assert limiter.is_allowed('1.1.1.1') is True
        assert limiter.is_allowed('1.1.1.1') is False
        assert limiter.is_allowed('2.2.2.2') is True

    def test_retry_after_when_exceeded(self):
        limiter = _limiter(FakeRedis(), max_requests=1, window=60)
        assert limiter.get_retry_after('1.2.3.4') == 0  # 未超限
        limiter.is_allowed('1.2.3.4')
        assert limiter.get_retry_after('1.2.3.4') > 0

    def test_window_expiry_allows_again(self):
        fake = FakeRedis()
        limiter = _limiter(fake, max_requests=1, window=60)
        assert limiter.is_allowed('1.2.3.4') is True

        key = limiter._backend._key('1.2.3.4')
        for member in list(fake.zsets[key]):
            fake.zsets[key][member] = time.time() - 120  # 滑出 60s 窗口

        assert limiter.is_allowed('1.2.3.4') is True

    def test_reset_clears_shared_state(self):
        fake = FakeRedis()
        limiter = _limiter(fake, max_requests=1)
        assert limiter.is_allowed('9.9.9.9') is True
        assert limiter.is_allowed('9.9.9.9') is False

        key = limiter._backend._key('9.9.9.9')
        index_key = limiter._backend._index_key
        assert fake.zcard(key) == 1  # 重置前确有共享记录

        limiter.reset()

        assert fake.zcard(key) == 0  # 共享键已被删除
        assert fake.smembers(index_key) == set()  # 键索引一并清理
        assert limiter.is_allowed('9.9.9.9') is True  # 重置后可再次放行

    def test_key_namespacing_and_index(self):
        fake = FakeRedis()
        limiter = _limiter(fake, max_requests=5, window=30)
        limiter.is_allowed('7.7.7.7')

        key = limiter._backend._key('7.7.7.7')
        assert key.startswith(_KEY_PREFIX)
        assert key.endswith(':7.7.7.7')
        assert '5:30' in key  # 命名空间含 (max_requests, window)，保证同策略共享
        assert key in fake.smembers(limiter._backend._index_key)


class TestGracefulDegradation:
    def test_falls_back_to_memory_when_backend_raises(self):
        """Redis 异常时降级为进程内限流：不抛异常，且单进程限额仍生效。"""
        limiter = IPRateLimiter(2, 60, backend=ExplodingBackend())

        assert limiter.is_allowed('1.2.3.4') is True
        assert limiter.is_allowed('1.2.3.4') is True
        assert limiter.is_allowed('1.2.3.4') is False  # 进程内限流兜底
        assert limiter.get_retry_after('1.2.3.4') > 0

    def test_reset_survives_backend_failure(self):
        limiter = IPRateLimiter(1, 60, backend=ExplodingBackend())
        assert limiter.is_allowed('1.2.3.4') is True
        limiter.reset()  # 不得抛出
        assert limiter.is_allowed('1.2.3.4') is True


class TestDefaultConfiguration:
    def test_no_backend_when_redis_url_unset(self, monkeypatch):
        """未配置 RATE_LIMIT_REDIS_URL → 无共享后端，行为与改造前一致。"""
        monkeypatch.delenv('RATE_LIMIT_REDIS_URL', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'testing')
        _reset_shared_state()

        limiter = IPRateLimiter(2, 60)

        assert limiter._backend is None
        assert _resolve_backend(2, 60) is None

    @pytest.mark.parametrize('client_id', ['1.2.3.4', 'unknown'])
    def test_memory_path_unchanged(self, monkeypatch, client_id):
        monkeypatch.delenv('RATE_LIMIT_REDIS_URL', raising=False)
        _reset_shared_state()

        limiter = IPRateLimiter(1, 60)

        assert limiter.is_allowed(client_id) is True
        assert limiter.is_allowed(client_id) is False
        limiter.reset()
        assert limiter.is_allowed(client_id) is True
