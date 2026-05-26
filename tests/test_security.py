"""安全工具函数测试"""

from unittest.mock import patch

from app.utils.security import (
    generate_secure_token,
    is_safe_redirect_url,
    log_safe,
    mask_sensitive_data,
    sanitize_filename,
    validate_input,
)


class TestValidateInput:
    """测试 validate_input"""

    def test_valid_input(self):
        is_valid, sanitized, error = validate_input('hello', field_name='name')
        assert is_valid is True
        assert sanitized == 'hello'
        assert error is None

    def test_none_input(self):
        is_valid, sanitized, error = validate_input(None, field_name='name')
        assert is_valid is False
        assert sanitized is None
        assert 'required' in error

    def test_empty_string(self):
        is_valid, sanitized, _error = validate_input('   ', field_name='name')
        assert is_valid is False
        assert sanitized is None

    def test_max_length_exceeded(self):
        is_valid, _sanitized, error = validate_input('a' * 101, max_length=100, field_name='name')
        assert is_valid is False
        assert 'at most' in error

    def test_max_length_ok(self):
        is_valid, _sanitized, _error = validate_input('short', max_length=100, field_name='name')
        assert is_valid is True

    def test_pattern_match(self):
        is_valid, _sanitized, _error = validate_input('abc123', pattern=r'^[a-z0-9]+$', field_name='code')
        assert is_valid is True

    def test_pattern_no_match(self):
        is_valid, _sanitized, error = validate_input('ABC!', pattern=r'^[a-z0-9]+$', field_name='code')
        assert is_valid is False
        assert 'invalid characters' in error

    def test_strips_whitespace(self):
        is_valid, sanitized, _error = validate_input('  hello  ', field_name='name')
        assert is_valid is True
        assert sanitized == 'hello'

    def test_numeric_input(self):
        is_valid, sanitized, _error = validate_input(123, field_name='count')
        assert is_valid is True
        assert sanitized == '123'


class TestSanitizeFilename:
    """测试 sanitize_filename"""

    def test_normal_filename(self):
        assert sanitize_filename('report.pdf') == 'report.pdf'

    def test_path_traversal(self):
        result = sanitize_filename('../../etc/passwd')
        assert '..' not in result

    def test_empty_filename(self):
        result = sanitize_filename('')
        assert result == 'unnamed'

    def test_special_chars(self):
        result = sanitize_filename('my file (1).txt')
        assert isinstance(result, str)
        assert len(result) > 0


class TestGenerateSecureToken:
    """测试 generate_secure_token"""

    def test_default_length(self):
        token = generate_secure_token()
        assert len(token) == 64

    def test_custom_length(self):
        token = generate_secure_token(16)
        assert len(token) == 32

    def test_uniqueness(self):
        t1 = generate_secure_token()
        t2 = generate_secure_token()
        assert t1 != t2


class TestMaskSensitiveData:
    """测试 mask_sensitive_data"""

    def test_normal_data(self):
        result = mask_sensitive_data('sk-1234567890abcdef')
        assert result.startswith('sk-1')
        assert '*' in result

    def test_short_data(self):
        result = mask_sensitive_data('abc')
        assert result == '****'

    def test_empty_data(self):
        result = mask_sensitive_data('')
        assert result == '****'

    def test_none_data(self):
        result = mask_sensitive_data(None)
        assert result == '****'

    def test_custom_visible_chars(self):
        result = mask_sensitive_data('abcdefgh', visible_chars=2)
        assert result.startswith('ab')
        assert result.endswith('******')


class TestIsSafeRedirectUrl:
    """测试 is_safe_redirect_url"""

    def test_empty_url(self):
        assert is_safe_redirect_url('') is False

    def test_none_url(self):
        assert is_safe_redirect_url(None) is False

    def test_relative_path(self):
        assert is_safe_redirect_url('/dashboard') is True

    def test_allowed_host(self):
        assert is_safe_redirect_url('https://example.com/page', allowed_hosts={'example.com'}) is True

    def test_disallowed_host(self):
        assert is_safe_redirect_url('https://evil.com/page', allowed_hosts={'example.com'}) is False

    def test_no_allowed_hosts_with_netloc(self):
        assert is_safe_redirect_url('https://example.com/page') is False

    def test_javascript_scheme(self):
        assert is_safe_redirect_url('javascript:alert(1)') is False

    def test_protocol_relative(self):
        assert is_safe_redirect_url('//evil.com') is False

    def test_backslash_in_url(self):
        assert is_safe_redirect_url('/path\\evil') is False

    def test_http_scheme(self):
        assert is_safe_redirect_url('http://example.com', allowed_hosts={'example.com'}) is True


class TestLogSafe:
    """测试 log_safe"""

    @patch('app.utils.security.logger')
    def test_filters_sensitive_keys(self, mock_logger):
        log_safe('test message', password='secret123', token='abc', username='john')
        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs['password'] == '****'
        assert call_kwargs['token'] == '****'
        assert call_kwargs['username'] == 'john'

    @patch('app.utils.security.logger')
    def test_no_kwargs(self, mock_logger):
        log_safe('simple message')
        mock_logger.info.assert_called_once_with('simple message')

    @patch('app.utils.security.logger')
    def test_api_key_filtered(self, mock_logger):
        log_safe('msg', api_key='my-key', SECRET='top')
        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs['api_key'] == '****'
        assert call_kwargs['SECRET'] == '****'
