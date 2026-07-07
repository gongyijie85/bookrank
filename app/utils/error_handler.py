"""
统一错误处理模块

提供标准化的异常捕获、日志记录和降级策略，
替代项目中散落的 253 处裸 except Exception。

核心原语:
- safe_execute: 安全执行，失败时记录日志并返回 fallback
- ErrorCategory: 错误分类枚举
- log_error: 集中日志 + ErrorTracker 记录
"""

import functools
import logging
from collections.abc import Callable
from contextlib import contextmanager
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误分类，用于 ErrorTracker 统计"""

    API_CALL = 'api_call'
    DB_QUERY = 'db_query'
    TRANSLATION = 'translation'
    CACHE = 'cache'
    CRAWLER = 'crawler'
    EMAIL = 'email'
    AUTH = 'auth'
    UNKNOWN = 'unknown'


def log_error(
    category: ErrorCategory,
    message: str,
    exc_info: bool = False,
    level: str = 'error',
) -> None:
    """
    集中日志记录 + ErrorTracker 记录。

    Args:
        category: 错误分类
        message: 错误描述
        exc_info: 是否包含异常堆栈
        level: 日志级别 ('error' / 'warning')
    """
    request_id = ''
    path = ''
    method = ''
    try:
        from flask import request

        if request:
            request_id = getattr(request, 'request_id', '')
            path = request.path
            method = request.method
    except Exception:
        pass

    log_func = getattr(logger, level, logger.error)
    log_func('[%s] [request_id=%s] %s', category.value, request_id, message, exc_info=exc_info)

    try:
        from .error_tracker import error_tracker

        error_tracker.record(
            error_type=category.value,
            message=message,
            path=path,
            method=method,
            request_id=request_id,
        )
    except Exception:
        logger.warning('ErrorTracker 记录失败（可能尚未初始化）')


def safe_execute(
    operation_name: str = 'unknown',
    fallback: Any = None,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    reraise: bool = False,
    log_level: str = 'error',
) -> Callable:
    """
    装饰器：安全执行函数，失败时记录日志并降级返回 fallback。

    Usage:
        @safe_execute('fetch_books', fallback=[], category=ErrorCategory.API_CALL)
        def fetch_books():
            ...

    Args:
        operation_name: 操作名称（用于日志）
        fallback: 异常时的降级返回值
        category: 错误分类
        reraise: 是否重新抛出异常
        log_level: 日志级别
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_error(
                    category=category,
                    message=f'{operation_name} 失败: {e}',
                    exc_info=True,
                    level=log_level,
                )
                if reraise:
                    raise
                if callable(fallback):
                    try:
                        return fallback()
                    except Exception as fb_err:
                        log_error(
                            category=category,
                            message=f'{operation_name} fallback() 失败: {fb_err}',
                            level='error',
                        )
                return fallback

        return wrapper

    return decorator


@contextmanager
def safe_context(
    operation_name: str = 'unknown',
    fallback: Any = None,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    log_level: str = 'error',
):
    """
    上下文管理器：安全执行代码块，失败时记录日志。

    Usage:
        with safe_context('load_config', fallback={}, category=ErrorCategory.CACHE):
            config = load_from_file()
    """
    try:
        yield
    except Exception as e:
        log_error(
            category=category,
            message=f'{operation_name} 失败: {e}',
            exc_info=True,
            level=log_level,
        )
        # fallback 通过外部代码处理，context manager 不返回值
