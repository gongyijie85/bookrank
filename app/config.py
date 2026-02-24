import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """基础配置类"""
    
    BASE_DIR = Path(__file__).parent.parent
    
    SECRET_KEY: str = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        'DATABASE_URL', 
        f'sqlite:///{BASE_DIR / "bestsellers.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = os.environ.get('SQLALCHEMY_ECHO', 'false').lower() == 'true'
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }
    
    NYT_API_KEY: str | None = os.environ.get('NYT_API_KEY')
    GOOGLE_API_KEY: str | None = os.environ.get('GOOGLE_API_KEY')
    
    CACHE_TYPE: str = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT: int = int(os.environ.get('CACHE_TTL', 3600))
    MEMORY_CACHE_TTL: int = int(os.environ.get('MEMORY_CACHE_TTL', 300))
    
    CACHE_DIR: Path = BASE_DIR / 'cache'
    IMAGE_CACHE_DIR: Path = CACHE_DIR / 'images'
    
    API_RATE_LIMIT: int = int(os.environ.get('API_RATE_LIMIT', 20))
    API_RATE_LIMIT_WINDOW: int = 60
    
    MAX_WORKERS: int = int(os.environ.get('MAX_WORKERS', 4))
    
    API_TIMEOUT: int = int(os.environ.get('API_TIMEOUT', 15))
    IMAGE_TIMEOUT: int = int(os.environ.get('IMAGE_TIMEOUT', 10))
    
    CATEGORIES: dict[str, str] = {
        'hardcover-fiction': '精装小说',
        'hardcover-nonfiction': '精装非虚构',
        'trade-fiction-paperback': '平装小说',
        'paperback-nonfiction': '平装非虚构'
    }
    
    NYT_API_BASE_URL: str = 'https://api.nytimes.com/svc/books/v3/lists/current'
    GOOGLE_BOOKS_API_URL: str = 'https://www.googleapis.com/books/v1/volumes'
    
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


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG: bool = False
    TESTING: bool = False
    
    CACHE_TYPE: str = 'simple'
    
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
    }


class TestingConfig(Config):
    """测试环境配置"""
    DEBUG: bool = True
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED: bool = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
