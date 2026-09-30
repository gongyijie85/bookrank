"""安全工具函数测试"""

import pytest

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


@pytest.mark.parametrize(
    'value',
    [
        '/new-books?search=https%3A%2F%2Fexample.com&lang=en&page=2',
        '/awards?year=2026&lang=zh&view=list&page=3',
        '/',
        '/new-books?search=a%26b',
    ],
)
def test_safe_return_path_retains_valid_local_path_and_query(value):
    from app.utils.security import safe_return_path

    assert safe_return_path(value, default='/awards') == value


@pytest.mark.parametrize(
    'value',
    [
        None,
        '',
        '   ',
        12,
        '//evil.example/a',
        'https://same.test/new-books',
        'javascript:alert(1)',
        '\\evil',
        '/\\evil',
        '/bad\npath',
        '/bad\x00path',
        '/bad\x7fpath',
        '/%0d%0aevil',
        '/%252f%252fevil',
        '/%2f%2fevil',
        '/%255cevil',
        '/%5cevil',
        '/%2Fevil',
        '/%252Fevil',
        '/%5Cevil',
        '/%255Cevil',
        '%2F%2Fevil',
        '/safe#frag',
        'relative',
    ],
)
def test_safe_return_path_rejects_unsafe_and_keeps_allowed_host(value):
    from app.utils.security import is_safe_redirect_url, safe_return_path

    assert safe_return_path(value, default='/awards') == '/awards'
    assert is_safe_redirect_url('https://example.com/page', allowed_hosts={'example.com'}) is True
