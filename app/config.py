import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.pool import StaticPool

BASE_DIR: Path = Path(__file__).parent.parent
load_dotenv(BASE_DIR / '.env')


def _build_database_uri() -> str:
    """Build the database URI for local SQLite or hosted PostgreSQL."""
    db_url = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "bestsellers.db"}')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    return _ensure_supabase_sslmode(db_url)


def _ensure_supabase_sslmode(db_url: str) -> str:
    """Supabase PostgreSQL connections should use SSL."""
    lowered = db_url.lower()
    is_postgres = lowered.startswith(('postgresql://', 'postgresql+psycopg2://'))
    is_supabase = 'supabase.co' in lowered or 'pooler.supabase.com' in lowered
    if not (is_postgres and is_supabase) or 'sslmode=' in lowered:
        return db_url

    separator = '&' if '?' in db_url else '?'
    return f'{db_url}{separator}sslmode=require'


class Config:
    """基础配置类"""

    BASE_DIR: Path = BASE_DIR
    # 网站基础 URL（用于邮件中构建完整图片链接）
    BASE_URL: str = os.environ.get('BASE_URL', '')

    SECRET_KEY: str = os.environ.get('SECRET_KEY', '')
    ADMIN_SECRET: str = os.environ.get('ADMIN_SECRET', '')
    CRON_SECRET: str = os.environ.get('CRON_SECRET', '')
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = 'Lax'

    _SECONDS_PER_DAY: int = 86400
    _SESSION_LIFETIME_DAYS: int = 7
    PERMANENT_SESSION_LIFETIME: int = _SECONDS_PER_DAY * _SESSION_LIFETIME_DAYS

    JSON_SORT_KEYS: bool = False
    JSONIFY_PRETTYPRINT_REGULAR: bool = False
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024

    SQLALCHEMY_DATABASE_URI: str = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = os.environ.get('SQLALCHEMY_ECHO', 'false').lower() == 'true'
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, object] = {
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

    NYT_CATEGORY_UPDATE_FREQUENCIES: dict[str, str] = {
        'hardcover-fiction': 'weekly',
        'trade-fiction-paperback': 'weekly',
        'hardcover-nonfiction': 'weekly',
        'paperback-nonfiction-monthly': 'monthly',
        'advice-how-to-and-miscellaneous': 'weekly',
        'graphic-books-and-manga': 'monthly',
        'childrens-middle-grade-hardcover': 'weekly',
        'young-adult-hardcover': 'weekly',
    }

    NYT_API_BASE_URL: str = 'https://api.nytimes.com/svc/books/v3/lists/current'
    NYT_LIST_NAMES_URL: str = 'https://api.nytimes.com/svc/books/v3/lists/names.json'
    GOOGLE_BOOKS_API_URL: str = 'https://www.googleapis.com/books/v1/volumes'

    # 外部 API 缓存 TTL（秒）
    NYT_CACHE_TTL: int = _SECONDS_PER_DAY * 7  # NYT 数据每周更新
    GOOGLE_BOOKS_CACHE_TTL: int = _SECONDS_PER_DAY  # Google Books 缓存 24 小时
    OPEN_LIBRARY_CACHE_TTL: int = _SECONDS_PER_DAY * 3  # Open Library 缓存 3 天

    # 智谱 AI 翻译模型
    ZHIPU_TRANSLATION_MODEL: str = 'glm-4.7-flash'

    # BookService 默认缓存 TTL（秒）
    BOOK_SERVICE_CACHE_TTL: int = _SECONDS_PER_DAY  # 24 小时

    # NYT 排行榜自动刷新间隔（天）；刷新后会补充资料、翻译并写入语言包
    NYT_RANKING_SYNC_DAYS: int = int(os.environ.get('NYT_RANKING_SYNC_DAYS', 7))

    # 内存缓存最大条目数
    MEMORY_CACHE_MAX_SIZE: int = 1000

    LANGUAGE_MAP: dict[str, str] = {
        'en': '英语',
        'zh': '中文',
        'ja': '日语',
        'ko': '韩语',
        'fr': '法语',
        'de': '德语',
        'es': '西班牙语',
        'ru': '俄语',
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
    MAIL_ENABLED: bool = os.environ.get('MAIL_ENABLED', 'true').lower() == 'true'

    # Flask-Babel 配置
    BABEL_DEFAULT_LOCALE: str = 'en'
    BABEL_DEFAULT_TIMEZONE: str = 'UTC'
    BABEL_TRANSLATION_DIRECTORIES: str = str(BASE_DIR / 'translations')

    @classmethod
    def init_app(cls, app: Any) -> None:
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

    # 开发环境允许使用固定的 dev key（仅限本地开发）
    _DEV_SECRET_KEY = 'dev-secret-key-for-local-development-only-do-not-use-in-production'
    SECRET_KEY: str = os.environ.get('SECRET_KEY', _DEV_SECRET_KEY)


class ProductionConfig(Config):
    """生产环境配置（适配 Render Web Service + 外部 PostgreSQL/Supabase）"""

    DEBUG: bool = False
    TESTING: bool = False
    SESSION_COOKIE_SECURE: bool = True

    # SECRET_KEY 从环境变量读取（若为空则在 init_app 时校验）
    SECRET_KEY: str = os.environ.get('SECRET_KEY', '')

    # CORS_ORIGINS 必须明确设置，空列表会导致 CORS 完全阻止跨域请求
    CORS_ORIGINS: list[str] = os.environ.get('CORS_ORIGINS', '').split(',') if os.environ.get('CORS_ORIGINS') else []

    @classmethod
    def init_app(cls, app: Any) -> None:
        """生产环境初始化：强制校验 SECRET_KEY"""
        super().init_app(app)
        if not cls.SECRET_KEY:
            raise ValueError(
                '生产环境必须设置 SECRET_KEY 环境变量！\n'
                '生成强随机密钥: python -c "import secrets; print(secrets.token_hex(32))"'
            )

    # 内存缓存（当前部署无 Redis）
    CACHE_TYPE: str = 'simple'
    CACHE_DEFAULT_TIMEOUT: int = 3600  # 缩短缓存时间减少内存占用
    MEMORY_CACHE_TTL: int = 300

    # 数据库连接池优化：保持较小连接数，适配 Supabase/Render 等托管 Postgres。
    # 注意：pool_size + max_overflow 不要超过 3，避免连接池耗尽。
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, object] = {
        'pool_size': 2,  # 基础连接池（原为1，避免并发查询时阻塞）
        'max_overflow': 1,  # 最多 1 个临时连接
        'pool_timeout': 15,  # 等待时间（适当放宽避免超时）
        'pool_recycle': 600,  # 每 10 分钟回收连接（pool_pre_ping 已保证活性）
        'pool_pre_ping': True,  # 连接前 ping 检测
        'echo': False,
        'connect_args': {
            'connect_timeout': 5,  # 缩短连接超时
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
    SECRET_KEY: str = 'test-secret-key-for-unit-tests-only'
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED: bool = False
    SESSION_COOKIE_SECURE: bool = False
    API_RATE_LIMIT: int = 10000
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, object] = {
        'poolclass': StaticPool,
        'connect_args': {'check_same_thread': False},
    }


config: dict[str, type[Config]] = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig,
}
