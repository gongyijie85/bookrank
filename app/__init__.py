import gzip
import io
import logging
import os
import re
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, render_template, request
from flask_babel import Babel
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import config
from .initialization import init_awards_data, init_sample_books
from .initialization import init_sample_award_books as init_sample_award_books
from .models import db, init_db
from .routes import admin_bp, analytics_bp, api_bp, health_bp, main_bp, new_books_bp, public_api_bp
from .setup import shutdown_scheduler
from .utils.error_handler import ErrorCategory, log_error

babel = Babel()

PROJECT_ROOT = Path(__file__).parent.parent


def create_app(config_name: str | None = None) -> Flask:
    """
    应用工厂函数

    Args:
        config_name: 配置名称 ('development', 'production', 'testing')

    Returns:
        Flask应用实例
    """
    if config_name is None or config_name == 'default':
        config_name = 'development'

    app = Flask(__name__, template_folder=str(PROJECT_ROOT / 'templates'), static_folder=str(PROJECT_ROOT / 'static'))

    app.config.from_object(config[config_name])
    app.config['APP_ENV'] = config_name
    app.config['ENV'] = config_name
    config[config_name].init_app(app)

    # 生产环境信任反向代理（Render、Nginx 等）的 X-Forwarded-For 头
    if config_name == 'production':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    if config_name != 'testing' and app.config.get('SECRET_KEY', '').startswith('dev-secret-key'):
        app.logger.warning(
            '⚠️ SECRET_KEY 仍为开发环境默认值！'
            ' 请生成强随机密钥: python -c "import secrets; print(secrets.token_hex(32))"'
            ' 并设置为 SECRET_KEY 环境变量'
        )

    _init_extensions(app, config_name)
    _register_blueprints(app)
    _register_error_handlers(app)
    _configure_logging(app)
    _apply_security_headers(app)
    _register_jinja_filters(app)

    if config_name == 'production':
        _enable_rate_limiting(app)

    # 为每个请求生成唯一追踪 ID，便于日志关联与排障
    @app.before_request
    def init_request_context() -> None:
        request.request_id = uuid.uuid4().hex[:16]  # type: ignore[attr-defined]

    # 请求结束时清理数据库会话，防止连接泄漏
    @app.teardown_appcontext
    def shutdown_session(exception: BaseException | None = None) -> None:
        db.session.remove()

    # 初始化 Babel（国际化）- Flask-Babel 4.0+ API
    babel.init_app(app, locale_selector=_get_locale)

    # 将 get_locale 注入 Jinja2 全局命名空间（确保所有模板包括导入的宏都能访问）
    app.jinja_env.globals['get_locale'] = _get_locale

    # 注入当前时间函数，供模板显示动态年份等场景
    app.jinja_env.globals['now'] = datetime.now

    import atexit

    atexit.register(lambda: shutdown_scheduler(app))

    return app


def _get_locale() -> str:
    """语言选择器：URL参数 > Cookie > Accept-Language > 默认en"""
    # 1. URL 参数
    lang = request.args.get('lang')
    if lang in ('en', 'zh'):
        return lang

    # 2. Cookie
    lang = request.cookies.get('lang')
    if lang in ('en', 'zh'):
        return lang

    # 3. Accept-Language header
    if request.accept_languages:
        best = request.accept_languages.best_match(['en', 'zh'])
        if best:
            return best

    # 4. 默认英文
    return 'en'


def _init_extensions(app: Flask, config_name: str) -> None:
    """初始化Flask扩展"""
    if config_name == 'production':
        cors_origins = app.config.get('CORS_ORIGINS', [])
        if not cors_origins:
            app.logger.warning(
                '⚠️ CORS_ORIGINS 未设置！生产环境跨域请求将被阻止。'
                ' 请设置 CORS_ORIGINS 环境变量（逗号分隔的域名列表），'
                '例如: CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com'
            )
            cors_origins = []
        cors_methods = ['GET', 'POST', 'OPTIONS']
    elif config_name == 'testing':
        cors_origins = '*'
        cors_methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    else:
        cors_origins = ['http://localhost:5000']
        cors_methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']

    CORS(
        app,
        resources={
            r'/api/*': {
                'origins': cors_origins,
                'methods': cors_methods,
                'allow_headers': ['Content-Type', 'Authorization'],
                'expose_headers': ['Content-Length', 'Content-Disposition'],
                'max_age': 3600,
            }
        },
        supports_credentials=bool(cors_origins and cors_origins != '*'),
    )

    init_db(app)

    try:
        from flask_mail import Mail

        app.extensions['mail'] = Mail(app)
    except ImportError:
        app.logger.info('Flask-Mail 未安装，邮件功能已禁用')

    _setup_db_event_listeners(app)

    if config_name not in ('production', 'testing'):
        _auto_init_awards(app)

    from .setup import init_services

    init_services(app)


