"""
自定义异常体系 — 统一的三层异常处理

层次结构:
  BookRankException (基类)
    ├── ExternalAPIError        # 外部 API 调用失败 (NYT, Google Books 等)
    ├── DataNotFoundError       # 数据不存在
    ├── ServiceUnavailableError # 服务未初始化/不可用
    ├── DatabaseError           # 数据库操作失败
    ├── TranslationError        # 翻译服务失败
    ├── APIRateLimitException   # 速率限制
    ├── CacheMissException      # 缓存未命中
    ├── APIException            # API 调用通用异常
    ├── ValidationException     # 输入验证失败
    └── SecurityException       # 安全相关异常
"""

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from .error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


# ==================== 异常类定义 ====================


class BookRankException(Exception):
    """基础异常类"""

    def __init__(self, message: str = 'An error occurred', *, log_level: str = 'error', details: dict | None = None):
        self.message = message
        self.log_level = log_level
        self.details = details or {}
        super().__init__(message)

    def log(self) -> None:
        """按配置的级别记录日志"""
        log_func = getattr(logger, self.log_level, logger.error)
        log_func(f'[{self.__class__.__name__}] {self.message}', exc_info=True)


class ExternalAPIError(BookRankException):
    """外部 API 调用失败 (NYT, Google Books, 翻译服务 等)"""

    def __init__(
        self,
        message: str = 'External API call failed',
        *,
        api_name: str = 'unknown',
        status_code: int = 500,
        details: dict | None = None,
    ):
        self.api_name = api_name
        self.status_code = status_code
        super().__init__(f'[{api_name}] {message}', log_level='warning', details=details)


class DataNotFoundError(BookRankException):
    """请求的数据不存在"""

    def __init__(self, message: str = 'Data not found', *, resource_type: str = 'resource', resource_id: Any = None):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f'{resource_type} not found: {resource_id}' if resource_id else message, log_level='info')


class ServiceUnavailableError(BookRankException):
    """服务未初始化或不可用"""

    def __init__(self, message: str = 'Service unavailable', *, service_name: str = 'unknown'):
        self.service_name = service_name
        super().__init__(f"Service '{service_name}' is not available", log_level='error')


class DatabaseError(BookRankException):
    """数据库操作失败"""

    def __init__(self, message: str = 'Database operation failed', *, operation: str = 'unknown'):
        self.operation = operation
        super().__init__(f'Database {operation} failed: {message}', log_level='error')


class TranslationError(BookRankException):
    """翻译服务失败"""

    def __init__(self, message: str = 'Translation failed', *, text_preview: str = '', target_lang: str = 'zh'):
        self.text_preview = text_preview[:50]
        self.target_lang = target_lang
        super().__init__(f"Translation to {target_lang} failed for: '{self.text_preview}...'", log_level='warning')


class APIRateLimitException(BookRankException):
    """API限流异常"""

    def __init__(self, message: str = 'API rate limit exceeded', *, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, log_level='warning')


class CacheMissException(BookRankException):
    """缓存未命中异常"""

    def __init__(self, message: str = 'Cache miss'):
        super().__init__(message, log_level='debug')


class APIException(BookRankException):
    """API调用通用异常"""

    def __init__(self, message: str = 'API call failed', *, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


class ValidationException(BookRankException):
    """数据验证异常"""

    def __init__(self, message: str = 'Validation failed', *, field: str = '', reason: str = ''):
        self.field = field
        self.reason = reason
        detail = f"field='{field}': {reason}" if field else reason
        super().__init__(f'Validation error: {detail}' if detail else message, log_level='info')


class SecurityException(BookRankException):
    """安全相关异常"""

    def __init__(self, message: str = 'Security violation'):
        super().__init__(message, log_level='warning')


# ==================== 工具函数 ====================

F = TypeVar('F', bound=Callable)


def safe_call(fallback: Any = None, log_level: str = 'warning'):
    """
    装饰器：安全调用函数，异常时返回 fallback 值

    用法:
        @safe_call(fallback=[], log_level="warning")
        def get_books():
            ...

    Args:
        fallback: 异常时的返回值
        log_level: 日志级别
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BookRankException as e:
                e.log()
                return fallback
            except Exception as e:
                log_error(ErrorCategory.UNKNOWN, f'[{func.__name__}] Unexpected: {e}', exc_info=True)
                return fallback

        return wrapper  # type: ignore

    return decorator


def safe_service_call(service_name: str, operation: str, fallback: Any = None):
    """
    安全调用服务方法，统一处理三种异常场景：
    1. 服务未初始化 → log error, return fallback
    2. 服务调用抛异常 → log warning, return fallback
    3. 成功 → return result

    用法:
        books = safe_service_call("book_service", "get_books", fallback=[])
    """
    from flask import current_app

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                service = current_app.extensions.get(service_name)
                if not service:
                    logger.error(f"Service '{service_name}' not initialized, cannot {operation}")
                    return fallback
                return func(service, *args, **kwargs)
            except BookRankException as e:
                e.log()
                return fallback
            except Exception as e:
                log_error(ErrorCategory.UNKNOWN, f'[{service_name}.{operation}] Failed: {e}', exc_info=True, level='warning')
                return fallback

        return wrapper

    return decorator
