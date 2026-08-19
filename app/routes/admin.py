import json as json_lib
import re
import time
from datetime import UTC, datetime
from typing import Any

import psutil
from flask import Blueprint, Response, current_app, request

from ..models.database import db
from ..services.admin_service import (
    batch_import_from_dict,
    get_weekly_report_by_id,
    update_book_metadata_records,
    update_translation_cache_records,
)
from ..utils.admin_auth import admin_required
from ..utils.api_helpers import APIResponse, csrf_protect
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.error_tracker import error_tracker
from ..utils.service_helpers import get_new_book_modules, get_service

_ADMIN_ERROR_MSG = '操作失败，请查看服务器日志获取详情'

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

_crawler_status: dict[str, dict[str, Any]] = {}


@admin_bp.route('/award-covers/sync', methods=['POST'])
@csrf_protect
@admin_required
def sync_award_covers():
    """手动触发获奖书籍封面同步（后台任务，立即返回 202）

    批同步含外部 API 调用 + 下载 + 逐本提交，最坏数百秒，不能占住
    请求线程（Render 免费版网关超时约 100s）；改为提交后台线程执行，
    进度与最近结果通过 /award-covers/status 轮询。
    """
    try:
        from ..services.award_cover_sync_service import AwardCoverSyncService
        from ..utils.service_helpers import (
            get_or_create_google_books_client,
            submit_background_task,
        )

        data = request.get_json(silent=True) or {}
        batch_size = min(max(1, data.get('batch_size', 10)), 50)

        app_obj = current_app._get_current_object()

        def _run_sync() -> None:
            with app_obj.app_context():
                try:
                    google_client = get_or_create_google_books_client()
                    sync_service = AwardCoverSyncService(google_client, image_cache=get_service('image_cache_service'))
                    result = sync_service.sync_missing_covers(batch_size=batch_size, delay=0.3)
                    app_obj.logger.info(f'后台封面同步完成: {result.get("status")} 更新{result.get("updated", 0)}本')
                except Exception as e:
                    log_error(ErrorCategory.API_CALL, f'后台封面同步失败: {e}', exc_info=True)

        submit_background_task(_run_sync)

        return APIResponse.success(
            data={'status': 'submitted', 'batch_size': batch_size},
            message='封面同步已提交后台执行，可通过 /api/admin/award-covers/status 查询进度与最近结果',
            status_code=202,
        )

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'提交封面同步任务失败: {e}', exc_info=True)
        return APIResponse.error('提交同步任务失败', 500)


@admin_bp.route('/award-covers/status')
@admin_required
def get_award_covers_status():
    """获取获奖书籍封面同步状态"""
    try:
        from ..services.award_cover_sync_service import AwardCoverSyncService
        from ..utils.service_helpers import get_or_create_google_books_client

        google_client = get_or_create_google_books_client()

        sync_service = AwardCoverSyncService(google_client)
        status = sync_service.get_sync_status()

        return APIResponse.success(data=status)

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取封面状态失败: {e}', exc_info=True)
        return APIResponse.error('获取状态失败', 500)


@admin_bp.route('/new-books/source-health')
@admin_required
def get_new_books_source_health():
    """按来源返回官网采集健康状态与降级计数（#136）。"""
    try:
        from ..services.source_health_service import list_source_health

        return APIResponse.success(data={'sources': list_source_health()})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'读取来源健康状态失败: {e}', exc_info=True)
        return APIResponse.error('读取失败', 500)


@admin_bp.route('/new-books/source-control/<source_id>', methods=['GET', 'POST'])
@admin_required
def manage_new_books_source_control(source_id: str):
    """读取或更新来源级官网主路径开关（#137，无重新部署）。"""
    try:
        from ..services import source_control_service

        if request.method == 'GET':
            return APIResponse.success(data=source_control_service.get_flags(source_id))

        data = request.get_json(silent=True) or {}
        actor = str(data.get('actor') or request.headers.get('X-Admin-Actor') or 'admin')
        flags = source_control_service.set_flags(
            source_id,
            actor=actor,
            site_crawl_enabled=data.get('site_crawl_enabled'),
            site_import_enabled=data.get('site_import_enabled'),
            site_display_primary=data.get('site_display_primary'),
            fallback_google_enabled=data.get('fallback_google_enabled'),
        )
        return APIResponse.success(data=flags, message='source control updated')
    except ValueError as e:
        return APIResponse.error(str(e), 400)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'更新来源开关失败: {e}', exc_info=True)
        return APIResponse.error('更新失败', 500)


