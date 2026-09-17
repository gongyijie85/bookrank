"""安全工具函数测试"""

from app.utils.security import is_safe_redirect_url


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
