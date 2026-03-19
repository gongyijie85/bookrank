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
        'app_running': True,
        'flask_version': 'unknown',
        'environment': 'unknown'
    }
    
    try:
        # 检查 Flask 版本
        from flask import __version__
        checks['flask_version'] = __version__
        
        # 检查环境
        checks['environment'] = current_app.config.get('ENV', 'unknown')
        
        # 尝试轻量级数据库检查（可选）
        try:
            from ..models.database import db
            db.session.execute('SELECT 1')
            checks['database'] = 'connected'
        except Exception as e:
            checks['database'] = f'error: {str(e)}'
        
        status = 'healthy'
        status_code = 200
        
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
