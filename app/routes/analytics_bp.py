import logging

from flask import Blueprint, request

from app.services.analytics_service import get_analytics_service
from app.utils.api_helpers import APIResponse

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__)


def _clamp(value: int, min_val: int, max_val: int) -> int:
    return min(max(min_val, value), max_val)


@analytics_bp.route('/api/analytics/report-views')
def get_report_views():
    """获取周报阅读统计数据"""
    try:
        days = _clamp(request.args.get('days', 30, type=int), 1, 365)
        analytics_service = get_analytics_service()
        stats = analytics_service.get_report_view_stats(days)
        return APIResponse.success(data=stats)
    except Exception as e:
        logger.error(f"获取周报统计失败: {e}", exc_info=True)
        return APIResponse.error(str(e), 500)


@analytics_bp.route('/api/analytics/user-behavior')
def get_user_behavior():
    """获取用户行为统计数据"""
    try:
        days = _clamp(request.args.get('days', 30, type=int), 1, 365)
        analytics_service = get_analytics_service()
        stats = analytics_service.get_user_behavior_stats(days)
        return APIResponse.success(data=stats)
    except Exception as e:
        logger.error(f"获取用户行为统计失败: {e}", exc_info=True)
        return APIResponse.error(str(e), 500)


@analytics_bp.route('/api/analytics/daily-stats')
def get_daily_stats():
    """获取每日统计数据"""
    try:
        days = _clamp(request.args.get('days', 30, type=int), 1, 365)
        analytics_service = get_analytics_service()
        stats = analytics_service.get_daily_stats(days)
        return APIResponse.success(data=stats)
    except Exception as e:
        logger.error(f"获取每日统计失败: {e}", exc_info=True)
        return APIResponse.error(str(e), 500)


@analytics_bp.route('/api/analytics/top-reports')
def get_top_reports():
    """获取阅读量最高的周报"""
    try:
        limit = _clamp(request.args.get('limit', 10, type=int), 1, 50)
        analytics_service = get_analytics_service()
        top_reports = analytics_service.get_top_reports(limit)
        return APIResponse.success(data=top_reports)
    except Exception as e:
        logger.error(f"获取热门周报失败: {e}", exc_info=True)
        return APIResponse.error(str(e), 500)


@analytics_bp.route('/api/analytics/session-stats')
def get_session_stats():
    """获取用户会话统计数据"""
    try:
        days = _clamp(request.args.get('days', 30, type=int), 1, 365)
        analytics_service = get_analytics_service()
        stats = analytics_service.get_user_session_stats(days)
        return APIResponse.success(data=stats)
    except Exception as e:
        logger.error(f"获取会话统计失败: {e}", exc_info=True)
        return APIResponse.error(str(e), 500)
