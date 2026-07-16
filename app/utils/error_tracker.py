import logging
import os
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ErrorTracker:
    """错误追踪器：内存环形缓冲区 + 可选 Sentry 持久化"""

    _instance: 'ErrorTracker | None' = None
    _MAX_RECORDS = 500

    def __new__(cls) -> 'ErrorTracker':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._records: deque[dict[str, Any]] = deque(maxlen=cls._MAX_RECORDS)
            cls._instance._sentry = None
            cls._instance._init_sentry()
        return cls._instance

    def _init_sentry(self) -> None:
        """若配置了 SENTRY_DSN，初始化 Sentry SDK"""
        dsn = os.environ.get('SENTRY_DSN')
        if not dsn:
            return
        try:
            import sentry_sdk  # type: ignore[import-not-found]

            sentry_sdk.init(dsn=dsn)
            self._sentry = sentry_sdk
            logger.info('Sentry 错误追踪已启用')
        except Exception as exc:
            logger.warning('Sentry 初始化失败: %s', exc)

    def record(
        self,
        error_type: str,
        message: str,
        path: str = '',
        method: str = '',
        request_id: str = '',
    ) -> None:
        """记录一条错误（内存 + Sentry）"""
        record = {
            'timestamp': datetime.now(UTC).isoformat(),
            'error_type': error_type,
            'message': str(message)[:500],
            'path': str(path)[:200],
            'method': str(method)[:10],
            'request_id': str(request_id)[:32],
        }
        self._records.append(record)

        if self._sentry:
            try:
                self._sentry.set_tag('error_type', error_type)
                self._sentry.set_tag('path', path)
                self._sentry.set_tag('method', method)
                self._sentry.set_tag('request_id', request_id)
                self._sentry.capture_message(message, level='error')
            except Exception as exc:
                logger.warning('Sentry 上报失败: %s', exc)

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
