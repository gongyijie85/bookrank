import time
import logging
from typing import List
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """滑动窗口限流器"""
    
    def __init__(self, max_calls: int, window_seconds: int):
        """
        初始化限流器
        
        Args:
            max_calls: 时间窗口内最大调用次数
            window_seconds: 时间窗口大小（秒）
        """
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.call_times: List[float] = []
        self._lock = Lock()
    
    def is_allowed(self) -> bool:
        """
        检查是否允许调用
        
        Returns:
            True if allowed, False otherwise
        """
        with self._lock:
            now = time.time()
            # 清理过期的调用记录
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
        """
        获取需要等待的秒数
        
        Returns:
            需要等待的秒数
        """
        with self._lock:
            if len(self.call_times) < self.max_calls:
                return 0
            
            now = time.time()
            oldest_call = min(self.call_times)
            wait_time = int(self.window_seconds - (now - oldest_call)) + 1
            return max(0, wait_time)
    
    def reset(self):
        """重置限流器"""
        with self._lock:
            self.call_times.clear()
