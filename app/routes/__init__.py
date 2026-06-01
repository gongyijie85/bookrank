from .admin import admin_bp
from .analytics_bp import analytics_bp
from .api import api_bp
from .cron import cron_bp
from .health import health_bp
from .main import main_bp
from .new_books import new_books_bp
from .public_api import public_api_bp

__all__ = ['admin_bp', 'analytics_bp', 'api_bp', 'cron_bp', 'health_bp', 'main_bp', 'new_books_bp', 'public_api_bp']
