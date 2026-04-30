import logging
import os
from pathlib import Path

from flask import Flask, request
from flask_cors import CORS

from .config import config
from .models import db, init_db
from .routes import api_bp, main_bp, public_api_bp, new_books_bp, health_bp, analytics_bp
from .initialization import init_awards_data, init_sample_books

PROJECT_ROOT = Path(__file__).parent.parent


def create_app(config_name='default'):
    """
    应用工厂函数

    Args:
        config_name: 配置名称 ('development', 'production', 'testing')

    Returns:
        Flask应用实例
    """
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / 'templates'),
        static_folder=str(PROJECT_ROOT / 'static')
    )

    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    _init_extensions(app, config_name)
    _register_blueprints(app)
    _register_error_handlers(app)
    _configure_logging(app)
    _apply_security_headers(app)
    _register_jinja_filters(app)

    if config_name == 'production':
        _enable_rate_limiting(app)

    return app


def _init_extensions(app, config_name: str):
    """初始化Flask扩展"""
    if config_name == 'production':
        cors_origins = app.config.get('CORS_ORIGINS', [])
        if not cors_origins:
            cors_origins = []
        cors_methods = ['GET', 'POST', 'OPTIONS']
    else:
        cors_origins = '*'
        cors_methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": cors_origins,
                "methods": cors_methods,
                "allow_headers": ["Content-Type", "Authorization"],
                "expose_headers": ["Content-Length", "Content-Disposition"],
                "max_age": 3600,
                "supports_credentials": True
            }
        },
        supports_credentials=True
    )

    init_db(app)

    # 邮件扩展（可选，未安装时跳过）
    try:
        from flask_mail import Mail
        app.extensions['mail'] = Mail(app)
    except ImportError:
        app.logger.info("Flask-Mail 未安装，邮件功能已禁用")

    _setup_db_event_listeners(app)

    if config_name != 'testing':
        _auto_init_awards(app)

    from .setup import init_services
    init_services(app)


def _auto_init_awards(app):
    """自动初始化奖项数据"""
    with app.app_context():
        init_awards_data(app)
        init_sample_books(app)


def _register_blueprints(app):
    """注册蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(public_api_bp)
    app.register_blueprint(new_books_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(analytics_bp)


def _register_error_handlers(app):
    """注册全局错误处理器"""

    @app.errorhandler(400)
    def bad_request(error):
        return {'success': False, 'message': 'Bad request'}, 400

    @app.errorhandler(404)
    def not_found(error):
        return {'success': False, 'message': 'Resource not found'}, 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return {'success': False, 'message': 'Method not allowed'}, 405

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return {'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logging.error(f"Internal error: {error}", exc_info=True)
        return {'success': False, 'message': 'Internal server error'}, 500


def _setup_db_event_listeners(app):
    """设置数据库事件监听器，处理 Render PostgreSQL 休眠恢复"""
    from sqlalchemy import event
    from sqlalchemy.exc import DisconnectionError
    from sqlalchemy.pool import Pool

    @event.listens_for(Pool, "checkout")
    def handle_checkout(dbapi_connection, connection_record, connection_proxy):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
        except Exception as e:
            app.logger.warning(f"数据库连接检查失败: {e}")
            raise DisconnectionError("Connection check failed")

    @event.listens_for(Pool, "checkin")
    def handle_checkin(dbapi_connection, connection_record):
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception as e:
            app.logger.warning(f"连接归还时回滚失败: {e}")

    @event.listens_for(Pool, "connect")
    def on_connect(dbapi_connection, connection_record):
        app.logger.debug("数据库新连接已建立")
        if hasattr(dbapi_connection, 'set_session'):
            try:
                dbapi_connection.set_session(autocommit=False, timezone='UTC')
            except Exception as e:
                app.logger.warning(f"设置连接参数失败: {e}")

    @event.listens_for(Pool, "reset")
    def on_reset(dbapi_connection, connection_record):
        try:
            if hasattr(dbapi_connection, 'rollback'):
                dbapi_connection.rollback()
        except Exception as e:
            app.logger.warning(f"连接重置时回滚失败: {e}")


def _configure_logging(app):
    """配置日志"""
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)

        app.logger.handlers.clear()
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.propagate = False

        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)


def _apply_security_headers(app):
    """应用安全响应头和静态资源缓存"""
    @app.after_request
    def add_security_headers(response):
        security_headers = {
            'X-Frame-Options': 'SAMEORIGIN',
            'X-XSS-Protection': '1; mode=block',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Server': 'BookRank',
            'Content-Security-Policy': (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com 'unsafe-inline'; "
                "img-src 'self' data: https://*.nytimes.com https://*.amazon.com https://*.amazonaws.com https://books.google.com https://covers.openlibrary.org https://openlibrary.org https://*.penguinrandomhouse.com https://*.harpercollins.com https://*.macmillan.com https://*.simonandschuster.com https://*.hachettebookgroup.com; "
                "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://fonts.gstatic.com; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "frame-src 'none'; "
                "object-src 'none';"
            ),
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()'
        }

        for header, value in security_headers.items():
            response.headers[header] = value

        if app.config.get('ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

        request_path = request.path if request else ''
        if request_path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=2592000, immutable'

        return response


def _enable_rate_limiting(app):
    """启用API速率限制"""
    from flask import make_response
    from .utils.rate_limiter import get_rate_limiter

    rate_limiter = get_rate_limiter(
        max_requests=app.config.get('API_RATE_LIMIT', 60),
        window_seconds=app.config.get('API_RATE_LIMIT_WINDOW', 60)
    )

    @app.before_request
    def rate_limit_requests():
        if (request.path.startswith('/static/') or
            request.path.startswith('/health/') or
            not request.path.startswith('/api/')):
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


def _register_jinja_filters(app):
    """注册自定义Jinja2过滤器"""
    import mistune
    
    @app.template_filter('markdown')
    def markdown_filter(text):
        """将Markdown文本转换为HTML"""
        if not text:
            return ''
        return mistune.html(text)

    @app.template_filter('format_title')
    def format_title_filter(title):
        """格式化书名，去除重复书名号并清理翻译污染"""
        if not title:
            return ''
        text = title.strip()
        # 去除markdown标记
        text = re.sub(r'\*{1,2}|_{1,2}|`', '', text)
        # 有换行只取第一行
        if '\n' in text:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if lines:
                text = lines[0]
        # 提取《》内内容
        book_match = re.search(r'《([^》]+)》', text)
        if book_match:
            text = book_match.group(1).strip()
        else:
            # 清理末尾作者名+"译"
            text = re.sub(r'\s*[\u4e00-\u9fff]{1,4}(?:·[\u4e00-\u9fff]{1,4})*译?\s*$', '', text).strip()
            # 清理书名后长描述
            text = re.sub(r'[。，；].*$', '', text).strip()
        text = text.strip('《》').strip()
        return f'《{text}》' if text else ''

    @app.template_filter('clean_brackets')
    def clean_brackets_filter(text):
        """清理文本中所有重复的书名号和markdown（《《xxx》》 → 《xxx》，**《xxx》** → 《xxx》）"""
        if not text:
            return text
        text = re.sub(r'《{2,}', '《', text)
        text = re.sub(r'》{2,}', '》', text)
        text = re.sub(r'\*\*《([^》]+)》\*\*', r'《\1》', text)
        text = re.sub(r'\*《([^》]+)》\*', r'《\1》', text)
        return text


app = create_app(os.environ.get('FLASK_ENV', 'development'))
