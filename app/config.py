import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """基础配置类"""

    BASE_DIR = Path(__file__).parent.parent

    # 安全配置
    SECRET_KEY: str = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = 'Lax'
    PERMANENT_SESSION_LIFETIME: int = 3600 * 24 * 7  # 7天

    # JSON 配置
    JSON_SORT_KEYS: bool = False  # 不排序键以提高性能
    JSONIFY_PRETTYPRINT_REGULAR: bool = False  # 生产环境不美化JSON
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB 最大请求体

    # 数据库配置 - 支持 Render PostgreSQL
    # Render 使用 postgres:// 但 SQLAlchemy 需要 postgresql://
    _db_url = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "bestsellers.db"}')
    SQLALCHEMY_DATABASE_URI: str = _db_url.replace('postgres://', 'postgresql://', 1) if _db_url.startswith('postgres://') else _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = os.environ.get('SQLALCHEMY_ECHO', 'false').lower() == 'true'
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }

    # API 配置
    NYT_API_KEY: str | None = os.environ.get('NYT_API_KEY')
    GOOGLE_API_KEY: str | None = os.environ.get('GOOGLE_API_KEY')
    
    # 智谱AI配置（用于翻译）
    ZHIPU_API_KEY: str | None = os.environ.get('ZHIPU_API_KEY')

    # 缓存配置
    CACHE_TYPE: str = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT: int = int(os.environ.get('CACHE_TTL', 3600))
    MEMORY_CACHE_TTL: int = int(os.environ.get('MEMORY_CACHE_TTL', 300))

    CACHE_DIR: Path = BASE_DIR / 'cache'
    IMAGE_CACHE_DIR: Path = CACHE_DIR / 'images'

    # 限流配置
    API_RATE_LIMIT: int = int(os.environ.get('API_RATE_LIMIT', 20))
    API_RATE_LIMIT_WINDOW: int = 60

    # 并发配置
    MAX_WORKERS: int = int(os.environ.get('MAX_WORKERS', 4))

    # 超时配置
    API_TIMEOUT: int = int(os.environ.get('API_TIMEOUT', 15))
    IMAGE_TIMEOUT: int = int(os.environ.get('IMAGE_TIMEOUT', 10))

    # 分类配置
    CATEGORIES: dict[str, str] = {
        # 小说类
        'hardcover-fiction': '精装小说',
        'trade-fiction-paperback': '平装小说',
        # 非虚构类
        'hardcover-nonfiction': '精装非虚构',
        'paperback-nonfiction': '平装非虚构',
        # 其他
        'advice-how-to-and-miscellaneous': '建议、方法与杂项',
        'graphic-books-and-manga': '漫画与绘本',
        # 儿童与青少年
        'childrens-middle-grade-hardcover': '儿童中级精装本',
        'young-adult-hardcover': '青少年精装本',
    }

    # API 端点配置
    NYT_API_BASE_URL: str = 'https://api.nytimes.com/svc/books/v3/lists/current'
    GOOGLE_BOOKS_API_URL: str = 'https://www.googleapis.com/books/v1/volumes'

    # 语言映射
    LANGUAGE_MAP: dict[str, str] = {
        'en': '英语', 'zh': '中文', 'ja': '日语', 'ko': '韩语',
        'fr': '法语', 'de': '德语', 'es': '西班牙语', 'ru': '俄语'
    }

    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        cls.CACHE_DIR.mkdir(exist_ok=True, mode=0o755)
        cls.IMAGE_CACHE_DIR.mkdir(exist_ok=True, mode=0o755)


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG: bool = True
    TESTING: bool = False
    SQLALCHEMY_ECHO: bool = True
    # 开发环境使用宽松的会话配置
    SESSION_COOKIE_SECURE: bool = False


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG: bool = False
    TESTING: bool = False

    # 生产环境强制使用安全会话
    SESSION_COOKIE_SECURE: bool = True

    # CORS 配置 - 生产环境限制允许的来源
    CORS_ORIGINS: list = os.environ.get('CORS_ORIGINS', '').split(',') if os.environ.get('CORS_ORIGINS') else []

    # 缓存优化
    CACHE_TYPE: str = 'simple'

    # 数据库连接池优化
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'echo': False,
    }

    # 响应压缩
    JSONIFY_PRETTYPRINT_REGULAR: bool = False

    # 启用安全响应头
    from flask import Flask
    @staticmethod
    def apply_security_headers(app: Flask):
        """应用安全响应头"""
        @app.after_request
        def add_security_headers(response):
            # 防止点击劫持
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            # XSS 防护
            response.headers['X-XSS-Protection'] = '1; mode=block'
            # 内容类型 sniffing 防护
            response.headers['X-Content-Type-Options'] = 'nosniff'
            # 引用来源策略
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            # CSP（可根据需要调整）
            response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' https: data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
            return response


class TestingConfig(Config):
    """测试环境配置"""
    DEBUG: bool = True
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED: bool = False
    # 测试环境使用宽松的安全配置
    SESSION_COOKIE_SECURE: bool = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
