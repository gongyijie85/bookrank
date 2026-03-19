"""
健康检查路由 - Render 专用
提供详细的健康检查端点，用于 UptimeRobot 等监控服务
"""
import logging
from flask import Blueprint, jsonify, current_app

health_bp = Blueprint('health', __name__)
logger = logging.getLogger(__name__)


@health_bp.route('/health')
def health_check():
    """
    简单健康检查 - 用于 UptimeRobot 等监控
    快速响应，不做耗时检查
    """
    return jsonify({
        'success': True,
        'status': 'healthy',
        'service': 'book-rank-api'
    }), 200


@health_bp.route('/health/detailed')
def detailed_health_check():
    """
    详细健康检查 - 检查所有服务和连接
    用于手动诊断问题
    """
    checks = {
        'database': False,
        'cache': False,
        'awards_count': 0,
        'books_count': 0,
        'publishers_count': 0,
        'memory_usage': 'unknown'
    }
    
    try:
        # 检查数据库连接
        from ..models.database import db
        db.session.execute('SELECT 1')
        checks['database'] = True
        
        # 检查数据量
        from ..models.schemas import Award, BookMetadata
        from ..models.new_book import Publisher
        
        checks['awards_count'] = Award.query.count()
        checks['books_count'] = BookMetadata.query.count()
        checks['publishers_count'] = Publisher.query.count()
        
        # 检查缓存服务
        cache_service = current_app.extensions.get('book_service')
        if cache_service and hasattr(cache_service, '_cache'):
            checks['cache'] = True
        
        # 检查内存使用
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            checks['memory_usage'] = f"{memory_mb:.2f} MB"
        except ImportError:
            checks['memory_usage'] = "psutil not installed"
        except Exception as e:
            checks['memory_usage'] = str(e)
        
        status = 'healthy' if checks['database'] else 'unhealthy'
        status_code = 200 if status == 'healthy' else 503
        
    except Exception as e:
        status = 'unhealthy'
        status_code = 503
        checks['error'] = str(e)
        logger.error(f"Health check failed: {e}", exc_info=True)
    
    return jsonify({
        'success': status == 'healthy',
        'status': status,
        'service': 'book-rank-api',
        'checks': checks
    }), status_code


@health_bp.route('/health/ready')
def readiness_check():
    """
    就绪检查 - 用于 Kubernetes/容器编排
    检查应用是否已准备好接收流量
    """
    try:
        from ..models.database import db
        db.session.execute('SELECT 1')
        
        return jsonify({
            'success': True,
            'status': 'ready'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'not_ready',
            'error': str(e)
        }), 503
