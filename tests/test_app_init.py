"""应用初始化和 Jinja 过滤器测试"""

import json


class TestJinjaFilters:
    """测试自定义 Jinja2 过滤器"""

    def test_sanitize_html_removes_script(self, app):
        with app.app_context():
            result = app.jinja_env.filters['sanitize_html']('<script>alert(1)</script><p>safe</p>')
            assert '<script>' not in result
            assert '<p>safe</p>' in result

    def test_sanitize_html_removes_iframe(self, app):
        with app.app_context():
            result = app.jinja_env.filters['sanitize_html']('<iframe src="evil.com"></iframe>')
            assert '<iframe' not in result

    def test_sanitize_html_removes_event_handlers(self, app):
        with app.app_context():
            result = app.jinja_env.filters['sanitize_html']('<div onclick="evil()">text</div>')
            assert 'onclick' not in result

    def test_sanitize_html_removes_js_urls(self, app):
        with app.app_context():
            result = app.jinja_env.filters['sanitize_html']('<a href="javascript:evil()">link</a>')
            assert 'javascript:' not in result

    def test_sanitize_html_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['sanitize_html'](None)
            assert result == ''

    def test_markdown_filter(self, app):
        with app.app_context():
            result = app.jinja_env.filters['markdown']('**bold**')
            assert '<strong>' in result or '<b>' in result

    def test_markdown_filter_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['markdown'](None)
            assert result == ''

    def test_format_title_filter(self, app):
        with app.app_context():
            result = app.jinja_env.filters['format_title']('Test Book')
            assert result == '《Test Book》'

    def test_format_title_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['format_title'](None)
            assert result == ''

    def test_format_title_removes_duplicate_brackets(self, app):
        with app.app_context():
            result = app.jinja_env.filters['format_title']('《Test》')
            assert result == '《Test》'

    def test_clean_brackets_filter(self, app):
        with app.app_context():
            result = app.jinja_env.filters['clean_brackets']('《《Book》》')
            assert result == '《Book》'

    def test_clean_brackets_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['clean_brackets'](None)
            assert result == ''

    def test_is_valid_isbn_13(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_valid_isbn']('9780743273565')
            assert result is True

    def test_is_valid_isbn_10(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_valid_isbn']('0743273567')
            assert result is True

    def test_is_valid_isbn_invalid(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_valid_isbn']('invalid')
            assert result is False

    def test_is_valid_isbn_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_valid_isbn'](None)
            assert result is False

    def test_clean_isbn_filter(self, app):
        with app.app_context():
            result = app.jinja_env.filters['clean_isbn']('978-0-7432-7356-5')
            assert result == '9780743273565'

    def test_clean_isbn_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['clean_isbn'](None)
            assert result == ''

    def test_is_invalid_publisher_none(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_invalid_publisher'](None)
            assert result is True

    def test_is_invalid_publisher_short(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_invalid_publisher']('abc')
            assert result is True

    def test_is_invalid_publisher_category_name(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_invalid_publisher']('fiction')
            assert result is True

    def test_is_invalid_publisher_valid(self, app):
        with app.app_context():
            result = app.jinja_env.filters['is_invalid_publisher']('Penguin Random House')
            assert result is False


class TestErrorHandlers:
    """测试全局错误处理器"""

    def test_404_error(self, client):
        response = client.get('/nonexistent-path-that-does-not-exist')
        assert response.status_code == 404

    def test_405_error(self, client):
        response = client.post('/health')
        assert response.status_code == 405

    def test_400_error(self, client, app):
        with app.app_context():
            response = client.post('/api/public/bestsellers/search')
            json.loads(response.data)
            assert response.status_code in (400, 405, 200)


class TestSecurityHeaders:
    """测试安全响应头"""

    def test_security_headers_present(self, client):
        response = client.get('/health')
        assert 'X-Frame-Options' in response.headers
        assert 'X-Content-Type-Options' in response.headers
        assert 'Content-Security-Policy' in response.headers

    def test_csp_nonce_injected(self, client):
        """v0.9.42 决策：CSP 使用 unsafe-inline 而非 nonce（详见 CHANGELOG v0.9.42）
        此处验证 'unsafe-inline' 在 script-src 和 style-src 中都存在。"""
        response = client.get('/health')
        csp = response.headers.get('Content-Security-Policy', '')
        assert 'unsafe-inline' in csp
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp


class TestGetLocale:
    """测试语言选择器"""

    def test_url_param_lang(self, client):
        response = client.get('/health?lang=zh')
        assert response.status_code == 200

    def test_cookie_lang(self, client):
        client.set_cookie('lang', 'zh')
        response = client.get('/health')
        assert response.status_code == 200
