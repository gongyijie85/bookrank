"""应用工厂函数和 setup 模块测试"""

from unittest.mock import patch

from flask import Flask


class TestCreateApp:
    """测试 create_app 工厂函数"""

    def test_returns_flask_instance(self, app):
        assert isinstance(app, Flask)

    def test_testing_config_enabled(self):
        from app import create_app

        test_app = create_app('testing')
        assert test_app.config['TESTING'] is True

    def test_app_env_set_to_testing(self, app):
        assert app.config['APP_ENV'] == 'testing'

    def test_debug_enabled_in_testing(self, app):
        assert app.config['DEBUG'] is True

    def test_sqlite_memory_database(self, app):
        assert 'memory' in app.config['SQLALCHEMY_DATABASE_URI']

    def test_csrf_disabled_in_testing(self, app):
        assert app.config.get('WTF_CSRF_ENABLED') is False

    def test_session_cookie_not_secure_in_testing(self, app):
        assert app.config['SESSION_COOKIE_SECURE'] is False

    def test_create_app_with_default_config(self):
        with patch.dict('os.environ', {'FLASK_ENV': 'testing'}):
            app = Flask(__name__)
            assert isinstance(app, Flask)

    def test_create_app_sets_env_key(self, app):
        assert 'ENV' in app.config


class TestBlueprints:
    """测试蓝图注册"""

    EXPECTED_BLUEPRINTS = {
        'main',
        'api',
        'admin',
        'public_api',
        'new_books',
        'health',
        'analytics',
    }

    def test_all_blueprints_registered(self, app):
        registered = set(app.blueprints.keys())
        assert self.EXPECTED_BLUEPRINTS.issubset(registered)

    def test_blueprint_count(self, app):
        registered = set(app.blueprints.keys())
        assert len(registered & self.EXPECTED_BLUEPRINTS) == 7

    def test_main_blueprint_has_rules(self, app):
        bp = app.blueprints.get('main')
        assert bp is not None
        assert len(bp.deferred_functions) > 0

    def test_api_blueprint_has_rules(self, app):
        bp = app.blueprints.get('api')
        assert bp is not None
        assert len(bp.deferred_functions) > 0


class TestErrorHandlers:
    """测试全局错误处理器"""

    EXPECTED_HANDLERS = {400, 404, 405, 429, 500}

    def test_all_error_handlers_registered(self, app):
        registered = set(app.error_handler_spec.get(None, {}).keys())
        assert self.EXPECTED_HANDLERS.issubset(registered)

    def test_400_returns_json(self, client):
        response = client.get('/api/nonexistent-endpoint-400-test')
        assert response.status_code in (400, 404)

    def test_404_returns_json(self, client):
        response = client.get('/path-that-does-not-exist-at-all')
        assert response.status_code == 404

    def test_405_returns_json(self, client):
        response = client.post('/health')
        assert response.status_code == 405


class TestTemplateFilters:
    """测试自定义 Jinja2 模板过滤器"""

    EXPECTED_FILTERS = {
        'sanitize_html',
        'markdown',
        'format_title',
        'clean_brackets',
        'is_valid_isbn',
        'clean_isbn',
        'is_invalid_publisher',
    }

    def test_all_filters_registered(self, app):
        registered = set(app.jinja_env.filters.keys())
        assert self.EXPECTED_FILTERS.issubset(registered)

    def test_filter_count(self, app):
        registered = set(app.jinja_env.filters.keys())
        assert len(registered & self.EXPECTED_FILTERS) == 7

    def test_sanitize_html_callable(self, app):
        with app.app_context():
            fn = app.jinja_env.filters['sanitize_html']
            assert callable(fn)

    def test_markdown_callable(self, app):
        with app.app_context():
            fn = app.jinja_env.filters['markdown']
            assert callable(fn)

    def test_format_title_callable(self, app):
        with app.app_context():
            fn = app.jinja_env.filters['format_title']
            assert callable(fn)

    def test_is_valid_isbn_callable(self, app):
        with app.app_context():
            fn = app.jinja_env.filters['is_valid_isbn']
            assert callable(fn)

    def test_clean_isbn_callable(self, app):
        with app.app_context():
            fn = app.jinja_env.filters['clean_isbn']
            assert callable(fn)

    def test_is_invalid_publisher_callable(self, app):
        with app.app_context():
            fn = app.jinja_env.filters['is_invalid_publisher']
            assert callable(fn)


class TestContextProcessors:
    """测试模板上下文处理器"""

    def test_get_locale_in_jinja_globals(self, app):
        assert 'get_locale' in app.jinja_env.globals

    def test_get_locale_callable(self, app):
        fn = app.jinja_env.globals['get_locale']
        assert callable(fn)

    def test_get_locale_via_jinja_globals(self, app):
        with app.app_context(), app.test_request_context('/?lang=zh'):
            assert 'get_locale' in app.jinja_env.globals
            assert app.jinja_env.globals['get_locale']() == 'zh'

    def test_csp_nonce_in_jinja_globals(self, app):
        with app.app_context():
            processors = app.template_context_processors[None]
            inject_csp = None
            for proc in processors:
                result = proc()
                if 'csp_nonce' in result:
                    inject_csp = proc
                    break
            assert inject_csp is not None

    def test_csp_nonce_returns_callable(self, app):
        with app.app_context():
            processors = app.template_context_processors[None]
            for proc in processors:
                result = proc()
                if 'csp_nonce' in result:
                    nonce_fn = result['csp_nonce']
                    assert callable(nonce_fn)
                    return
            assert False, 'csp_nonce context processor not found'


class TestSecurityHeaders:
    """测试安全响应头和 after_request 钩子"""

    def test_x_frame_options(self, client):
        response = client.get('/health')
        assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'

    def test_x_content_type_options(self, client):
        response = client.get('/health')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_xss_protection(self, client):
        response = client.get('/health')
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'

    def test_referrer_policy(self, client):
        response = client.get('/health')
        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_server_header(self, client):
        response = client.get('/health')
        assert response.headers.get('Server') == 'BookRank'

    def test_csp_header_present(self, client):
        response = client.get('/health')
        assert 'Content-Security-Policy' in response.headers

    def test_permissions_policy(self, client):
        response = client.get('/health')
        assert 'Permissions-Policy' in response.headers


class TestInitServices:
    """测试 setup.py 中的 init_services"""

    def test_cache_service_registered(self, app):
        assert 'cache_service' in app.extensions

    def test_cache_service_is_cache_service_instance(self, app):
        from app.services.cache_service import CacheService

        assert isinstance(app.extensions['cache_service'], CacheService)


class TestShutdownScheduler:
    """测试 shutdown_scheduler 函数"""

    def test_shutdown_scheduler_when_none(self, app):
        from app.setup import shutdown_scheduler

        with patch('app.setup._scheduler', None):
            shutdown_scheduler(app)

    def test_shutdown_scheduler_when_running(self, app):
        from app.setup import shutdown_scheduler

        mock_scheduler = patch('app.setup._scheduler')
        with mock_scheduler as mock_s:
            mock_s.running = True
            shutdown_scheduler(app)
            mock_s.shutdown.assert_called_once_with(wait=True)
