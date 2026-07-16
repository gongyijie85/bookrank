"""外部 cron 触发端点

供 GitHub Actions 等外部调度器调用，作为数据刷新回调之外的
兜底触发方式（主要用于 Render 免费层冷启动场景）。
"""

import logging
import secrets

from flask import current_app, request

from ...utils.api_helpers import APIResponse, handle_api_errors
from . import api_bp

logger = logging.getLogger(__name__)


def _verify_cron_secret() -> bool:
    """验证 cron 请求携带的 Bearer token 与配置是否一致"""
    secret = current_app.config.get('CRON_SECRET') or ''
    if not secret:
        logger.warning('CRON_SECRET 未配置，拒绝 cron 请求')
        return False

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False

    token = auth_header[7:]
    return secrets.compare_digest(token, secret)


@api_bp.route('/cron/trigger-weekly-report')
@handle_api_errors
def trigger_weekly_report() -> tuple:
    """触发周报生成（供外部 cron 调用）"""
    if not _verify_cron_secret():
        return APIResponse.error('Unauthorized', 401)

    # 函数内导入，避免启动阶段循环导入
    from app.tasks.weekly_report_task import generate_weekly_report

    report = generate_weekly_report(force_regenerate=True)

    if report:
        return APIResponse.success(
            data={
                'report_id': report.id,
                'report_date': report.report_date.isoformat(),
                'week_start': report.week_start.isoformat(),
                'week_end': report.week_end.isoformat(),
                'title': report.title,
            },
            message=f'周报已生成: {report.title}',
        )
    return APIResponse.success(
        data=None,
        message='周报已存在或生成被跳过（冷却中/进行中）',
    )
