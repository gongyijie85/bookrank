#!/usr/bin/env python3
"""
用户行为数据分析服务

用于处理和分析用户行为数据，包括阅读量统计、行为分析等功能
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import func, desc
from app.models.schemas import UserBehavior, WeeklyReport, ReportView
from app.models.database import db


class AnalyticsService:
    """用户行为数据分析服务"""
    
    def __init__(self):
        """初始化分析服务"""
        pass
    
    def get_report_view_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        获取周报阅读统计数据
        
        Args:
            days: 统计天数
            
        Returns:
            阅读统计数据
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # 获取周报阅读量统计
        report_views = db.session.query(
            WeeklyReport.report_date,
            WeeklyReport.title,
            WeeklyReport.view_count
        ).filter(
            WeeklyReport.created_at >= start_date
        ).order_by(
            WeeklyReport.report_date.desc()
        ).all()
        
        # 转换为列表格式
        view_stats = []
        for report_date, title, view_count in report_views:
            view_stats.append({
                'date': report_date.isoformat() if report_date else None,
                'title': title,
                'view_count': view_count or 0
            })
        
        # 计算总阅读量
        total_views = sum(item['view_count'] for item in view_stats)
        
        # 计算平均阅读量
        avg_views = total_views / len(view_stats) if view_stats else 0
        
        return {
            'total_views': total_views,
            'average_views': round(avg_views, 2),
            'view_stats': view_stats,
            'period': f"最近{days}天"
        }
    
    def get_user_behavior_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        获取用户行为统计数据
        
        Args:
            days: 统计天数
            
        Returns:
            用户行为统计数据
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # 获取行为类型统计
        behavior_stats = db.session.query(
            UserBehavior.event_type,
            func.count(UserBehavior.id).label('count')
        ).filter(
            UserBehavior.created_at >= start_date
        ).group_by(
            UserBehavior.event_type
        ).order_by(
            desc('count')
        ).all()
        
        # 转换为列表格式
        behavior_list = []
        for event_type, count in behavior_stats:
            behavior_list.append({
                'event_type': event_type,
                'count': count
            })
        
        # 获取总行为数
        total_behaviors = sum(item['count'] for item in behavior_list)
        
        return {
            'total_behaviors': total_behaviors,
            'behavior_stats': behavior_list,
            'period': f"最近{days}天"
        }
    
    def get_daily_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        获取每日统计数据
        
        Args:
            days: 统计天数
            
        Returns:
            每日统计数据
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # 获取每日行为统计
        daily_stats = db.session.query(
            func.date(UserBehavior.created_at).label('date'),
            func.count(UserBehavior.id).label('count')
        ).filter(
            UserBehavior.created_at >= start_date
        ).group_by(
            func.date(UserBehavior.created_at)
        ).order_by(
            func.date(UserBehavior.created_at)
        ).all()
        
        # 转换为列表格式
        daily_list = []
        for date, count in daily_stats:
            daily_list.append({
                'date': date.isoformat() if date else None,
                'count': count
            })
        
        return {
            'daily_stats': daily_list,
            'period': f"最近{days}天"
        }
    
    def get_top_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取阅读量最高的周报
        
        Args:
            limit: 返回数量限制
            
        Returns:
            阅读量最高的周报列表
        """
        top_reports = db.session.query(
            WeeklyReport.report_date,
            WeeklyReport.title,
            WeeklyReport.view_count
        ).order_by(
            desc(WeeklyReport.view_count)
        ).limit(limit).all()
        
        # 转换为列表格式
        top_list = []
        for report_date, title, view_count in top_reports:
            top_list.append({
                'date': report_date.isoformat() if report_date else None,
                'title': title,
                'view_count': view_count or 0
            })
        
        return top_list
    
    def get_user_session_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        获取用户会话统计数据
        
        Args:
            days: 统计天数
            
        Returns:
            用户会话统计数据
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # 获取会话数量
        session_count = db.session.query(
            func.count(func.distinct(UserBehavior.session_id))
        ).filter(
            UserBehavior.created_at >= start_date
        ).scalar() or 0
        
        # 获取每个会话的平均行为数
        session_behavior_avg = db.session.query(
            func.avg(func.count(UserBehavior.id))
        ).filter(
            UserBehavior.created_at >= start_date
        ).group_by(
            UserBehavior.session_id
        ).scalar() or 0
        
        return {
            'session_count': session_count,
            'average_behaviors_per_session': round(float(session_behavior_avg), 2),
            'period': f"最近{days}天"
        }


# 创建单例实例
_analytics_service: Optional[AnalyticsService] = None


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
