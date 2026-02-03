import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量（必须在类定义之前）
load_dotenv()


class Config:
    """基础配置类"""
    
    # 项目根目录
    BASE_DIR = Path(__file__).parent.parent
    
    # Flask配置
    SECRET_KEY: str = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        'DATABASE_URL', 
        f'sqlite:///{BASE_DIR / "bestsellers.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    
    # API密钥
    NYT_API_KEY: Optional[str] = os.environ.get('NYT_API_KEY')
    GOOGLE_API_KEY: Optional[str] = os.environ.get('GOOGLE_API_KEY')
    
    # 缓存配置
    CACHE_TYPE: str = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT: int = int(os.environ.get('CACHE_TTL', 3600))
    MEMORY_CACHE_TTL: int = int(os.environ.get('MEMORY_CACHE_TTL', 300))
    
    # 缓存目录
    CACHE_DIR: Path = BASE_DIR / 'cache'
    IMAGE_CACHE_DIR: Path = CACHE_DIR / 'images'
    
    # API限流配置
    # 增加限流阈值以适应多分类请求（4个分类 + 搜索等操作）
    API_RATE_LIMIT: int = int(os.environ.get('API_RATE_LIMIT', 20))
    API_RATE_LIMIT_WINDOW: int = 60  # 秒
    
    # 并发配置
    MAX_WORKERS: int = int(os.environ.get('MAX_WORKERS', 4))
    
    # 请求超时配置
    API_TIMEOUT: int = int(os.environ.get('API_TIMEOUT', 15))
    IMAGE_TIMEOUT: int = int(os.environ.get('IMAGE_TIMEOUT', 10))
    
    # 分类配置
    CATEGORIES: dict[str, str] = {
        'hardcover-fiction': '精装小说',
        'hardcover-nonfiction': '精装非虚构',
        'trade-fiction-paperback': '平装小说',
        'paperback-nonfiction': '平装非虚构'
    }
    
    # API基础URL
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
        # 确保缓存目录存在
        cls.CACHE_DIR.mkdir(exist_ok=True, mode=0o755)
        cls.IMAGE_CACHE_DIR.mkdir(exist_ok=True, mode=0o755)


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG: bool = True
    TESTING: bool = False


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG: bool = False
    TESTING: bool = False
    
    # 生产环境使用内存缓存（免费套餐通常不包含 Redis）
    CACHE_TYPE: str = 'simple'
    
    # 数据库配置 - Render 会自动提供 DATABASE_URL
    # 格式: postgresql://user:password@host:port/database
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,
    }


class TestingConfig(Config):
    """测试环境配置"""
    DEBUG: bool = True
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED: bool = False


# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
