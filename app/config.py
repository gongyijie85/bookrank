import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / '.env')


def _build_database_uri() -> str:
    """构建数据库URI，自动处理 Render 的 postgres:// 前缀"""
    db_url = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "bestsellers.db"}')
    if db_url.startswith('postgres://'):
        return db_url.replace('postgres://', 'postgresql://', 1)
    return db_url


class Config:
    """基础配置类"""

    BASE_DIR = BASE_DIR
    # 网站基础 URL（用于邮件中构建完整图片链接）
    BASE_URL: str = os.environ.get('BASE_URL', '')

    SECRET_KEY: str = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = 'Lax'
    PERMANENT_SESSION_LIFETIME: int = 3600 * 24 * 7

    JSON_SORT_KEYS: bool = False
    JSONIFY_PRETTYPRINT_REGULAR: bool = False
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024

    SQLALCHEMY_DATABASE_URI: str = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = os.environ.get('SQLALCHEMY_ECHO', 'false').lower() == 'true'
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }

    NYT_API_KEY: str | None = os.environ.get('NYT_API_KEY')
    GOOGLE_API_KEY: str | None = os.environ.get('GOOGLE_API_KEY')
    ZHIPU_API_KEY: str | None = os.environ.get('ZHIPU_API_KEY')

    CACHE_TYPE: str = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT: int = int(os.environ.get('CACHE_TTL', 7200))
    MEMORY_CACHE_TTL: int = int(os.environ.get('MEMORY_CACHE_TTL', 600))

    CACHE_DIR: Path = BASE_DIR / 'cache'
    IMAGE_CACHE_DIR: Path = CACHE_DIR / 'images'

    API_RATE_LIMIT: int = int(os.environ.get('API_RATE_LIMIT', 100))
    API_RATE_LIMIT_WINDOW: int = 60

    MAX_WORKERS: int = int(os.environ.get('MAX_WORKERS', 4))

    API_TIMEOUT: int = int(os.environ.get('API_TIMEOUT', 15))
    IMAGE_TIMEOUT: int = int(os.environ.get('IMAGE_TIMEOUT', 10))

    CATEGORIES: dict[str, str] = {
        'hardcover-fiction': '精装小说',
        'trade-fiction-paperback': '平装小说',
        'hardcover-nonfiction': '精装非虚构',
        'paperback-nonfiction-monthly': '平装非虚构',
        'advice-how-to-and-miscellaneous': '建议、方法与杂项',
        'graphic-books-and-manga': '漫画与绘本',
        'childrens-middle-grade-hardcover': '儿童中级精装本',
        'young-adult-hardcover': '青少年精装本',
    }

    NYT_API_BASE_URL: str = 'https://api.nytimes.com/svc/books/v3/lists/current'
    GOOGLE_BOOKS_API_URL: str = 'https://www.googleapis.com/books/v1/volumes'

    LANGUAGE_MAP: dict[str, str] = {
        'en': '英语', 'zh': '中文', 'ja': '日语', 'ko': '韩语',
        'fr': '法语', 'de': '德语', 'es': '西班牙语', 'ru': '俄语'
    }

    MAIL_SERVER: str = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT: int = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS: bool = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL: bool = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME: str | None = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD: str | None = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER: str = os.environ.get('MAIL_DEFAULT_SENDER', 'bookrank@example.com')
    MAIL_MAX_EMAILS: int | None = None
    MAIL_SUPPRESS_SEND: bool = os.environ.get('MAIL_SUPPRESS_SEND', 'false').lower() == 'true'
    MAIL_RECIPIENTS: str = os.environ.get('MAIL_RECIPIENTS', '')

    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        cls.CACHE_DIR.mkdir(exist_ok=True, mode=0o755)
        cls.IMAGE_CACHE_DIR.mkdir(exist_ok=True, mode=0o755)

        _max_emails = os.environ.get('MAIL_MAX_EMAILS')
        if _max_emails:
            try:
                cls.MAIL_MAX_EMAILS = int(_max_emails)
            except (ValueError, TypeError):
                cls.MAIL_MAX_EMAILS = None


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG: bool = True
    TESTING: bool = False
    SQLALCHEMY_ECHO: bool = True
    SESSION_COOKIE_SECURE: bool = False


class ProductionConfig(Config):
    """生产环境配置（针对 Render 免费版优化：512MB 内存、97 连接 PostgreSQL）"""
    DEBUG: bool = False
    TESTING: bool = False
    SESSION_COOKIE_SECURE: bool = True

    CORS_ORIGINS: list = os.environ.get('CORS_ORIGINS', '').split(',') if os.environ.get('CORS_ORIGINS') else []

    # 内存缓存（免费版 Render 无 Redis）
    CACHE_TYPE: str = 'simple'
    CACHE_DEFAULT_TIMEOUT: int = 3600  # 缩短缓存时间减少内存占用
    MEMORY_CACHE_TTL: int = 300

    # 数据库连接池优化（免费 PostgreSQL 限制 97 连接）
    # 注意：pool_size + max_overflow 不要超过 3，避免连接池耗尽
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        'pool_size': 2,           # 基础连接池（原为1，避免并发查询时阻塞）
        'max_overflow': 1,        # 最多 1 个临时连接
        'pool_timeout': 15,       # 等待时间（适当放宽避免超时）
        'pool_recycle': 180,      # 更频繁回收连接
        'pool_pre_ping': True,    # 连接前 ping 检测
        'echo': False,
        'connect_args': {
            'connect_timeout': 5,     # 缩短连接超时
            'options': '-c statement_timeout=15000',  # 15 秒查询超时
        },
    }

    # 减少并发工作线程
    MAX_WORKERS: int = 2  # 原为 4

    JSONIFY_PRETTYPRINT_REGULAR: bool = False


class TestingConfig(Config):
    """测试环境配置"""
    DEBUG: bool = True
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED: bool = False
    SESSION_COOKIE_SECURE: bool = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
