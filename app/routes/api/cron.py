"""外部 cron 触发端点

供 GitHub Actions 等外部调度器调用，作为数据刷新回调之外的
兜底触发方式（主要用于 Render 免费层冷启动场景）。
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import current_app, request

from ...services.cron_receipt import CronReceipt, ReceiptConflict
from ...utils.api_helpers import APIResponse, handle_api_errors, rate_limit
from ...utils.error_handler import ErrorCategory, log_error
from . import _verify_bearer, api_bp


def _claim_receipt(operation: str) -> tuple[CronReceipt | None, tuple | None]:
    key = request.headers.get('X-Idempotency-Key')
    if key is None:
        return None, None
    try:
        receipt, replayed = CronReceipt.claim(key, operation)
    except ReceiptConflict:
        return None, APIResponse.error('idempotency_key_operation_mismatch', 409)
    except ValueError:
        return None, APIResponse.error('invalid_idempotency_key', 400)
    except Exception as exc:
        current_app.logger.warning('cron receipt unavailable: %s', type(exc).__name__)
        return None, APIResponse.error('receipt_unavailable', 503)
    if replayed:
        return None, APIResponse.success(data=receipt.snapshot(replayed=True), message='返回持久任务回执，未重复执行')
    return receipt, None


def _receipt_no_store(handler: Callable[..., tuple]) -> Callable[..., tuple]:
    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> tuple:
        response = handler(*args, **kwargs)
        response[0].headers['Cache-Control'] = 'no-store'
        return response

    return wrapped


@api_bp.route('/cron/receipt', methods=['GET'])
@_receipt_no_store
@rate_limit(max_requests=20, window=60)
@handle_api_errors
def get_cron_receipt() -> tuple:
    """只读核验持久回执；未知 key 不会创建任务或回执。"""
    if not _verify_bearer('CRON_SECRET'):
        response = APIResponse.error('Unauthorized', 401)
    else:
        try:
            receipt = CronReceipt.read(request.headers.get('X-Idempotency-Key', ''))
        except ValueError:
            response = APIResponse.error('invalid_idempotency_key', 400)
        except Exception as exc:
            current_app.logger.warning('cron receipt read unavailable: %s', type(exc).__name__)
            response = APIResponse.error('receipt_unavailable', 503)
        else:
            response = (
                APIResponse.error('receipt_not_found', 404)
                if receipt is None
                else APIResponse.success(data=receipt.snapshot(), message='持久任务回执，只读查询')
            )
    return response


@api_bp.route('/cron/trigger-weekly-report')
@rate_limit(max_requests=20, window=60)
@handle_api_errors
def trigger_weekly_report() -> tuple:
    """触发周报生成（供外部 cron 调用）"""
    if not _verify_bearer('CRON_SECRET'):
        return APIResponse.error('Unauthorized', 401)

    receipt, response = _claim_receipt('weekly-report:force-regenerate')
    if response is not None:
        return response

    # 函数内导入，避免启动阶段循环导入
    from app.tasks.weekly_report_task import generate_weekly_report

    try:
        if receipt is not None and not receipt.transition('running'):
            return APIResponse.error('receipt_ownership_lost', 503)
        report = generate_weekly_report(force_regenerate=True)
    except Exception as exc:
        if receipt is not None:
            receipt.transition('failed', {'error': type(exc).__name__})
        raise

    if report:
        result = {
            'report_id': report.id,
            'report_date': report.report_date.isoformat(),
            'week_start': report.week_start.isoformat(),
            'week_end': report.week_end.isoformat(),
            'title': report.title,
        }
        if receipt is not None:
            receipt.transition('completed', result)
            return APIResponse.success(data=receipt.snapshot(), message=f'周报已生成: {report.title}')
        return APIResponse.success(
            data=result,
            message=f'周报已生成: {report.title}',
        )
    if receipt is not None:
        receipt.transition('pending_verification')
        return APIResponse.success(data=receipt.snapshot(), message='周报未确认完成，结果待核实')
    return APIResponse.success(
        data=None,
        message='周报已存在或生成被跳过（冷却中/进行中）',
    )


@api_bp.route('/cron/trigger-new-books-sync')
@rate_limit(max_requests=20, window=60)
@handle_api_errors
def trigger_new_books_sync() -> tuple:
    """触发新书速递自动同步（供外部 cron 调用）

    全量同步约 4 分钟，超过 Gunicorn timeout，因此在后台线程执行、
    立即返回；同步逻辑内置 24 小时自我节流与实例锁，与 APScheduler
    定时器并存也不会重复或并发同步。
    """
    if not _verify_bearer('CRON_SECRET'):
        return APIResponse.error('Unauthorized', 401)

    receipt, response = _claim_receipt('new-books-sync:max-15:batch-1')
    if response is not None:
        return response

    # 函数内导入，避免启动阶段循环导入
    from app.setup import trigger_auto_sync_background

    app_obj = cast('Any', current_app)._get_current_object()
    result = (
        trigger_auto_sync_background(app_obj, receipt=receipt) if receipt else trigger_auto_sync_background(app_obj)
    )
    if receipt is not None:
        return APIResponse.success(data=receipt.snapshot(), message='返回持久任务回执；受理不代表同步完成')

    if result['status'] == 'already_running':
        return APIResponse.success(
            data=result,
            message='新书同步已有实例在运行，本次触发被跳过',
        )
    if result['status'] == 'pending_verification':
        return APIResponse.success(
            data=result,
            message='已有后台同步仍在执行，结果待核实；未启动新任务',
        )

    return APIResponse.success(
        data=result,
        message='新书同步已在后台启动（约 4 分钟完成，结果见服务器日志）',
    )


@api_bp.route('/cron/sync-award-covers')
@rate_limit(max_requests=20, window=60)
@handle_api_errors
def sync_award_covers() -> tuple:
    """触发获奖封面补同步（供外部 cron 调用）

    生产临时文件系统会在重启后清空 cache/，DB 里的 cover_local_path 仍指向已消失
    的文件；同步服务会把这类记录视为缺失并重新下载。批同步含外部 API 调用与逐本
    提交，最坏数百秒，不能占住请求线程（Render 免费版网关超时约 100s），因此提交
    后台线程后立即返回。服务内置防重入，与 APScheduler 定时器并存也不会并发同步。
    """
    if not _verify_bearer('CRON_SECRET'):
        return APIResponse.error('Unauthorized', 401)

    receipt, response = _claim_receipt('award-covers:batch-50:delay-0.3')
    if response is not None:
        return response

    # 函数内导入，避免启动阶段循环导入
    from ...services.award_cover_sync_service import AwardCoverSyncService
    from ...utils.service_helpers import (
        get_or_create_google_books_client,
        get_service,
        submit_background_task,
    )

    app_obj = cast('Any', current_app)._get_current_object()

    def _run_sync() -> None:
        with app_obj.app_context():
            try:
                if receipt is not None and not receipt.transition('running'):
                    return
                google_client = get_or_create_google_books_client()
                sync_service = AwardCoverSyncService(google_client, image_cache=get_service('image_cache_service'))
                result = sync_service.sync_missing_covers(batch_size=50, delay=0.3)
                if receipt is not None:
                    receipt.finish_sync(result)
                app_obj.logger.info(
                    f'cron 封面同步完成: {result.get("status")} '
                    f'更新{result.get("updated", 0)}本 跳过{result.get("skipped", 0)}本 失败{result.get("failed", 0)}本'
                )
            except Exception as exc:
                if receipt is not None:
                    try:
                        receipt.transition('failed', {'error': type(exc).__name__})
                    except Exception:
                        app_obj.logger.warning('封面同步回执未能确认，保留原回执')
                log_error(ErrorCategory.API_CALL, f'cron 封面同步失败: {type(exc).__name__}')

    try:
        submit_background_task(_run_sync)
    except Exception as exc:
        if receipt is not None:
            receipt.transition('failed', {'error': type(exc).__name__})
        raise

    if receipt is not None:
        return APIResponse.success(data=receipt.snapshot(), message='封面同步已受理，完成状态由持久回执确认')

    return APIResponse.success(
        data={'status': 'submitted'},
        message='获奖封面同步已在后台启动，结果见服务器日志',
    )
