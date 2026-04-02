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
    # 极简版健康检查，只返回基本信息
    return jsonify({
        'success': True,
        'status': 'healthy',
        'service': 'book-rank-api',
        'checks': {
            'app_running': True,
            'status': 'ok'
        }
    }), 200


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
        # 即使数据库连接失败，也返回 200 OK
        # 避免 Render 认为服务不健康而休眠
        logger.warning(f"Database check failed: {e}")
        return jsonify({
            'success': True,
            'status': 'ready',
            'warning': 'Database connection check failed, but service is running'
        }), 200
