#!/usr/bin/env python3
"""
用户行为数据分析服务

用于处理和分析用户行为数据，包括阅读量统计、行为分析等功能
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError

from app.models.database import db
from app.models.schemas import UserBehavior, WeeklyReport

logger = logging.getLogger(__name__)


class AnalyticsService:
    """用户行为数据分析服务"""

    def __init__(self):
        """初始化分析服务"""
        pass

    def get_report_view_stats(self, days: int = 30) -> dict[str, Any]:
        """
        获取周报阅读统计数据

        Args:
            days: 统计天数

        Returns:
            阅读统计数据
        """
        try:
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            logger.info(f'查询周报阅读统计，时间范围: {days}天')

            report_views = (
                db.session.query(WeeklyReport.report_date, WeeklyReport.title, WeeklyReport.view_count)
                .filter(WeeklyReport.created_at >= start_date)
                .order_by(WeeklyReport.report_date.desc())
                .all()
            )

            view_stats = []
            for report_date, title, view_count in report_views:
                view_stats.append(
                    {
                        'date': report_date.isoformat() if report_date else None,
                        'title': title,
                        'view_count': view_count or 0,
                    }
                )

            total_views = sum(item['view_count'] for item in view_stats)
            avg_views = total_views / len(view_stats) if view_stats else 0

            logger.info(f'周报阅读统计完成: {len(view_stats)}条记录, 总阅读量{total_views}, 平均阅读量{avg_views:.2f}')

            return {
                'total_views': total_views,
                'average_views': round(avg_views, 2),
                'view_stats': view_stats,
                'period': f'最近{days}天',
            }
        except SQLAlchemyError as e:
            logger.error(f'查询周报阅读统计失败: {e}')
            return {
                'total_views': 0,
                'average_views': 0,
                'view_stats': [],
                'period': f'最近{days}天',
                'error': '查询失败',
            }

    def get_user_behavior_stats(self, days: int = 30) -> dict[str, Any]:
        """
        获取用户行为统计数据

        Args:
            days: 统计天数

        Returns:
            用户行为统计数据
        """
        try:
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            logger.info(f'查询用户行为统计，时间范围: {days}天')

            behavior_stats = (
                db.session.query(UserBehavior.event_type, func.count(UserBehavior.id).label('count'))
                .filter(UserBehavior.created_at >= start_date)
                .group_by(UserBehavior.event_type)
                .order_by(desc('count'))
                .all()
            )

            behavior_list = []
            for event_type, count in behavior_stats:
                behavior_list.append({'event_type': event_type, 'count': count})

            total_behaviors = sum(item['count'] for item in behavior_list)

            logger.info(f'用户行为统计完成: {len(behavior_list)}种事件类型, 总行为数{total_behaviors}')

            return {'total_behaviors': total_behaviors, 'behavior_stats': behavior_list, 'period': f'最近{days}天'}
        except SQLAlchemyError as e:
            logger.error(f'查询用户行为统计失败: {e}')
            return {'total_behaviors': 0, 'behavior_stats': [], 'period': f'最近{days}天', 'error': '查询失败'}

    def get_daily_stats(self, days: int = 30) -> dict[str, Any]:
        """
        获取每日统计数据

        Args:
            days: 统计天数

        Returns:
            每日统计数据
        """
        try:
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            logger.info(f'查询每日统计，时间范围: {days}天')

            daily_stats = (
                db.session.query(
                    func.date(UserBehavior.created_at).label('date'), func.count(UserBehavior.id).label('count')
                )
                .filter(UserBehavior.created_at >= start_date)
                .group_by(func.date(UserBehavior.created_at))
                .order_by(func.date(UserBehavior.created_at))
                .all()
            )

            daily_list = []
            for date, count in daily_stats:
                daily_list.append({'date': date.isoformat() if hasattr(date, 'isoformat') else date, 'count': count})

            logger.info(f'每日统计完成: {len(daily_list)}天数据')

            return {'daily_stats': daily_list, 'period': f'最近{days}天'}
        except SQLAlchemyError as e:
            logger.error(f'查询每日统计失败: {e}')
            return {'daily_stats': [], 'period': f'最近{days}天', 'error': '查询失败'}

    def get_top_reports(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        获取阅读量最高的周报

        Args:
            limit: 返回数量限制

        Returns:
            阅读量最高的周报列表
        """
        try:
            logger.info(f'查询热门周报，数量限制: {limit}')

            top_reports = (
                db.session.query(WeeklyReport.report_date, WeeklyReport.title, WeeklyReport.view_count)
                .order_by(desc(WeeklyReport.view_count))
                .limit(limit)
                .all()
            )

            top_list = []
            for report_date, title, view_count in top_reports:
                top_list.append(
                    {
                        'date': report_date.isoformat() if report_date else None,
                        'title': title,
                        'view_count': view_count or 0,
                    }
                )

            logger.info(f'热门周报查询完成: {len(top_list)}条记录')

            return top_list
        except SQLAlchemyError as e:
            logger.error(f'查询热门周报失败: {e}')
            return []

    def get_user_session_stats(self, days: int = 30) -> dict[str, Any]:
        """
        获取用户会话统计数据

        Args:
            days: 统计天数

        Returns:
            用户会话统计数据
        """
        try:
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            logger.info(f'查询用户会话统计，时间范围: {days}天')

            session_count = (
                db.session.query(func.count(func.distinct(UserBehavior.session_id)))
                .filter(UserBehavior.created_at >= start_date)
                .scalar()
                or 0
            )

            session_counts = (
                db.session.query(func.count(UserBehavior.id))
                .filter(UserBehavior.created_at >= start_date)
                .group_by(UserBehavior.session_id)
                .all()
            )
            session_behavior_avg = sum(c[0] for c in session_counts) / len(session_counts) if session_counts else 0

            logger.info(f'会话统计完成: {session_count}个会话, 平均行为数{session_behavior_avg:.2f}')

            return {
                'session_count': session_count,
                'average_behaviors_per_session': round(float(session_behavior_avg), 2),
                'period': f'最近{days}天',
            }
        except SQLAlchemyError as e:
            logger.error(f'查询用户会话统计失败: {e}')
            return {
                'session_count': 0,
                'average_behaviors_per_session': 0,
                'period': f'最近{days}天',
                'error': '查询失败',
            }


# 创建单例实例
_analytics_service: AnalyticsService | None = None


def get_analytics_service() -> AnalyticsService:
    """
    获取分析服务实例

    Returns:
        分析服务实例
    """
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
