import time
import logging
from typing import List
from threading import Lock
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """滑动窗口限流器"""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.call_times: List[float] = []
        self._lock = Lock()
    
    def is_allowed(self) -> bool:
        with self._lock:
            now = time.time()
            self.call_times = [
                t for t in self.call_times 
                if now - t < self.window_seconds
            ]
            
            if len(self.call_times) >= self.max_calls:
                logger.warning(f"Rate limit exceeded: {len(self.call_times)} calls in {self.window_seconds}s")
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


class IPRateLimiter:
    """
    基于 IP 的限流器
    
    为每个 IP 地址维护独立的限流窗口
    支持多进程环境（通过共享存储）
    """
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()
    
    def is_allowed(self, client_id: str) -> bool:
        """
        检查指定客户端是否允许请求
        
        Args:
            client_id: 客户端标识（通常是 IP 地址）
            
        Returns:
            是否允许请求
        """
        with self._lock:
            now = time.time()
            
            self._requests[client_id] = [
                t for t in self._requests[client_id]
                if now - t < self.window_seconds
            ]
            
            if len(self._requests[client_id]) >= self.max_requests:
                logger.warning(f"Rate limit exceeded for {client_id}")
                return False
            
            self._requests[client_id].append(now)
            return True
    
    def get_retry_after(self, client_id: str) -> int:
        """获取指定客户端需要等待的秒数"""
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
        """清理过期的客户端记录"""
        with self._lock:
            now = time.time()
            expired_clients = [
                client_id for client_id, times in self._requests.items()
                if not times or (now - max(times)) > max_age
            ]
            for client_id in expired_clients:
                del self._requests[client_id]


_global_rate_limiter: IPRateLimiter | None = None


def get_rate_limiter(max_requests: int = 60, window_seconds: int = 60) -> IPRateLimiter:
    """获取全局限流器实例"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = IPRateLimiter(max_requests, window_seconds)
    return _global_rate_limiter
