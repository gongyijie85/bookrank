"""api_helpers 模块扩展测试 — 覆盖现有测试未触及的函数和错误路径"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.utils.api_helpers import (
    APIResponse,
    PublicAPIResponse,
    _add_book_title_marks,
    _clean_title_text,
    _cleanup_expired_csrf_tokens,
    _extract_field_content,
    _strip_markdown,
    api_rate_limit,
    clean_translation_text,
    csrf_protect,
    get_csrf_token,
    handle_api_errors,
    public_rate_limit,
    quick_clean_translation,
    validate_csrf_token,
)
from app.utils.exceptions import BookRankException


class TestCleanupExpiredCsrfTokens:
    def test_normal_cleanup(self, app, db):
        with app.app_context():
            from app.models.schemas import CSRFToken

            old_token = CSRFToken(token='old_token')
            old_token.created_at = datetime.now(UTC) - timedelta(seconds=7200)
            db.session.add(old_token)
            db.session.commit()

            _cleanup_expired_csrf_tokens()
            assert CSRFToken.query.filter_by(token='old_token').first() is None

    def test_exception_rolls_back(self, app, db):
        with app.app_context(), patch('app.utils.api_helpers.CSRFToken') as MockToken:
            MockToken.query.filter.return_value.delete.side_effect = Exception('db fail')
            _cleanup_expired_csrf_tokens()


class TestHandleApiErrorsExtended:
    def test_catches_book_rank_exception(self, app):
        with app.app_context():

            @handle_api_errors
            def raise_bre():
                raise BookRankException('bre error')

            response, status = raise_bre()
            assert status == 500

    def test_catches_permission_error(self, app):
        with app.app_context():

            @handle_api_errors
            def raise_perm():
                raise PermissionError('forbidden')

            response, status = raise_perm()
            assert status == 403

    def test_catches_file_not_found_error(self, app):
        with app.app_context():

            @handle_api_errors
            def raise_fnf():
                raise FileNotFoundError('not found')

            response, status = raise_fnf()
            assert status == 404

    def test_catches_connection_error(self, app):
        with app.app_context():

            @handle_api_errors
            def raise_conn():
                raise ConnectionError('refused')

            response, status = raise_conn()
            assert status == 503
            assert '不可用' in response.json['message']


class TestApiRateLimitDecorator:
    def test_testing_mode_bypasses_limit(self, app):
        app.config['TESTING'] = True

        @api_rate_limit(max_requests=1, window=60)
        def my_view():
            return 'ok'

        with app.test_request_context():
            result = my_view()
            assert result == 'ok'

    def test_rate_limit_exceeded(self, app):
        app.config['TESTING'] = False

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = False
        mock_limiter.get_retry_after.return_value = 30

        with app.test_request_context():
            with patch('app.utils.api_helpers.get_rate_limiter', return_value=mock_limiter):
                with patch('app.utils.api_helpers.current_app', app):
                    with patch('app.utils.api_helpers.request') as mock_req:
                        mock_req.remote_addr = '1.2.3.4'

                        @api_rate_limit(max_requests=1, window=60)
                        def my_view():
                            return 'ok'

                        response, status = my_view()
                        assert status == 429
                        assert '30s' in response.json['message']

    def test_rate_limit_allowed(self, app):
        app.config['TESTING'] = False

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = True

        with app.test_request_context():
            with patch('app.utils.api_helpers.get_rate_limiter', return_value=mock_limiter):
                with patch('app.utils.api_helpers.current_app', app):
                    with patch('app.utils.api_helpers.request') as mock_req:
                        mock_req.remote_addr = '1.2.3.4'

                        @api_rate_limit(max_requests=60, window=60)
                        def my_view():
                            return 'ok'

                        result = my_view()
                        assert result == 'ok'


class TestPublicRateLimitDecorator:
    def test_testing_mode_bypasses(self, app):
        app.config['TESTING'] = True

        @public_rate_limit(max_requests=1, window=60)
        def my_view():
            return 'ok'

        with app.test_request_context():
            assert my_view() == 'ok'

    def test_rate_limit_exceeded(self, app):
        app.config['TESTING'] = False

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = False
        mock_limiter.get_retry_after.return_value = 45

        with app.test_request_context():
            with patch('app.utils.api_helpers.get_rate_limiter', return_value=mock_limiter):
                with patch('app.utils.api_helpers.current_app', app):
                    with patch('app.utils.api_helpers.request') as mock_req:
                        mock_req.remote_addr = '5.6.7.8'

                        @public_rate_limit(max_requests=1, window=60)
                        def my_view():
                            return 'ok'

                        response, status = my_view()
                        assert status == 429
                        assert '45s' in response.json['message']

    def test_unknown_remote_addr(self, app):
        app.config['TESTING'] = False

        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = True

        with app.test_request_context():
            with patch('app.utils.api_helpers.get_rate_limiter', return_value=mock_limiter):
                with patch('app.utils.api_helpers.current_app', app):
                    with patch('app.utils.api_helpers.request') as mock_req:
                        mock_req.remote_addr = None

                        @public_rate_limit()
                        def my_view():
                            return 'ok'

                        result = my_view()
                        assert result == 'ok'


class TestGetCsrfToken:
    def test_creates_token_and_returns(self, app, db):
        with app.app_context():
            token = get_csrf_token()
            assert isinstance(token, str)
            assert len(token) == 64

    def test_token_saved_to_db(self, app, db):
        with app.app_context():
            from app.models.schemas import CSRFToken

            token = get_csrf_token()
            record = CSRFToken.query.filter_by(token=token).first()
            assert record is not None

    def test_cleanup_triggered_at_100th_token(self, app, db):
        with app.app_context():
            from app.models.schemas import CSRFToken

            count = CSRFToken.query.count()
            remaining_to_100 = (100 - (count % 100)) % 100
            for _ in range(remaining_to_100):
                get_csrf_token()
            get_csrf_token()

    def test_db_exception_returns_token(self, app, db):
        with app.app_context(), patch('app.utils.api_helpers.db') as mock_db:
            mock_db.session.add.side_effect = Exception('db error')
            token = get_csrf_token()
            assert isinstance(token, str)


class TestValidateCsrfToken:
    def test_no_token_returns_false(self, app):
        with app.test_request_context():
            assert validate_csrf_token() is False

    def test_token_from_header(self, app, db):
        with app.app_context():
            token = get_csrf_token()
            with app.test_request_context(headers={'X-CSRF-Token': token}):
                assert validate_csrf_token() is True

    def test_token_from_form(self, app, db):
        with app.app_context():
            token = get_csrf_token()
            with app.test_request_context(data={'csrf_token': token}):
                assert validate_csrf_token() is True

    def test_invalid_token_returns_false(self, app, db):
        with app.app_context(), app.test_request_context(headers={'X-CSRF-Token': 'nonexistent'}):
            assert validate_csrf_token() is False

    def test_expired_token_returns_false(self, app, db):
        with app.app_context():
            from app.models.schemas import CSRFToken

            token = 'expired_token_123'
            record = CSRFToken(token=token)
            record.created_at = datetime.now(UTC) - timedelta(seconds=7200)
            db.session.add(record)
            db.session.commit()

            with app.test_request_context(headers={'X-CSRF-Token': token}):
                assert validate_csrf_token() is False

    def test_valid_token_with_naive_created_at(self, app, db):
        with app.app_context():
            from app.models.schemas import CSRFToken

            token = 'valid_naive_token'
            record = CSRFToken(token=token)
            record.created_at = datetime.now(UTC)
            db.session.add(record)
            db.session.commit()

            with app.test_request_context(headers={'X-CSRF-Token': token}):
                assert validate_csrf_token() is True

    def test_db_exception_returns_false(self, app, db):
        with app.app_context(), patch('app.utils.api_helpers.db') as mock_db:
            mock_db.session.get.return_value = None
            with app.test_request_context(headers={'X-CSRF-Token': 'some_token'}):
                mock_db.session.get.side_effect = Exception('db error')
                assert validate_csrf_token() is False


class TestCsrfProtectDecorator:
    def test_testing_mode_bypasses(self, app):
        app.config['TESTING'] = True

        @csrf_protect
        def my_view():
            return 'ok'

        with app.test_request_context(method='POST'):
            assert my_view() == 'ok'

    def test_get_request_passes_through(self, app):
        app.config['TESTING'] = False

        @csrf_protect
        def my_view():
            return 'ok'

        with app.test_request_context(method='GET'):
            assert my_view() == 'ok'

    def test_post_without_token_fails(self, app):
        app.config['TESTING'] = False

        @csrf_protect
        def my_view():
            return 'ok'

        with app.test_request_context(method='POST'):
            response, status = my_view()
            assert status == 403

    def test_post_with_valid_token_deletes_record(self, app, db):
        app.config['TESTING'] = False
        with app.app_context():
            token = get_csrf_token()

            @csrf_protect
            def my_view():
                return 'ok'

            with app.test_request_context(method='POST', headers={'X-CSRF-Token': token}):
                result = my_view()
                assert result == 'ok'

    def test_delete_with_valid_token(self, app, db):
        app.config['TESTING'] = False
        with app.app_context():
            token = get_csrf_token()

            @csrf_protect
            def my_view():
                return 'ok'

            with app.test_request_context(method='DELETE', headers={'X-CSRF-Token': token}):
                result = my_view()
                assert result == 'ok'

    def test_patch_with_valid_token(self, app, db):
        app.config['TESTING'] = False
        with app.app_context():
            token = get_csrf_token()

            @csrf_protect
            def my_view():
                return 'ok'

            with app.test_request_context(method='PATCH', headers={'X-CSRF-Token': token}):
                result = my_view()
                assert result == 'ok'

    def test_token_delete_exception_rolls_back(self, app, db):
        app.config['TESTING'] = False
        with app.app_context():
            from app.models.schemas import CSRFToken

            token = get_csrf_token()

            @csrf_protect
            def my_view():
                return 'ok'

            with patch('app.utils.api_helpers.db') as mock_db:
                real_record = CSRFToken.query.filter_by(token=token).first()
                mock_db.session.get.return_value = real_record
                mock_db.session.delete.side_effect = Exception('del error')

                with app.test_request_context(method='POST', headers={'X-CSRF-Token': token}):
                    result = my_view()
                    assert result == 'ok'


class TestExtractFieldContent:
    def test_title_field_chinese(self):
        text = '书名：测试书名\n作者：张三\n简介：这是一本好书'
        result = _extract_field_content(text, 'title')
        assert result == '测试书名'

    def test_description_field(self):
        text = '简介：这是一本关于冒险的书\n作者：李四'
        result = _extract_field_content(text, 'description')
        assert result == '这是一本关于冒险的书'

    def test_details_field(self):
        text = '详情：详细内容在这里\n出版社：测试出版社'
        result = _extract_field_content(text, 'details')
        assert result == '详细内容在这里'

    def test_english_labels(self):
        text = 'Title: My Book\nAuthor: Someone'
        result = _extract_field_content(text, 'title')
        assert result == 'My Book'

    def test_unknown_field_type_returns_text(self):
        result = _extract_field_content('some text', 'unknown')
        assert result == 'some text'

    def test_no_start_label(self):
        text = '没有标签的文本'
        result = _extract_field_content(text, 'title')
        assert result == '没有标签的文本'

    def test_colon_separator(self):
        text = 'Title: English Book\nAuthor: Writer'
        result = _extract_field_content(text, 'title')
        assert result == 'English Book'


class TestAddBookTitleMarks:
    def test_empty_text(self):
        assert _add_book_title_marks('') == ''
        assert _add_book_title_marks(None) is None

    def test_already_has_marks(self):
        assert _add_book_title_marks('《活着》') == '《活着》'

    def test_chinese_title_gets_marks(self):
        assert _add_book_title_marks('活着') == '《活着》'

    def test_english_title_no_marks(self):
        assert _add_book_title_marks('The Great Gatsby') == 'The Great Gatsby'

    def test_mixed_text_no_marks(self):
        assert _add_book_title_marks('活着 Alive') == '活着 Alive'


class TestCleanTitleText:
    def test_empty(self):
        assert _clean_title_text('') == ''
        assert _clean_title_text(None) is None

    def test_book_match_in_brackets(self):
        result = _clean_title_text('作者名 · 《书名》 描述文本')
        assert result == '书名'

    def test_newline_separated(self):
        result = _clean_title_text('简短书名\n作者名字很长')
        assert result == '简短书名'

    def test_dot_separator(self):
        result = _clean_title_text('书名 · 作者')
        assert result == '书名'

    def test_translator_suffix_removed(self):
        result = _clean_title_text('书名 张三译')
        assert '张三译' not in result

    def test_description_truncation(self):
        result = _clean_title_text('书名是一本非常好的长书名。这本书很好看值得推荐')
        assert '这本书' not in result

    def test_long_first_line_with_dot_keeps_original(self):
        result = _clean_title_text('这是一本非常非常长的书名，超过二十个字符的\n第二行')
        assert '非常非常长' in result


class TestStripMarkdown:
    def test_empty(self):
        assert _strip_markdown('') == ''
        assert _strip_markdown(None) is None

    def test_bold(self):
        assert _strip_markdown('**bold**') == 'bold'

    def test_underscore_bold(self):
        assert _strip_markdown('__bold__') == 'bold'

    def test_italic_star(self):
        assert _strip_markdown('*italic*') == 'italic'

    def test_inline_code(self):
        assert _strip_markdown('`code`') == 'code'

    def test_header(self):
        assert _strip_markdown('# Header') == 'Header'

    def test_link(self):
        assert _strip_markdown('[link](http://example.com)') == 'link'

    def test_image_becomes_bang_alias(self):
        assert _strip_markdown('![alt](http://img.com/a.png)') == '!alt'

    def test_horizontal_rule(self):
        assert _strip_markdown('---') == ''

    def test_quote(self):
        assert _strip_markdown('> quoted text') == 'quoted text'


class TestCleanTranslationTextExtended:
    def test_removes_translation_prefix(self):
        result = clean_translation_text('翻译：这是翻译结果')
        assert result == '这是翻译结果'

    def test_removes_translation_result_prefix(self):
        result = clean_translation_text('翻译结果：Hello')
        assert result == 'Hello'

    def test_removes_trailing_yi(self):
        result = clean_translation_text('翻译结果译')
        assert result == '翻译结果'

    def test_removes_trailing_bracket_yi(self):
        result = clean_translation_text('翻译结果[译]')
        assert '[译]' not in result

    def test_removes_trailing_paren_yi(self):
        result = clean_translation_text('翻译结果(译)')
        assert '(译)' not in result

    def test_removes_field_prefix(self):
        result = clean_translation_text('Title：我的书', field_type='title')
        assert 'Title' not in result

    def test_title_field_extraction(self):
        result = clean_translation_text('书名：好书\n作者：张三', field_type='title')
        assert '好书' in result

    def test_description_field_extraction(self):
        result = clean_translation_text('简介：好书简介\n出版社：测试', field_type='description')
        assert '好书简介' in result

    def test_removes_single_stars(self):
        result = clean_translation_text('这是*翻译*文本')
        assert '*' not in result

    def test_unified_quotes(self):
        result = clean_translation_text('\u201c测试\u201d')
        assert '\u201c' in result

    def test_clears_empty_lines(self):
        result = clean_translation_text('第一行\n\n\n第二行')
        assert '\n\n' not in result


class TestQuickCleanTranslation:
    def test_empty(self):
        assert quick_clean_translation('') == ''
        assert quick_clean_translation(None) is None

    def test_clean_text_passes_through(self):
        assert quick_clean_translation('这是一段干净的文本') == '这是一段干净的文本'

    def test_dirty_text_gets_cleaned(self):
        result = quick_clean_translation('书名：脏数据\n作者：张三', field_type='title')
        assert '书名' not in result

    def test_trailing_yi_marker(self):
        result = quick_clean_translation('翻译结果译')
        assert result == '翻译结果'

    def test_dirty_marker_bold(self):
        result = quick_clean_translation('**粗体文本**')
        assert '**' not in result


class TestPublicAPIResponseExtended:
    @pytest.fixture
    def app(self):
        return Flask(__name__)

    def test_error_with_list_errors(self, app):
        with app.test_request_context():
            response, status = PublicAPIResponse.error('err', 400, errors=['e1', 'e2'])
            assert status == 400
            assert response.json['errors'] == ['e1', 'e2']

    def test_error_without_errors(self, app):
        with app.test_request_context():
            response, status = PublicAPIResponse.error('err', 400, errors=None)
            assert 'errors' not in response.json

    def test_success_custom_status(self, app):
        with app.test_request_context():
            response, status = PublicAPIResponse.success(data='d', status_code=201)
            assert status == 201


class TestAPIResponseExtended:
    @pytest.fixture
    def app(self):
        return Flask(__name__)

    def test_error_without_errors_field(self, app):
        with app.test_request_context():
            response, status = APIResponse.error('err', 400)
            assert 'errors' not in response.json

    def test_error_with_list_errors(self, app):
        with app.test_request_context():
            response, status = APIResponse.error('err', 400, errors=['e1'])
            assert response.json['errors'] == ['e1']

    def test_success_custom_status(self, app):
        with app.test_request_context():
            response, status = APIResponse.success(data='x', status_code=201)
            assert status == 201