@admin_bp.route('/new-books/source-control-audit')
@admin_required
def get_source_control_audit():
    """来源开关变更审计日志。"""
    try:
        from ..services import source_control_service

        return APIResponse.success(data={'audit': source_control_service.list_audit(limit=50)})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'读取来源开关审计失败: {e}', exc_info=True)
        return APIResponse.error('读取失败', 500)


@admin_bp.route('/new-books/pilot/<source_id>/evidence')
@admin_required
def get_pilot_evidence(source_id: str):
    """试点证据集（#140）。"""
    try:
        from ..services import pilot_gate_service

        return APIResponse.success(data={'evidence': pilot_gate_service.get_evidence_bundle(source_id)})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'读取试点证据失败: {e}', exc_info=True)
        return APIResponse.error('读取失败', 500)


@admin_bp.route('/new-books/pilot/<source_id>/gates')
@admin_required
def get_pilot_gates(source_id: str):
    """试点质量闸门评估（#140）。"""
    try:
        from ..services import pilot_gate_service

        report = pilot_gate_service.evaluate_gates(source_id)
        allowed, reason = pilot_gate_service.can_enable_display_primary(source_id)
        report['can_enable_display_primary'] = allowed
        report['can_enable_reason'] = reason
        return APIResponse.success(data=report)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'评估试点闸门失败: {e}', exc_info=True)
        return APIResponse.error('读取失败', 500)


@admin_bp.route('/new-books/pilot/<source_id>/rollback-drill', methods=['POST'])
@admin_required
def post_pilot_rollback_drill(source_id: str):
    """无重新部署回滚演练（#140）。"""
    try:
        from ..services import pilot_gate_service

        data = request.get_json(silent=True) or {}
        actor = str(data.get('actor') or 'admin')
        result = pilot_gate_service.run_rollback_drill(source_id, actor=actor)
        return APIResponse.success(data=result, message='rollback drill completed')
    except ValueError as e:
        return APIResponse.error(str(e), 400)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'回滚演练失败: {e}', exc_info=True)
        return APIResponse.error('演练失败', 500)


@admin_bp.route('/new-books/pilot/<source_id>/compliance-go', methods=['POST'])
@admin_required
def post_pilot_compliance_go(source_id: str):
    """记录合规 GO/NO-GO（通常对应 #124）。"""
    try:
        from ..services import pilot_gate_service

        data = request.get_json(silent=True) or {}
        go = bool(data.get('go'))
        actor = str(data.get('actor') or 'admin')
        pilot_gate_service.set_compliance_go(source_id, go, actor=actor)
        return APIResponse.success(data={'source_id': source_id, 'go': go})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'写入合规 GO 失败: {e}', exc_info=True)
        return APIResponse.error('写入失败', 500)


@admin_bp.route('/new-books/source-alert/sync/<source_id>', methods=['POST'])
@admin_required
def post_sync_source_alert(source_id: str):
    """手动同步 degraded 告警 Issue（alert 相位也可调用，不持有导入密钥）。"""
    try:
        from ..services import source_alert_service
        from ..services.source_health_service import publisher_for_source

        pub = publisher_for_source(source_id)
        if pub is None:
            return APIResponse.error('unknown source', 400)
        if pub.source_status == 'degraded':
            issue = source_alert_service.sync_degraded_alert(source_id, pub)
            return APIResponse.success(data={'action': 'synced', 'issue': issue})
        if pub.source_status == 'healthy':
            source_alert_service.close_degraded_alert(source_id, recovery_batch_id=pub.last_success_batch_id)
            return APIResponse.success(data={'action': 'closed_if_open'})
        return APIResponse.success(data={'action': 'noop', 'status': pub.source_status})
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'同步来源告警失败: {e}', exc_info=True)
        return APIResponse.error('同步失败', 500)


@admin_bp.route('/new-books/last-sync')
@admin_required
def get_new_books_last_sync():
    """读取最近一次新书自动同步结果（工单 #83 观测通道）

    返回 last_auto_sync_time 与 last_auto_sync_result 摘要，后者包含
    Google Books 系各家的 date_filter 分类拒绝计数，是 2 周观测期
    漏报率判定的数据读取入口。
    """
    try:
        from ..models.schemas import SystemConfig

        raw = SystemConfig.get_value('last_auto_sync_result')
        summary = json_lib.loads(raw) if raw else None
        return APIResponse.success(
            data={
                'last_auto_sync_time': SystemConfig.get_value('last_auto_sync_time'),
                'result': summary,
            }
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'读取新书同步摘要失败: {e}', exc_info=True)
        return APIResponse.error('读取失败', 500)