def _auto_init_awards(app: Flask) -> None:
    """自动初始化奖项数据"""
    with app.app_context():
        init_awards_data(app)
        init_sample_books(app)


def _register_blueprints(app: Flask) -> None:
    """注册蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_api_bp)
    app.register_blueprint(new_books_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(analytics_bp)


def _register_error_handlers(app: Flask) -> None:
    """注册全局错误处理器"""

    @app.errorhandler(400)
    def bad_request(error: Exception) -> tuple[dict[str, bool | str], int]:
        return {'success': False, 'message': 'Bad request'}, 400

    @app.errorhandler(404)
    def not_found(error: Exception):
        if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
            return {'success': False, 'message': 'Resource not found'}, 404
        return render_template('error.html', message='Page not found', back_url='/'), 404

    @app.errorhandler(405)
    def method_not_allowed(error: Exception) -> tuple[dict[str, bool | str], int]:
        return {'success': False, 'message': 'Method not allowed'}, 405

    @app.errorhandler(429)
    def rate_limit_exceeded(error: Exception) -> tuple[dict[str, bool | str], int]:
        return {'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429

    @app.errorhandler(500)
    def internal_error(error: Exception):
        try:
            db.session.rollback()
        except Exception:
            db.session.remove()
        log_error(ErrorCategory.UNKNOWN, f'Internal error: {error}', exc_info=True)
        try:
            from .utils.error_tracker import error_tracker

            error_tracker.record(
                error_type='500',
                message=str(error),
                path=request.path if request else '',
                method=request.method if request else '',
            )
        except Exception as e:
            log_error(ErrorCategory.UNKNOWN, f'ErrorTracker 记录失败: {e}', level='warning')
        if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
            return {'success': False, 'message': 'Internal server error'}, 500
        return render_template('error.html', message='Something went wrong', back_url='/'), 500


def _setup_db_event_listeners(app: Flask) -> None:
    """设置数据库事件监听器，处理 Render PostgreSQL 休眠恢复

    注意：pool_pre_ping=True 已在 config.py 中启用，它会在每次 checkout 时
    自动执行连接活性检测，因此这里不再重复 SELECT 1 检查。
    """
    from sqlalchemy import event
    from sqlalchemy.pool import Pool

    @event.listens_for(Pool, 'checkin')
    def handle_checkin(dbapi_connection: Any, connection_record: Any) -> None:
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'连接归还时回滚失败: {e}', level='warning')

    @event.listens_for(Pool, 'connect')
    def on_connect(dbapi_connection: Any, connection_record: Any) -> None:
        app.logger.debug('数据库新连接已建立')
        if hasattr(dbapi_connection, 'set_session'):
            try:
                dbapi_connection.set_session(autocommit=False)
            except Exception as e:
                log_error(ErrorCategory.DB_QUERY, f'设置连接参数失败: {e}', level='warning')
        module_name = dbapi_connection.__class__.__module__
        if 'psycopg' in module_name:
            cursor = None
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("SET TIME ZONE 'UTC'")
            except Exception as e:
                log_error(ErrorCategory.DB_QUERY, f'设置时区失败: {e}', level='warning')
            finally:
                if cursor is not None:
                    cursor.close()

    @event.listens_for(Pool, 'reset')
    def on_reset(dbapi_connection: Any, connection_record: Any, reset_state: Any = None) -> None:
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'连接重置时回滚失败: {e}', level='warning')


def _configure_logging(app: Flask) -> None:
    """配置日志"""
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)

        app.logger.handlers.clear()
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.propagate = False

        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)


def _apply_security_headers(app: Flask) -> None:
    """应用安全响应头和静态资源缓存"""

    @app.before_request
    def generate_csp_nonce() -> None:
        """每个请求生成独立的 CSP nonce，供内联脚本/样式使用"""
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def inject_csp_nonce() -> dict[str, Any]:
        """注入 csp_nonce() 模板函数，返回当前请求的 nonce"""
        return {'csp_nonce': lambda: getattr(g, 'csp_nonce', '')}

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        nonce = getattr(g, 'csp_nonce', '')
        security_headers = {
            'X-Frame-Options': 'SAMEORIGIN',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                f"style-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
                "img-src 'self' data: https://*.nytimes.com https://*.amazon.com https://*.amazonaws.com https://books.google.com "
                'https://covers.openlibrary.org https://openlibrary.org https://archive.org https://*.archive.org '
                'https://*.penguinrandomhouse.com https://*.harpercollins.com '
                'https://*.macmillan.com https://*.simonandschuster.com https://*.hachettebookgroup.com; '
                "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://fonts.gstatic.com; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "frame-src 'none'; "
                "object-src 'none';"
            ),
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
        }

        for header, value in security_headers.items():
            response.headers[header] = value

        # 显式移除 Server 头（默认会泄露 Werkzeug/Flask 版本）
        response.headers.pop('Server', None)

        if app.config.get('APP_ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

        if request and hasattr(request, 'request_id'):
            response.headers['X-Request-ID'] = request.request_id

        request_path = request.path if request else ''
        if request_path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=2592000, immutable'

        if (
            'gzip' in request.headers.get('Accept-Encoding', '')
            and response.content_type
            and any(
                t in response.content_type for t in ('text/', 'application/json', 'application/javascript', 'image/svg')
            )
            and response.content_length
            and response.content_length > 1024
        ):
            response.direct_passthrough = False
            gzip_buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=gzip_buffer, mode='wb', compresslevel=4) as gz:
                gz.write(response.get_data())
            response.set_data(gzip_buffer.getvalue())
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = str(len(response.get_data()))
            response.headers['Vary'] = 'Accept-Encoding'

        return response


def _enable_rate_limiting(app: Flask) -> None:
    """启用API速率限制"""
    from flask import make_response

    from .utils.rate_limiter import get_rate_limiter

    rate_limiter = get_rate_limiter(
        max_requests=app.config.get('API_RATE_LIMIT', 60), window_seconds=app.config.get('API_RATE_LIMIT_WINDOW', 60)
    )

    @app.before_request
    def rate_limit_requests() -> Response | None:
        from flask import current_app

        if current_app.config.get('TESTING'):
            return None

        if (
            request.path.startswith('/static/')
            or request.path.startswith('/health/')
            or request.path.startswith('/api/cron/')
            or not request.path.startswith('/api/')
        ):
            return None

        excluded_paths = ['/api/csrf-token', '/api/health']
        if request.path in excluded_paths:
            return None

        client_ip = request.remote_addr or 'unknown'

        if not rate_limiter.is_allowed(client_ip):
            retry_after = rate_limiter.get_retry_after(client_ip)
            response = make_response({'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429)
            response.headers['Retry-After'] = str(retry_after)
            return response

        return None


def _register_jinja_filters(app: Flask) -> None:
    """注册自定义Jinja2过滤器"""
    import mistune

    try:
        import bleach as _bleach

        _ALLOWED_TAGS = [
            'p',
            'br',
            'strong',
            'em',
            'b',
            'i',
            'u',
            'h1',
            'h2',
            'h3',
            'h4',
            'h5',
            'h6',
            'ul',
            'ol',
            'li',
            'a',
            'blockquote',
            'code',
            'pre',
            'span',
            'div',
            'table',
            'thead',
            'tbody',
            'tr',
            'th',
            'td',
            'img',
            'hr',
            'sub',
            'sup',
        ]
        _ALLOWED_ATTRS = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'span': ['class'],
            'div': ['class'],
            'code': ['class'],
            'pre': ['class'],
            'td': ['colspan', 'rowspan'],
            'th': ['colspan', 'rowspan'],
        }

        def _sanitize_with_bleach(text: str) -> str:
            return str(_bleach.clean(text, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True))

        _sanitize_fn = _sanitize_with_bleach
    except ImportError:
        # Fallback: regex-based sanitizer when bleach is not installed
        _UNSAFE_TAGS_RE = re.compile(
            r'<\s*/?\s*(?:script|iframe|object|embed|form|input|textarea|button|link|meta|base|applet)\b[^>]*>',
            re.IGNORECASE,
        )
        _EVENT_HANDLER_RE = re.compile(r'\s+on\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)', re.IGNORECASE)
        _JS_URL_RE = re.compile(
            r'(?:href|src|action)\s*=\s*(?:"javascript:[^"]*"|\'javascript:[^\']*\'|javascript:\S+)', re.IGNORECASE
        )

        def _sanitize_with_regex(text: str) -> str:
            text = _UNSAFE_TAGS_RE.sub('', text)
            text = _EVENT_HANDLER_RE.sub('', text)
            text = _JS_URL_RE.sub('', text)
            return text

        _sanitize_fn = _sanitize_with_regex

    @app.template_filter('sanitize_html')
    def sanitize_html_filter(text: str | None) -> str:
        """HTML消毒：移除危险标签和事件属性，保留安全的格式标签"""
        if not text:
            return ''
        return _sanitize_fn(text)

    @app.template_filter('markdown')
    def markdown_filter(text: str | None) -> str:
        """将Markdown文本转换为HTML（自动消毒）"""
        if not text:
            return ''
        html = mistune.html(text)
        return sanitize_html_filter(html if isinstance(html, str) else str(html))

    @app.template_filter('format_title')
    def format_title_filter(title: str | None) -> str:
        """格式化书名，去除重复书名号"""
        if not title:
            return ''
        clean = title.strip().strip('《》')
        return f'《{clean}》'

    @app.template_filter('clean_brackets')
    def clean_brackets_filter(text: str | None) -> str:
        """清理文本中所有重复的书名号（《《xxx》》 → 《xxx》）"""
        if not text:
            return ''
        text = re.sub(r'《{2,}', '《', text)
        text = re.sub(r'》{2,}', '》', text)
        return text

    @app.template_filter('is_valid_isbn')
    def is_valid_isbn_filter(value: str | None) -> bool:
        """校验字符串是否为合法 ISBN-10 或 ISBN-13（委托给 validate_isbn）"""
        from .utils.api_helpers import validate_isbn

        return validate_isbn(value)

    @app.template_filter('clean_isbn')
    def clean_isbn_filter(value: str | None) -> str:
        """去除 ISBN 中的空格和连字符"""
        if not value:
            return ''
        return re.sub(r'[\s\-]', '', value)

    @app.template_filter('is_invalid_publisher')
    def is_invalid_publisher_filter(value: str | None) -> bool:
        """检查出版社值是否为无效的分类名"""
        if not value:
            return True
        stripped = value.strip()
        if len(stripped) <= 3:
            return True
        invalid = {
            'unknown',
            'unknown publisher',
            'n/a',
            '',
            '精装小说',
            'hardcover fiction',
            '平装小说',
            'paperback fiction',
            '虚构类',
            'fiction',
            '非虚构类',
            'nonfiction',
            '青少年',
            'young adult',
            '儿童图书',
            "children's",
            'children',
            '建议读物',
            'advice',
            '如何做',
            'how-to',
            'how to',
            '图画书',
            'picture books',
            '图像小说',
            'graphic books',
            '系列图书',
            'series books',
            '综合类',
            'combined',
            '商业',
            'business',
            '科学',
            'science',
            '历史',
            'history',
            '政治',
            'politics',
            '旅行',
            'travel',
            '美食',
            'food',
            '健康',
            'health',
            '自助',
            'self-help',
            '宗教',
            'religion',
            '幽默',
            'humor',
            '体育',
            'sports',
            '家庭',
            'family',
            '关系',
            'relationships',
            '教育',
            'education',
        }
        return stripped.lower() in invalid


app = create_app(os.environ.get('FLASK_ENV', 'development'))
