from collections import deque
from datetime import UTC, datetime
from typing import Any


class ErrorTracker:
    """内存错误追踪器（环形缓冲区，Render免费版无需外部服务）"""

    _instance: 'ErrorTracker | None' = None
    _MAX_RECORDS = 500

    def __new__(cls) -> 'ErrorTracker':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._records: deque[dict[str, Any]] = deque(maxlen=cls._MAX_RECORDS)
        return cls._instance

    def record(self, error_type: str, message: str, path: str = '', method: str = '') -> None:
        """记录一条错误"""
        self._records.append(
            {
                'timestamp': datetime.now(UTC).isoformat(),
                'error_type': error_type,
                'message': str(message)[:500],
                'path': str(path)[:200],
                'method': str(method)[:10],
            }
        )

    def get_recent(self, limit: int = 50, error_type: str | None = None) -> list[dict[str, Any]]:
        """获取最近错误记录（支持按类型筛选）"""
        records = list(self._records)
        if error_type:
            records = [r for r in records if r['error_type'] == error_type]
        return records[-limit:][::-1]

    def get_stats(self) -> dict[str, int]:
        """获取错误统计"""
        stats: dict[str, int] = {}
        for record in self._records:
            error_type = record['error_type']
            stats[error_type] = stats.get(error_type, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def clear(self) -> None:
        """清空错误记录"""
        self._records.clear()


error_tracker = ErrorTracker()
