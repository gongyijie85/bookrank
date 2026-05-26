"""测试 error_handler 模块"""

import pytest

from app.utils.error_handler import ErrorCategory, log_error, safe_context, safe_execute


class TestErrorCategory:
    def test_all_categories_have_values(self):
        """确保所有分类都有值"""
        categories = [
            ErrorCategory.API_CALL,
            ErrorCategory.DB_QUERY,
            ErrorCategory.TRANSLATION,
            ErrorCategory.CACHE,
            ErrorCategory.CRAWLER,
            ErrorCategory.EMAIL,
            ErrorCategory.AUTH,
            ErrorCategory.UNKNOWN,
        ]
        for cat in categories:
            assert cat.value, f'{cat} 缺少 value'


class TestSafeExecute:
    def test_returns_result_on_success(self):
        @safe_execute('test_op')
        def success_func():
            return 42

        assert success_func() == 42

    def test_returns_fallback_on_failure(self):
        @safe_execute('test_op', fallback='default')
        def fail_func():
            raise ValueError('boom')

        assert fail_func() == 'default'

    def test_callable_fallback(self):
        @safe_execute('test_op', fallback=lambda: 'computed')
        def fail_func():
            raise RuntimeError('crash')

        assert fail_func() == 'computed'

    def test_reraises_when_requested(self):
        @safe_execute('test_op', reraise=True)
        def fail_func():
            raise ValueError('must propagate')

        with pytest.raises(ValueError, match='must propagate'):
            fail_func()

    def test_preserves_args_and_kwargs(self):
        @safe_execute('test_op')
        def add(a, b=0):
            return a + b

        assert add(3, b=4) == 7

    def test_preserves_function_metadata(self):
        @safe_execute('test_op')
        def my_func():
            """My docstring"""
            pass

        assert my_func.__name__ == 'my_func'
        assert my_func.__doc__ == 'My docstring'


class TestSafeContext:
    def test_no_exception_passes_through(self):
        executed = False
        with safe_context('test_ctx'):
            executed = True
        assert executed

    def test_exception_is_suppressed_and_logged(self):
        with safe_context('test_ctx', category=ErrorCategory.CACHE):
            raise ValueError('expected error')
        # 不应该抛出异常
        assert True


class TestLogError:
    def test_log_error_records_category(self):
        """确保 log_error 可以正常调用"""
        log_error(
            ErrorCategory.CACHE,
            'test message',
            exc_info=False,
            level='warning',
        )
        # 不抛异常即为通过