@admin_bp.route('/weekly-report/regenerate', methods=['POST'])
@csrf_protect
@admin_required
def regenerate_weekly_report():
    """手动重新生成指定日期的周报"""
    try:
        from datetime import date, timedelta

        from ..services.weekly_report_service import WeeklyReportService

        data = request.json or {}
        report_date_str = data.get('report_date')

        if not report_date_str:
            return APIResponse.error('缺少 report_date 参数', 400)

        try:
            report_date = date.fromisoformat(report_date_str)
        except ValueError:
            return APIResponse.error('日期格式错误，应为 YYYY-MM-DD', 400)

        if report_date > date.today():
            return APIResponse.error('不能重新生成未来的周报', 400)

        book_service = get_service('book_service')
        if not book_service:
            return APIResponse.error('服务不可用', 503)
        weekly_service = WeeklyReportService(book_service)

        weekday = report_date.weekday()
        week_start = report_date - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)

        report = weekly_service.generate_report(week_start, week_end, force_regenerate=True)

        if report:
            return APIResponse.success(
                data={
                    'report_id': report.id,
                    'report_date': report_date.isoformat(),
                    'week_start': week_start.isoformat(),
                    'week_end': week_end.isoformat(),
                    'title': report.title,
                    'message': f'已成功重新生成 {report_date} 的周报',
                },
                message='周报重新生成成功',
            )
        else:
            return APIResponse.error('生成失败：数据不足或AI服务异常', 500)

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'重新生成周报失败: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


@admin_bp.route('/weekly-report/regenerate-all', methods=['POST'])
@csrf_protect
@admin_required
def regenerate_all_weekly_reports():
    """批量重新生成所有有问题的周报"""
    try:
        from ..models.schemas import WeeklyReport
        from ..services.weekly_report_service import WeeklyReportService

        prompt_markers = ['请为', '要求：', '基于以下分析结果']
        problematic_reports = []

        reports = WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).all()
        for report in reports:
            summary = report.summary or ''
            if any(marker in summary for marker in prompt_markers):
                problematic_reports.append(report)

        if not problematic_reports:
            return APIResponse.success(
                data={'total_checked': len(reports), 'regenerated': 0, 'message': '所有周报正常，无需重新生成'},
                message='所有周报数据正常',
            )

        book_service = get_service('book_service')
        if not book_service:
            return APIResponse.error('服务不可用', 503)
        weekly_service = WeeklyReportService(book_service)

        results = []
        for report in problematic_reports:
            try:
                new_report = weekly_service.generate_report(report.week_start, report.week_end, force_regenerate=True)
                results.append(
                    {
                        'date': report.report_date.isoformat(),
                        'success': new_report is not None,
                        'error': None if new_report else '生成失败',
                    }
                )
            except Exception as e:
                results.append({'date': report.report_date.isoformat(), 'success': False, 'error': str(e)})

        success_count = sum(1 for r in results if r['success'])

        return APIResponse.success(
            data={
                'total_problematic': len(problematic_reports),
                'regenerated': success_count,
                'details': results,
                'message': f'成功修复 {success_count}/{len(problematic_reports)} 份周报',
            },
            message=f'批量修复完成：{success_count}份成功',
        )

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'批量重新生成周报失败: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


@admin_bp.route('/categories/cleanup', methods=['GET', 'POST'])
@csrf_protect
@admin_required
def cleanup_categories():
    """清理新书分类中的营销文案数据"""
    try:
        from ..services.category_cleanup_service import apply_cleanup

        if request.method == 'GET':
            dry_run = True
        else:
            data = request.get_json(silent=True) or {}
            dry_run = data.get('dry_run', True)

        result = apply_cleanup(dry_run=dry_run)

        if not dry_run:
            return APIResponse.success(
                data={
                    'total_checked': result.total_checked,
                    'invalid_found': result.invalid_found,
                    'updated': result.updated,
                    'details': result.details,
                },
                message=f'清理完成: 修复{result.updated}条分类数据',
            )
        else:
            return APIResponse.success(
                data={
                    'total_checked': result.total_checked,
                    'invalid_found': result.invalid_found,
                    'details': result.details,
                    'message': '预览模式，未实际修改。发送 dry_run=false 执行清理',
                },
                message=f'预览: 发现{result.invalid_found}条无效分类',
            )

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'清理分类数据失败: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


