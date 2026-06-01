"""外部 cron 触发端点

供 GitHub Actions 等外部调度器调用，绕过 APScheduler 在 Render 免费层
因休眠导致的定时器重置问题。
"""

import logging
import secrets
from typing import Any

from flask import Blueprint, current_app, jsonify, request

cron_bp = Blueprint('cron', __name__, url_prefix='/api/cron')
logger = logging.getLogger(__name__)


def _verify_cron_secret() -> bool:
    secret = current_app.config.get('CRON_SECRET') or ''
    if not secret:
        logger.warning('CRON_SECRET 未配置，拒绝 cron 请求')
        return False

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    token = auth_header[7:]

    return secrets.compare_digest(token, secret)


@cron_bp.route('/trigger-weekly-report')
def trigger_weekly_report() -> tuple[Any, int]:
    """触发周报生成（供外部 cron 调用）"""
    if not _verify_cron_secret():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        from app.tasks.weekly_report_task import generate_weekly_report

        report = generate_weekly_report()

        if report:
            return jsonify({
                'success': True,
                'message': f'周报已生成: {report.title}',
                'data': {
                    'report_id': report.id,
                    'report_date': report.report_date.isoformat(),
                    'week_start': report.week_start.isoformat(),
                    'week_end': report.week_end.isoformat(),
                    'title': report.title,
                },
            })
        else:
            return jsonify({
                'success': True,
                'message': '周报已存在或生成被跳过（冷却中/进行中）',
                'data': None,
            })
    except Exception as e:
        logger.error(f'Cron 触发周报生成失败: {e}', exc_info=True)
        return jsonify({'success': False, 'message': '周报生成失败，请查看服务器日志'}), 500
