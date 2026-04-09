#!/usr/bin/env python3
"""
分析服务路由

提供用户行为数据统计和分析相关的API接口
"""
from flask import Blueprint, jsonify, request
from app.services.analytics_service import get_analytics_service

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/api/analytics/report-views')
def get_report_views():
    """
    获取周报阅读统计数据
    
    Query参数:
        days: 统计天数，默认30
    """
    try:
        days = request.args.get('days', 30, type=int)
        days = min(max(1, days), 365)  # 限制范围
        
        analytics_service = get_analytics_service()
        stats = analytics_service.get_report_view_stats(days)
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analytics_bp.route('/api/analytics/user-behavior')
def get_user_behavior():
    """
    获取用户行为统计数据
    
    Query参数:
        days: 统计天数，默认30
    """
    try:
        days = request.args.get('days', 30, type=int)
        days = min(max(1, days), 365)  # 限制范围
        
        analytics_service = get_analytics_service()
        stats = analytics_service.get_user_behavior_stats(days)
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analytics_bp.route('/api/analytics/daily-stats')
def get_daily_stats():
    """
    获取每日统计数据
    
    Query参数:
        days: 统计天数，默认30
    """
    try:
        days = request.args.get('days', 30, type=int)
        days = min(max(1, days), 365)  # 限制范围
        
        analytics_service = get_analytics_service()
        stats = analytics_service.get_daily_stats(days)
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analytics_bp.route('/api/analytics/top-reports')
def get_top_reports():
    """
    获取阅读量最高的周报
    
    Query参数:
        limit: 返回数量限制，默认10
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(max(1, limit), 50)  # 限制范围
        
        analytics_service = get_analytics_service()
        top_reports = analytics_service.get_top_reports(limit)
        
        return jsonify({
            'success': True,
            'data': top_reports
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analytics_bp.route('/api/analytics/session-stats')
def get_session_stats():
    """
    获取用户会话统计数据
    
    Query参数:
        days: 统计天数，默认30
    """
    try:
        days = request.args.get('days', 30, type=int)
        days = min(max(1, days), 365)  # 限制范围
        
        analytics_service = get_analytics_service()
        stats = analytics_service.get_user_session_stats(days)
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
