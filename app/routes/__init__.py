from .api import api_bp
from .main import main_bp
from .public_api import public_api_bp
from .new_books import new_books_bp
from .health import health_bp
from .analytics_bp import analytics_bp
from .admin import admin_bp

__all__ = ['api_bp', 'main_bp', 'public_api_bp', 'new_books_bp', 'health_bp', 'analytics_bp', 'admin_bp']