def _clean_report_text(text: str) -> str:
    """清理周报文本中的书名污染"""
    if not text:
        return text
    from ..services.weekly_report_service import _format_book_title

    text = re.sub(r'《{2,}', '《', text)
    text = re.sub(r'》{2,}', '》', text)
    text = re.sub(r'\*\*《([^》]+)》\*\*', r'《\1》', text)
    text = re.sub(r'\*《([^》]+)》\*', r'《\1》', text)
    text = re.sub(r'《[^》\n]+》\n[^《\n]*(?:\n[^《\n]*)*', lambda m: _format_book_title(m.group(0)), text)
    return text


@admin_bp.route('/reports/clean-brackets', methods=['GET', 'POST'])
@csrf_protect
@admin_required
def clean_report_brackets():
    """清理周报中的书名污染（双书名号、markdown、作者名混入、长描述等）"""
    try:
        from ..models.schemas import WeeklyReport
        from ..services.weekly_report_service import _format_book_title

        if request.method == 'GET':
            dry_run = True
        else:
            data = request.get_json(silent=True) or {}
            dry_run = data.get('dry_run', True)

        reports = WeeklyReport.query.all()
        fixable = []

        for report in reports:
            issues = []

            if report.summary:
                cleaned_summary = _clean_report_text(report.summary)
                if cleaned_summary != report.summary:
                    issues.append('summary')

            if report.content:
                try:
                    content = json_lib.loads(report.content)
                    has_issue = False
                    for key in ['top_changes', 'new_books', 'top_risers', 'longest_running', 'featured_books']:
                        for book in content.get(key, []):
                            if 'title' in book:
                                clean = _format_book_title(book['title'])
                                if clean != book['title']:
                                    has_issue = True
                                    book['title'] = clean
                    if has_issue:
                        issues.append('content')
                except (json_lib.JSONDecodeError, TypeError):
                    pass

            if issues:
                fixable.append({'id': report.id, 'report_date': str(report.report_date), 'issues': issues})

        if not dry_run:
            updated = 0
            for item in fixable:
                report = get_weekly_report_by_id(item['id'])
                if not report:
                    continue

                if 'summary' in item['issues']:
                    report.summary = _clean_report_text(report.summary)

                if 'content' in item['issues']:
                    content = json_lib.loads(report.content)
                    for key in ['top_changes', 'new_books', 'top_risers', 'longest_running', 'featured_books']:
                        for book in content.get(key, []):
                            if 'title' in book:
                                book['title'] = _format_book_title(book['title'])
                    report.content = json_lib.dumps(content, ensure_ascii=False)

                updated += 1

            db.session.commit()
            return APIResponse.success(
                data={'total_reports': len(reports), 'fixable': len(fixable), 'updated': updated, 'details': fixable},
                message=f'清理完成: 修复{updated}份周报',
            )
        else:
            return APIResponse.success(
                data={
                    'total_reports': len(reports),
                    'fixable': len(fixable),
                    'details': fixable,
                    'message': '预览模式，未实际修改。发送 dry_run=false 执行清理',
                },
                message=f'预览: 发现{len(fixable)}份周报有问题',
            )

    except Exception as e:
        db.session.rollback()
        log_error(ErrorCategory.DB_QUERY, f'清理周报书名号失败: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


@admin_bp.route('/reports/fix-truncated-titles', methods=['GET', 'POST'])
@csrf_protect
@admin_required
def fix_truncated_titles():
    """修复被截断的书名（从其他数据源恢复）"""
    try:
        from ..models.schemas import BookMetadata, WeeklyReport

        if request.method == 'GET':
            dry_run = True
        else:
            data = request.get_json(silent=True) or {}
            dry_run = data.get('dry_run', True)

        book_metadata_map = {}
        all_books = BookMetadata.query.all()
        for book in all_books:
            if book.isbn and book.title_zh:
                book_metadata_map[book.isbn] = book.title_zh

        reports = WeeklyReport.query.all()
        fixed_count = 0
        details = []

        for report in reports:
            if not report.content:
                continue

            try:
                content = json_lib.loads(report.content)
            except (json_lib.JSONDecodeError, TypeError):
                continue

            report_fixed = False
            for key in ['top_changes', 'new_books', 'top_risers', 'longest_running', 'featured_books']:
                for book in content.get(key, []):
                    title = book.get('title', '')
                    if not title:
                        continue

                    clean_title = title.strip('《》').strip()
                    if len(clean_title) <= 2 and '《' in title:
                        isbn = book.get('isbn', '')
                        if isbn and isbn in book_metadata_map:
                            correct_title = book_metadata_map[isbn]
                            details.append(
                                {
                                    'report_date': str(report.report_date),
                                    'section': key,
                                    'old_title': title,
                                    'new_title': f'《{correct_title}》',
                                    'source': 'book_metadata',
                                }
                            )
                            book['title'] = f'《{correct_title}》'
                            report_fixed = True

            if report_fixed:
                fixed_count += 1
                if not dry_run:
                    report.content = json_lib.dumps(content, ensure_ascii=False)

        if not dry_run and fixed_count > 0:
            db.session.commit()

        return APIResponse.success(
            data={
                'total_reports': len(reports),
                'fixed': fixed_count,
                'details': details[:50],
                'dry_run': dry_run,
                'message': '预览模式' if dry_run else f'已修复{fixed_count}份周报',
            }
        )

    except Exception as e:
        db.session.rollback()
        log_error(ErrorCategory.DB_QUERY, f'修复截断书名失败: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


@admin_bp.route('/translations/cleanup', methods=['GET', 'POST'])
@csrf_protect
@admin_required
def cleanup_translations():
    """清理翻译缓存和BookMetadata中污染的书名"""
    try:
        from ..models.schemas import BookMetadata, TranslationCache
        from ..utils.api_helpers import clean_translation_text

        if request.method == 'GET':
            dry_run = True
        else:
            data = request.get_json(silent=True) or {}
            dry_run = data.get('dry_run', True)

        def is_dirty(text):
            if not text:
                return False
            if re.search(r'\*{1,2}|_{1,2}|#{1,6}|`', text):
                return True
            if any(label in text for label in ['书名：', '作者：', '简介：', 'Title:', 'Author:']):
                return True
            if '路' in text:
                if '《' not in text and len(text) > 10:
                    return True
                if re.search(r'[\u4e00-\u9fff]+\s*路\s*[\u4e00-\u9fff]+\s*路?\s*《', text):
                    return True
            if text.endswith('》') and len(text) > 2:
                return True
            if '《》' in text:
                return True
            bracket_match = re.search(r'《[^》]+》', text)
            if bracket_match and len(text[bracket_match.end() :].strip()) > 5:
                return True
            return bool('\n' in text and len(text) > 30)

        fixable_translations = []
        fixable_metadata = []

        t_records = TranslationCache.query.filter(TranslationCache.target_lang == 'zh').all()
        for record in t_records:
            text = record.translated_text or ''
            if is_dirty(text):
                cleaned = clean_translation_text(text)
                if cleaned != text:
                    fixable_translations.append(
                        {
                            'id': record.id,
                            'source': record.source_text[:50],
                            'before': text[:100],
                            'after': cleaned[:100],
                        }
                    )

        m_records = BookMetadata.query.filter(BookMetadata.title_zh.isnot(None)).all()
        for record in m_records:
            text = record.title_zh or ''
            if is_dirty(text):
                cleaned = clean_translation_text(text, field_type='title')
                if cleaned != text:
                    fixable_metadata.append(
                        {'isbn': record.isbn, 'source': record.title[:50], 'before': text[:100], 'after': cleaned[:100]}
                    )

        total_fixable = len(fixable_translations) + len(fixable_metadata)

        if not dry_run:
            t_ids = [item['id'] for item in fixable_translations]
            t_updated = update_translation_cache_records(
                t_ids, lambda r: setattr(r, 'translated_text', clean_translation_text(r.translated_text))
            )

            m_isbn_list = [item['isbn'] for item in fixable_metadata]
            m_updated = update_book_metadata_records(
                m_isbn_list, lambda r: setattr(r, 'title_zh', clean_translation_text(r.title_zh, field_type='title'))
            )

            db.session.commit()
            return APIResponse.success(
                data={
                    'translation_cache': {'total': len(t_records), 'fixed': t_updated},
                    'book_metadata': {'total': len(m_records), 'fixed': m_updated},
                    'details_translations': fixable_translations[:20],
                    'details_metadata': fixable_metadata[:20],
                },
                message=f'清理完成: 修复{t_updated}条缓存 + {m_updated}条元数据',
            )
        else:
            return APIResponse.success(
                data={
                    'translation_cache': {'total': len(t_records), 'fixable': len(fixable_translations)},
                    'book_metadata': {'total': len(m_records), 'fixable': len(fixable_metadata)},
                    'details_translations': fixable_translations[:20],
                    'details_metadata': fixable_metadata[:20],
                    'message': '预览模式，未实际修改。发送 dry_run=false 执行清理',
                },
                message=f'预览: 发现{total_fixable}条被污染的翻译数据',
            )

    except Exception as e:
        db.session.rollback()
        log_error(ErrorCategory.DB_QUERY, f'清理翻译缓存失败: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


@admin_bp.route('/errors')
@admin_required
def view_errors():
    """查看内存中记录的错误（最近50条）"""
    try:
        stats = error_tracker.get_stats()
        recent = error_tracker.get_recent(limit=50)
        return APIResponse.success(
            data={
                'total_count': sum(stats.values()),
                'error_stats': stats,
                'recent_errors': recent,
            }
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'获取错误记录失败: {e}', exc_info=True)
        return APIResponse.error('获取失败', 500)


@admin_bp.route('/errors/clear', methods=['POST'])
@csrf_protect
@admin_required
def clear_errors():
    """清空内存中的错误记录"""
    try:
        error_tracker.clear()
        return APIResponse.success(message='错误记录已清空')
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'清空错误记录失败: {e}', exc_info=True)
        return APIResponse.error('清空失败', 500)


@admin_bp.route('/crawler/run/<publisher_name>', methods=['POST'])
@csrf_protect
@admin_required
def run_crawler(publisher_name: str):
    try:
        modules = get_new_book_modules()
        publishers = modules.publisher_manager.get_publishers(active_only=True)
        publisher = next((p for p in publishers if p.name == publisher_name), None)
        if not publisher:
            return APIResponse.error(f'出版社不存在: {publisher_name}', 404)

        data = request.get_json(silent=True) or {}
        category = data.get('category')
        max_books = min(max(1, data.get('max_books', 30)), 100)

        _crawler_status[publisher_name] = {
            'status': 'running',
            'started_at': datetime.now(UTC).isoformat(),
            'publisher': publisher_name,
        }

        try:
            result = modules.sync_engine.sync_publisher_books(
                publisher_id=publisher.id,
                category=category,
                max_books=max_books,
                translate=True,
            )
            _crawler_status[publisher_name].update(
                {
                    'status': 'completed',
                    'finished_at': datetime.now(UTC).isoformat(),
                    'last_result': result,
                }
            )
            return APIResponse.success(data=result, message=f'{publisher_name} 爬虫执行完成')
        except Exception as e:
            _crawler_status[publisher_name].update(
                {
                    'status': 'failed',
                    'finished_at': datetime.now(UTC).isoformat(),
                    'error': str(e),
                }
            )
            raise

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'爬虫执行失败 [{publisher_name}]: {e}', exc_info=True)
        return APIResponse.error(_ADMIN_ERROR_MSG, 500)


@admin_bp.route('/crawler/status')
@admin_required
def crawler_status():
    try:
        modules = get_new_book_modules()
        publishers = modules.publisher_manager.get_publishers(active_only=True)
        pub_book_counts = modules.publisher_manager.get_publisher_book_counts()

        publishers_info = []
        for p in publishers:
            publishers_info.append(
                {
                    'name': p.name,
                    'crawler_class': p.crawler_class,
                    'book_count': pub_book_counts.get(p.id, 0),
                    'last_run': _crawler_status.get(p.name, {}),
                }
            )

        return APIResponse.success(
            data={
                'publishers': publishers_info,
                'total_publishers': len(publishers_info),
                'active_crawlers': sum(1 for s in _crawler_status.values() if s.get('status') == 'running'),
            }
        )
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获取爬虫状态失败: {e}', exc_info=True)
        return APIResponse.error('获取状态失败', 500)


@admin_bp.route('/system/status')
@admin_required
def system_status():
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()

        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        db_type = 'unknown'
        if 'sqlite' in db_uri:
            db_type = 'sqlite'
        elif 'postgresql' in db_uri:
            db_type = 'postgresql'
        elif 'mysql' in db_uri:
            db_type = 'mysql'

        try:
            from ..utils.service_helpers import get_service as _get_svc

            cs = _get_svc('cache_service')
            cache_stats = (
                cs.get_stats() if cs else {'memory': {'size': 0, 'max_size': 0, 'hits': 0, 'misses': 0, 'hit_rate': 0}}
            )
        except Exception:
            cache_stats = {'memory': {'size': 0, 'max_size': 0, 'hits': 0, 'misses': 0, 'hit_rate': 0}}

        try:
            error_stats = error_tracker.get_stats()
        except Exception:
            error_stats = {}

        return APIResponse.success(
            data={
                'process': {
                    'pid': process.pid,
                    'memory_rss_mb': round(memory_info.rss / (1024 * 1024), 2),
                    'memory_vms_mb': round(memory_info.vms / (1024 * 1024), 2),
                    'memory_percent': round(memory_percent, 2),
                    'cpu_percent': process.cpu_percent(interval=0.1),
                    'threads': process.num_threads(),
                },
                'database': {
                    'type': db_type,
                    'pool_status': 'ok',
                },
                'cache': cache_stats,
                'errors': error_stats,
                'uptime_seconds': round(time.time() - process.create_time(), 0),
                'timestamp': datetime.now(UTC).isoformat(),
            }
        )
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获取系统状态失败: {e}', exc_info=True)
        return APIResponse.error('获取系统状态失败', 500)


@admin_bp.route('/backup/export')
@admin_required
def backup_export():
    try:
        from ..models.schemas import Award, AwardBook, BookMetadata, SearchHistory, TranslationCache, WeeklyReport

        tables_to_export = {
            'awards': Award.query.all(),
            'award_books': AwardBook.query.all(),
            'weekly_reports': WeeklyReport.query.all(),
            'translation_caches': TranslationCache.query.all(),
            'book_metadata': BookMetadata.query.all(),
            'search_histories': SearchHistory.query.all(),
        }

        export_data: dict[str, Any] = {
            'exported_at': datetime.now(UTC).isoformat(),
            'tables': {},
        }

        for table_name, records in tables_to_export.items():
            export_data['tables'][table_name] = {
                'count': len(records),
                'records': [r.to_dict() for r in records],
            }

        return Response(
            json_lib.dumps(export_data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=bookrank_backup.json'},
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'数据导出失败: {e}', exc_info=True)
        return APIResponse.error('数据导出失败', 500)


@admin_bp.route('/backup/import', methods=['POST'])
@csrf_protect
@admin_required
def backup_import():
    try:
        from ..models.schemas import Award, AwardBook, BookMetadata, SearchHistory, TranslationCache, WeeklyReport

        data = request.get_json(silent=True)
        if not data or 'tables' not in data:
            return APIResponse.error('无效的导入数据格式', 400)

        table_models = {
            'awards': Award,
            'award_books': AwardBook,
            'weekly_reports': WeeklyReport,
            'translation_caches': TranslationCache,
            'book_metadata': BookMetadata,
            'search_histories': SearchHistory,
        }

        imported_counts = batch_import_from_dict(table_models, data['tables'])  # type: ignore[arg-type]

        return APIResponse.success(
            data={'imported': imported_counts, 'total': sum(imported_counts.values())},
            message=f'导入完成，共导入 {sum(imported_counts.values())} 条记录',
        )
    except Exception as e:
        db.session.rollback()
        log_error(ErrorCategory.DB_QUERY, f'数据导入失败: {e}', exc_info=True)
        return APIResponse.error('数据导入失败', 500)


@admin_bp.route('/awards/seed', methods=['POST'])
@csrf_protect
@admin_required
def seed_award_books():
    """补种缺失的预置获奖图书数据（如2026年新获奖）"""
    try:
        from ..initialization.sample_award_books import init_sample_award_books

        init_sample_award_books(current_app._get_current_object())  # type: ignore[attr-defined]

        from ..models.schemas import AwardBook

        total = AwardBook.query.count()
        return APIResponse.success(
            data={'total_awards': total},
            message=f'补种完成，当前共 {total} 本获奖图书',
        )
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'补种获奖图书失败: {e}', exc_info=True)
        return APIResponse.error('补种失败', 500)
