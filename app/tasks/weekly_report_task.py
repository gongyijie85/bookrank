"""周报定时任务"""

import datetime
import logging
import threading

from ..models.schemas import WeeklyReport
from ..services.weekly_report_service import WeeklyReportService
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.service_helpers import require_book_service
from .weekly_report_task_helpers import compute_expected_week_range

logger = logging.getLogger(__name__)

_weekly_report_lock = threading.Lock()
_last_report_trigger_time: float = 0
_REPORT_TRIGGER_COOLDOWN: float = 300.0


def generate_weekly_report(force_regenerate: bool = False) -> WeeklyReport | None:
    global _last_report_trigger_time

    import time

    now = time.time()
    if not force_regenerate and (now - _last_report_trigger_time) < _REPORT_TRIGGER_COOLDOWN:
        logger.debug(f'周报触发冷却中（距上次 {now - _last_report_trigger_time:.0f}s），跳过')
        return None

    if not _weekly_report_lock.acquire(blocking=False):
        logger.info('周报生成已在进行中，跳过本次触发')
        return None

    try:
        _last_report_trigger_time = time.time()
        book_service = require_book_service()

        today = datetime.date.today()
        week_start, week_end = compute_expected_week_range(today)

        existing_report = WeeklyReport.query.filter(
            WeeklyReport.week_start == week_start, WeeklyReport.week_end == week_end
        ).first()

        if existing_report and not force_regenerate:
            logger.info(f'周报已存在: {week_start} 至 {week_end}')
            return existing_report

        if existing_report and force_regenerate:
            logger.info(f'强制重新生成周报: {week_start} 至 {week_end}')

        report_service = WeeklyReportService(book_service)

        report = report_service.generate_report(week_start, week_end, force_regenerate=force_regenerate)

        if report:
            logger.info(f'周报生成成功: {report.title}')
            return report
        else:
            logger.error('周报生成失败')
            return None

    except RuntimeError as e:
        log_error(ErrorCategory.API_CALL, f'服务未初始化，无法生成周报: {e!s}')
        return None
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'生成周报时出错: {e!s}')
        return None
    finally:
        try:
            _weekly_report_lock.release()
        except RuntimeError:
            pass


def send_weekly_report_email(report: WeeklyReport) -> bool:
    """发送周报邮件（已禁用 — Render 免费版不支持 SMTP 出站连接）"""
    logger.debug('邮件发送已禁用，周报仅在网页端查看')
    return False


def schedule_weekly_report():
    """调度周报生成任务"""
    report = generate_weekly_report()
    return report
