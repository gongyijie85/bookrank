"""自定义异常体系测试"""

from unittest.mock import MagicMock, patch

from app.utils.exceptions import (
    APIException,
    APIRateLimitException,
    BookRankException,
    CacheMissException,
    DatabaseError,
    DataNotFoundError,
    ExternalAPIError,
    SecurityException,
    ServiceUnavailableError,
    TranslationError,
    ValidationException,
    safe_call,
    safe_service_call,
)


class TestBookRankException:
    """测试基础异常类"""

    def test_default_message(self):
        exc = BookRankException()
        assert str(exc) == 'An error occurred'
        assert exc.log_level == 'error'
        assert exc.details == {}

    def test_custom_message(self):
        exc = BookRankException('Custom error')
        assert str(exc) == 'Custom error'

    def test_custom_log_level(self):
        exc = BookRankException('msg', log_level='warning')
        assert exc.log_level == 'warning'

    def test_custom_details(self):
        exc = BookRankException('msg', details={'key': 'value'})
        assert exc.details == {'key': 'value'}

    @patch('app.utils.exceptions.logger')
    def test_log_method(self, mock_logger):
        exc = BookRankException('test', log_level='warning')
        exc.log()
        mock_logger.warning.assert_called_once()


class TestExternalAPIError:
    """测试外部API异常"""

    def test_default(self):
        exc = ExternalAPIError()
        assert 'unknown' in str(exc)
        assert exc.api_name == 'unknown'
        assert exc.status_code == 500

    def test_custom(self):
        exc = ExternalAPIError('timeout', api_name='NYT', status_code=503)
        assert '[NYT]' in str(exc)
        assert exc.api_name == 'NYT'
        assert exc.status_code == 503
        assert exc.log_level == 'warning'


class TestDataNotFoundError:
    """测试数据不存在异常"""

    def test_default(self):
        exc = DataNotFoundError()
        assert str(exc) == 'Data not found'
        assert exc.resource_type == 'resource'

    def test_with_resource_id(self):
        exc = DataNotFoundError(resource_type='Book', resource_id=42)
        assert 'Book' in str(exc)
        assert '42' in str(exc)

    def test_without_resource_id(self):
        exc = DataNotFoundError('Custom not found message')
        assert str(exc) == 'Custom not found message'


class TestServiceUnavailableError:
    """测试服务不可用异常"""

    def test_default(self):
        exc = ServiceUnavailableError()
        assert 'unknown' in str(exc)

    def test_custom_service(self):
        exc = ServiceUnavailableError(service_name='Redis')
        assert 'Redis' in str(exc)
        assert exc.log_level == 'error'


class TestDatabaseError:
    """测试数据库异常"""

    def test_default(self):
        exc = DatabaseError()
        assert 'unknown' in str(exc)

    def test_custom_operation(self):
        exc = DatabaseError('connection lost', operation='insert')
        assert 'insert' in str(exc)
        assert exc.operation == 'insert'


class TestTranslationError:
    """测试翻译异常"""

    def test_default(self):
        exc = TranslationError()
        assert 'zh' in str(exc)

    def test_custom(self):
        exc = TranslationError(text_preview='A' * 100, target_lang='en')
        assert 'en' in str(exc)
        assert len(exc.text_preview) == 50

    def test_short_preview(self):
        exc = TranslationError(text_preview='Hello')
        assert exc.text_preview == 'Hello'


class TestAPIRateLimitException:
    """测试限流异常"""

    def test_default(self):
        exc = APIRateLimitException()
        assert exc.retry_after == 60
        assert exc.log_level == 'warning'

    def test_custom_retry(self):
        exc = APIRateLimitException('slow down', retry_after=120)
        assert exc.retry_after == 120


class TestCacheMissException:
    """测试缓存未命中异常"""

    def test_default(self):
        exc = CacheMissException()
        assert exc.log_level == 'debug'

    def test_custom_message(self):
        exc = CacheMissException('nyt:hardcover-fiction')
        assert 'nyt' in str(exc)


class TestAPIException:
    """测试API通用异常"""

    def test_default(self):
        exc = APIException()
        assert exc.status_code == 500

    def test_custom_status(self):
        exc = APIException('bad request', status_code=400)
        assert exc.status_code == 400


class TestValidationException:
    """测试验证异常"""

    def test_default(self):
        exc = ValidationException()
        assert 'Validation' in str(exc)

    def test_with_field_and_reason(self):
        exc = ValidationException(field='email', reason='invalid format')
        assert 'email' in str(exc)
        assert 'invalid format' in str(exc)

    def test_with_reason_only(self):
        exc = ValidationException(reason='too short')
        assert 'too short' in str(exc)


class TestSecurityException:
    """测试安全异常"""

    def test_default(self):
        exc = SecurityException()
        assert exc.log_level == 'warning'

    def test_custom_message(self):
        exc = SecurityException('CSRF token mismatch')
        assert 'CSRF' in str(exc)


class TestSafeCall:
    """测试 safe_call 装饰器"""

    def test_normal_execution(self):
        @safe_call(fallback=None)
        def get_data():
            return [1, 2, 3]

        assert get_data() == [1, 2, 3]

    def test_bookrank_exception_returns_fallback(self):
        @safe_call(fallback=[])
        def get_data():
            raise ExternalAPIError('NYT down', api_name='NYT')

        assert get_data() == []

    def test_generic_exception_returns_fallback(self):
        @safe_call(fallback=0)
        def get_data():
            raise ValueError('unexpected')

        assert get_data() == 0

    def test_fallback_none(self):
        @safe_call()
        def get_data():
            raise RuntimeError('fail')

        assert get_data() is None

    def test_preserves_function_name(self):
        @safe_call(fallback=None)
        def my_function():
            pass

        assert my_function.__name__ == 'my_function'


class TestSafeServiceCall:
    """测试 safe_service_call 装饰器"""

    def test_service_not_initialized(self, app):
        with app.app_context():
            app.extensions.pop('book_service', None)

            @safe_service_call('book_service', 'get_books', fallback=[])
            def get_books(service):
                return service.get_books()

            result = get_books()
            assert result == []

    def test_service_call_success(self, app):
        mock_service = MagicMock()
        mock_service.get_books.return_value = ['book1']

        with app.app_context():
            app.extensions['book_service'] = mock_service

            @safe_service_call('book_service', 'get_books', fallback=[])
            def get_books(service):
                return service.get_books()

            result = get_books()
            assert result == ['book1']

            del app.extensions['book_service']

    def test_service_call_exception(self, app):
        mock_service = MagicMock()
        mock_service.get_books.side_effect = ExternalAPIError('fail', api_name='NYT')

        with app.app_context():
            app.extensions['book_service'] = mock_service

            @safe_service_call('book_service', 'get_books', fallback=[])
            def get_books(service):
                return service.get_books()

            result = get_books()
            assert result == []

            del app.extensions['book_service']

    def test_service_generic_exception(self, app):
        mock_service = MagicMock()
        mock_service.get_books.side_effect = RuntimeError('unexpected')

        with app.app_context():
            app.extensions['book_service'] = mock_service

            @safe_service_call('book_service', 'get_books', fallback=[])
            def get_books(service):
                return service.get_books()

            result = get_books()
            assert result == []

            del app.extensions['book_service']
