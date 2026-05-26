"""api_helpers 模块单元测试"""

import pytest
from flask import Flask

from app.utils.api_helpers import (
    APIResponse,
    PublicAPIResponse,
    clean_translation_text,
    handle_api_errors,
    validate_isbn,
    validate_pagination,
)
from app.utils.exceptions import (
    APIRateLimitException,
    DataNotFoundError,
    ExternalAPIError,
    ValidationException,
)


class TestValidateIsbn:
    def test_empty_returns_false(self):
        assert validate_isbn('') is False
        assert validate_isbn(None) is False

    def test_valid_isbn10(self):
        assert validate_isbn('0306406152') is True
        assert validate_isbn('080442957X') is True
        assert validate_isbn('080442957x') is True

    def test_valid_isbn13(self):
        assert validate_isbn('9783161484100') is True
        assert validate_isbn('9780123456789') is True

    def test_isbn_with_hyphens(self):
        assert validate_isbn('978-3-16-148410-0') is True
        assert validate_isbn('0-306-40615-2') is True

    def test_invalid_format(self):
        assert validate_isbn('123456789') is False  # too short
        assert validate_isbn('abcdefghij') is False  # letters
        assert validate_isbn('12345678901234') is False  # too long


class TestValidatePagination:
    def test_defaults(self):
        page, limit = validate_pagination(1, 20)
        assert page == 1
        assert limit == 20

    def test_clamps_negative(self):
        page, limit = validate_pagination(-5, -10)
        assert page == 1
        assert limit == 1

    def test_clamps_too_large(self):
        page, limit = validate_pagination(99999, 200)
        assert page == 10000
        assert limit == 50

    def test_respects_max_limit(self):
        page, limit = validate_pagination(1, 20, max_limit=100)
        assert page == 1
        assert limit == 20
        page, limit = validate_pagination(1, 200, max_limit=100)
        assert limit == 100


class TestAPIResponse:
    @pytest.fixture
    def app(self):
        app = Flask(__name__)
        return app

    def test_success_format(self, app):
        with app.test_request_context():
            response, status = APIResponse.success(data={'key': 'val'})
            assert status == 200
            assert response.json['success'] is True
            assert response.json['data'] == {'key': 'val'}

    def test_success_defaults(self, app):
        with app.test_request_context():
            response, status = APIResponse.success()
            assert status == 200
            assert response.json['data'] is None

    def test_error_format(self, app):
        with app.test_request_context():
            response, status = APIResponse.error('Bad request', 400)
            assert status == 400
            assert response.json['success'] is False
            assert response.json['message'] == 'Bad request'

    def test_error_with_details(self, app):
        with app.test_request_context():
            response, status = APIResponse.error('Invalid', 422, errors={'field': 'missing'})
            assert status == 422
            assert response.json['errors'] == {'field': 'missing'}


class TestPublicAPIResponse:
    @pytest.fixture
    def app(self):
        app = Flask(__name__)
        return app

    def test_success_has_timestamp(self, app):
        with app.test_request_context():
            response, status = PublicAPIResponse.success(data={'x': 1})
            assert status == 200
            assert 'timestamp' in response.json

    def test_error_has_timestamp(self, app):
        with app.test_request_context():
            response, status = PublicAPIResponse.error('Gone', 410)
            assert status == 410
            assert 'timestamp' in response.json


class TestHandleApiErrors:
    @pytest.fixture
    def app(self):
        return Flask(__name__)

    def test_passes_through_success(self):
        @handle_api_errors
        def ok_func():
            return 'hello'

        assert ok_func() == 'hello'

    def test_catches_validation_exception(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise ValidationException('missing field')

            _response, status = bad_func()
            assert status == 400

    def test_catches_data_not_found(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise DataNotFoundError('no such book')

            _response, status = bad_func()
            assert status == 404

    def test_catches_rate_limit(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise APIRateLimitException('too fast')

            _response, status = bad_func()
            assert status == 429

    def test_catches_external_api_error(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise ExternalAPIError('down')

            _response, status = bad_func()
            assert status == 503

    def test_catches_value_error(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise ValueError('bad input')

            _response, status = bad_func()
            assert status == 400

    def test_catches_key_error(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise KeyError('missing_key')

            _response, status = bad_func()
            assert status == 400

    def test_catches_timeout_error(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise TimeoutError('timed out')

            _response, status = bad_func()
            assert status == 504

    def test_catches_generic_exception(self, app):
        with app.app_context():

            @handle_api_errors
            def bad_func():
                raise RuntimeError('unknown crash')

            _response, status = bad_func()
            assert status == 500


class TestCleanTranslationText:
    def test_passes_clean_text(self):
        assert clean_translation_text('hello world') == 'hello world'

    def test_passes_empty_and_none(self):
        assert clean_translation_text('') == ''
        assert clean_translation_text(None) is None

    def test_removes_markdown_bold(self):
        assert '**bold**' not in clean_translation_text('This is **bold** text')

    def test_removes_markdown_underscore(self):
        result = clean_translation_text('__italic__ here')
        assert '__italic__' not in result or result == 'italic here'

    def test_truncates_at_field_label(self):
        result = clean_translation_text('我的书 作者：张三', field_type='title')
        assert '作者' not in result or result.endswith('我的书')

    def test_chinese_text_preserved(self):
        assert clean_translation_text('你好世界') == '你好世界'
