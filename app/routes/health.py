"""
健康检查路由 - Render 专用
提供详细的健康检查端点，用于 UptimeRobot 等监控服务
"""

import logging

from flask import Blueprint, make_response

from ..services.health_service import HealthService

health_bp = Blueprint('health', __name__)
logger = logging.getLogger(__name__)

_NO_CACHE_HEADERS = {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0',
}


def _json_response(body: str, status: int = 200):
    """构建带 no-cache 头的 JSON 响应"""
    response = make_response(body, status)
    response.headers.update(_NO_CACHE_HEADERS)
    return response


@health_bp.route('/health')
def health_check():
    """简单健康检查 - 用于 UptimeRobot 等监控"""
    return _json_response('{"success":true,"status":"healthy","service":"book-rank-api"}')


@health_bp.route('/health/detailed')
def detailed_health_check():
    """详细健康检查 - 用于手动诊断问题"""
    return _json_response(
        '{"success":true,"status":"healthy","service":"book-rank-api","checks":{"app_running":true,"status":"ok"}}'
    )


@health_bp.route('/health/ready')
def readiness_check():
    """就绪检查 - 快速检测数据库连通性（不重试，减少延迟）"""
    try:
        HealthService.check_database()
        return _json_response('{"success":true,"status":"ready"}')
    except Exception as e:
        logger.warning(f'Readiness check failed: {e}')
        return _json_response(
            '{"success":false,"status":"not_ready","error":"database_unavailable"}',
            status=503,
        )
