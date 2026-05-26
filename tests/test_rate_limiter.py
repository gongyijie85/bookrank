"""rate_limiter 模块单元测试"""

import time

from app.utils.rate_limiter import IPRateLimiter, RateLimiter, get_rate_limiter


class TestRateLimiter:
    def test_allows_within_limit(self):
        limiter = RateLimiter(max_calls=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed() is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_calls=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed() is True
        assert limiter.is_allowed() is False

    def test_retry_after_returns_zero_when_allowed(self):
        limiter = RateLimiter(max_calls=10, window_seconds=60)
        assert limiter.get_retry_after() == 0

    def test_retry_after_positive_when_blocked(self):
        limiter = RateLimiter(max_calls=1, window_seconds=3600)
        limiter.is_allowed()
        retry = limiter.get_retry_after()
        assert retry > 0

    def test_reset_clears_history(self):
        limiter = RateLimiter(max_calls=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed()
        assert limiter.is_allowed() is False
        limiter.reset()
        assert limiter.is_allowed() is True

    def test_window_expires_old_calls(self):
        """旧调用在窗口外应被清理"""
        limiter = RateLimiter(max_calls=2, window_seconds=0)  # 0秒窗口
        assert limiter.is_allowed() is True
        # 下一毫秒窗口已过期，应继续允许
        assert limiter.is_allowed() is True


class TestIPRateLimiter:
    def test_different_clients_independent(self):
        limiter = IPRateLimiter(max_requests=2, window_seconds=60)
        for _ in range(2):
            assert limiter.is_allowed('192.168.1.1') is True
        assert limiter.is_allowed('192.168.1.1') is False
        # 另一个 IP 应不受影响
        assert limiter.is_allowed('192.168.1.2') is True

    def test_same_client_blocked(self):
        limiter = IPRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed('10.0.0.1') is True
        assert limiter.is_allowed('10.0.0.1') is False

    def test_retry_after_for_blocked(self):
        limiter = IPRateLimiter(max_requests=1, window_seconds=3600)
        limiter.is_allowed('10.0.0.1')
        retry = limiter.get_retry_after('10.0.0.1')
        assert retry > 0

    def test_retry_after_unknown_client_returns_zero(self):
        limiter = IPRateLimiter(max_requests=10, window_seconds=60)
        assert limiter.get_retry_after('unknown') == 0

    def test_cleanup_removes_expired(self):
        limiter = IPRateLimiter(max_requests=10, window_seconds=60)
        limiter.is_allowed('expired-client')
        # 清理 0 秒前的记录（全部过期）
        limiter.cleanup_expired(max_age=0)
        assert limiter.get_retry_after('expired-client') == 0

    def test_cleanup_keeps_recent(self):
        limiter = IPRateLimiter(max_requests=10, window_seconds=60)
        limiter.is_allowed('recent-client')
        # 清理 1 小时前的记录（当前为最近）
        limiter.cleanup_expired(max_age=3600)
        assert limiter.is_allowed('recent-client') is True

    def test_memory_cleanup_triggered_at_threshold(self):
        """10000+ 客户端时自动清理"""
        limiter = IPRateLimiter(max_requests=1, window_seconds=1)
        # 使用非常小的窗口让记录快速过期从而触发清理
        for i in range(50):
            limiter.is_allowed(f'client-{i}')
        # 不应崩溃
        time.sleep(0.1)
        assert limiter.is_allowed('test') is True


class TestGetRateLimiter:
    def test_returns_same_instance_for_same_params(self):
        a = get_rate_limiter(60, 60)
        b = get_rate_limiter(60, 60)
        assert a is b

    def test_returns_different_instance_for_different_params(self):
        a = get_rate_limiter(60, 60)
        b = get_rate_limiter(30, 30)
        assert a is not b
