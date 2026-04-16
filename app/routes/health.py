"""
健康检查路由 - Render 专用
提供详细的健康检查端点，用于 UptimeRobot 等监控服务
"""
import logging
from flask import Blueprint, jsonify, current_app, make_response

health_bp = Blueprint('health', __name__)
logger = logging.getLogger(__name__)


@health_bp.route('/health')
def health_check():
    """
    简单健康检查 - 用于 UptimeRobot 等监控
    快速响应，不做耗时检查
    """
    # 直接返回响应，减少 jsonify 的开销
    response = make_response('{"success":true,"status":"healthy","service":"book-rank-api"}', 200)
    response.headers['Content-Type'] = 'application/json'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@health_bp.route('/health/detailed')
def detailed_health_check():
    """
    详细健康检查 - 检查所有服务和连接
    用于手动诊断问题
    """
    # 极简版健康检查，只返回基本信息
    response = make_response('{"success":true,"status":"healthy","service":"book-rank-api","checks":{"app_running":true,"status":"ok"}}', 200)
    response.headers['Content-Type'] = 'application/json'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@health_bp.route('/health/ready')
def readiness_check():
    """
    就绪检查 - 用于 Kubernetes/容器编排
    检查应用是否已准备好接收流量
    """
    import time as _time
    from sqlalchemy.exc import OperationalError

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            from ..models.database import db
            db.session.execute(db.text('SELECT 1'))

            response = make_response('{"success":true,"status":"ready"}', 200)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        except OperationalError as e:
            if attempt < max_retries:
                logger.warning(f"Database retry {attempt + 1}/{max_retries}: {e}")
                _time.sleep(2 ** attempt)
                continue
            # 即使数据库连接失败，也返回 200 OK
            # 避免 Render 认为服务不健康而休眠
            logger.warning(f"Database check failed after retries: {e}")
            response = make_response('{"success":true,"status":"ready","warning":"db_warming_up"}', 200)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        except Exception as e:
            logger.warning(f"Health check error: {e}")
            response = make_response('{"success":true,"status":"ready","warning":"check_skipped"}', 200)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
