import re
import logging
from flask import Blueprint, request, current_app

from ..models.database import db
from ..utils.api_helpers import APIResponse, csrf_protect

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
logger = logging.getLogger(__name__)


def _get_google_client():
    """从应用扩展获取 GoogleBooksClient，避免重复创建"""
    book_service = current_app.extensions.get('book_service')
    if book_service and hasattr(book_service, '_google_client'):
        return book_service._google_client
    return None


@admin_bp.route('/award-covers/sync', methods=['POST'])
@csrf_protect
def sync_award_covers():
    """手动触发获奖书籍封面同步"""
    try:
        from ..services.award_cover_sync_service import AwardCoverSyncService

        google_client = _get_google_client()
        if not google_client:
            from ..services.google_books_client import GoogleBooksClient
            from ..config import Config
            google_client = GoogleBooksClient(
                api_key=Config.GOOGLE_API_KEY,
                base_url='https://www.googleapis.com/books/v1/volumes'
            )

        sync_service = AwardCoverSyncService(google_client)

        data = request.get_json(silent=True) or {}
        batch_size = min(max(1, data.get('batch_size', 10)), 50)

        result = sync_service.sync_missing_covers(batch_size=batch_size, delay=0.3)

        return APIResponse.success(data=result, message=f"同步完成: 更新{result.get('updated', 0)}本")

    except Exception as e:
        logger.error(f"同步获奖书籍封面失败: {e}", exc_info=True)
        return APIResponse.error('同步失败', 500)


@admin_bp.route('/award-covers/status')
def get_award_covers_status():
    """获取获奖书籍封面同步状态"""
    try:
        from ..services.award_cover_sync_service import AwardCoverSyncService

        google_client = _get_google_client()
        if not google_client:
            from ..services.google_books_client import GoogleBooksClient
            google_client = GoogleBooksClient(
                api_key=None,
                base_url='https://www.googleapis.com/books/v1/volumes'
            )

        sync_service = AwardCoverSyncService(google_client)
        status = sync_service.get_sync_status()

        return APIResponse.success(data=status)

    except Exception as e:
        logger.error(f"获取封面状态失败: {e}", exc_info=True)
        return APIResponse.error('获取状态失败', 500)


@admin_bp.route('/weekly-report/regenerate', methods=['POST'])
@csrf_protect
def regenerate_weekly_report():
    """手动重新生成指定日期的周报"""
    try:
        from ..services.weekly_report_service import WeeklyReportService
        from datetime import date, timedelta

        data = request.json or {}
        report_date_str = data.get('report_date')

        if not report_date_str:
            return APIResponse.error('缺少report_date参数', 400)

        try:
            report_date = date.fromisoformat(report_date_str)
        except ValueError:
            return APIResponse.error('日期格式错误，应为YYYY-MM-DD', 400)

        if report_date > date.today():
            return APIResponse.error('不能重新生成未来的周报', 400)

        book_service = current_app.extensions.get('book_service')
        weekly_service = WeeklyReportService(book_service)

        weekday = report_date.weekday()
        week_start = report_date - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)

        report = weekly_service.generate_report(week_start, week_end, force_regenerate=True)

        if report:
            return APIResponse.success(data={
                'report_id': report.id,
                'report_date': report_date.isoformat(),
                'week_start': week_start.isoformat(),
                'week_end': week_end.isoformat(),
                'title': report.title,
                'message': f"已成功重新生成 {report_date} 的周报"
            }, message="周报重新生成成功")
        else:
            return APIResponse.error('生成失败：数据不足或AI服务异常', 500)

    except Exception as e:
        logger.error(f"重新生成周报失败: {e}", exc_info=True)
        return APIResponse.error(f'重新生成失败: {str(e)}', 500)


@admin_bp.route('/weekly-report/regenerate-all', methods=['POST'])
@csrf_protect
def regenerate_all_weekly_reports():
    """批量重新生成所有有问题的周报"""
    try:
        from ..services.weekly_report_service import WeeklyReportService
        from ..models.schemas import WeeklyReport

        prompt_markers = ['请为', '要求：', '基于以下分析结果']
        problematic_reports = []

        reports = WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).all()
        for report in reports:
            summary = (report.summary or '')
            if any(marker in summary for marker in prompt_markers):
                problematic_reports.append(report)

        if not problematic_reports:
            return APIResponse.success(data={
                'total_checked': len(reports),
                'regenerated': 0,
                'message': '所有周报正常，无需重新生成'
            }, message='所有周报数据正常')

        book_service = current_app.extensions.get('book_service')
        weekly_service = WeeklyReportService(book_service)

        results = []
        for report in problematic_reports:
            try:
                new_report = weekly_service.generate_report(
                    report.week_start, report.week_end,
                    force_regenerate=True
                )
                results.append({
                    'date': report.report_date.isoformat(),
                    'success': new_report is not None,
                    'error': None if new_report else '生成失败'
                })
            except Exception as e:
                results.append({
                    'date': report.report_date.isoformat(),
                    'success': False,
                    'error': str(e)
                })

        success_count = sum(1 for r in results if r['success'])

        return APIResponse.success(data={
            'total_problematic': len(problematic_reports),
            'regenerated': success_count,
            'details': results,
            'message': f"成功修复 {success_count}/{len(problematic_reports)} 份周报"
        }, message=f"批量修复完成：{success_count}份成功")

    except Exception as e:
        logger.error(f"批量重新生成周报失败: {e}", exc_info=True)
        return APIResponse.error(f'批量修复失败: {str(e)}', 500)


@admin_bp.route('/categories/cleanup', methods=['GET', 'POST'])
def cleanup_categories():
    """清理新书分类中的营销文案数据"""
    try:
        from ..models.new_book import NewBook
        from ..services.new_book_service import NewBookService

        if request.method == 'GET':
            dry_run = True
        else:
            data = request.get_json(silent=True) or {}
            dry_run = data.get('dry_run', True)

        books = NewBook.query.filter(NewBook.category.isnot(None)).all()

        invalid_books = []
        for book in books:
            cleaned = NewBookService._sanitize_category(book.category)
            if cleaned != book.category:
                invalid_books.append({
                    'id': book.id,
                    'title': book.title,
                    'old_category': book.category,
                    'new_category': cleaned
                })

        if not dry_run:
            updated = 0
            for item in invalid_books:
                book = NewBook.query.get(item['id'])
                if book:
                    book.category = item['new_category']
                    updated += 1
            db.session.commit()
            return APIResponse.success(data={
                'total_checked': len(books),
                'invalid_found': len(invalid_books),
                'updated': updated,
                'details': invalid_books[:50]
            }, message=f"清理完成: 修复{updated}条分类数据")
        else:
            return APIResponse.success(data={
                'total_checked': len(books),
                'invalid_found': len(invalid_books),
                'details': invalid_books[:50],
                'message': '预览模式，未实际修改。发送 dry_run=false 执行清理'
            }, message=f"预览: 发现{len(invalid_books)}条无效分类")

    except Exception as e:
        logger.error(f"清理分类数据失败: {e}", exc_info=True)
        return APIResponse.error(f'清理失败: {str(e)}', 500)


def _clean_report_text(text: str) -> str:
    """清理周报文本中的书名污染"""
    if not text:
        return text
    from ..services.weekly_report_service import _format_book_title
    text = re.sub(r'《{2,}', '《', text)
    text = re.sub(r'》{2,}', '》', text)
    text = re.sub(r'\*\*《([^》]+)》\*\*', r'《\1》', text)
    text = re.sub(r'\*《([^》]+)》\*', r'《\1》', text)
    text = re.sub(r'《([^》\n]+)》\n[^《\n]*(?:\n[^《\n]*)*', lambda m: _format_book_title(m.group(0)), text)
    return text


@admin_bp.route('/reports/clean-brackets', methods=['GET', 'POST'])
def clean_report_brackets():
    """清理周报中的书名污染（双书名号、markdown、作者名混入、长描述等）"""
    try:
        from ..models.schemas import WeeklyReport
        from ..services.weekly_report_service import _format_book_title
        import json as json_lib

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
                fixable.append({
                    'id': report.id,
                    'report_date': str(report.report_date),
                    'issues': issues
                })

        if not dry_run:
            updated = 0
            for item in fixable:
                report = WeeklyReport.query.get(item['id'])
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
            return APIResponse.success(data={
                'total_reports': len(reports),
                'fixable': len(fixable),
                'updated': updated,
                'details': fixable
            }, message=f"清理完成: 修复{updated}份周报")
        else:
            return APIResponse.success(data={
                'total_reports': len(reports),
                'fixable': len(fixable),
                'details': fixable,
                'message': '预览模式，未实际修改。发送 dry_run=false 执行清理'
            }, message=f"预览: 发现{len(fixable)}份周报有问题")

    except Exception as e:
        logger.error(f"清理周报书名号失败: {e}", exc_info=True)
        return APIResponse.error(f'清理失败: {str(e)}', 500)


@admin_bp.route('/reports/fix-truncated-titles', methods=['GET', 'POST'])
def fix_truncated_titles():
    """修复被截断的书名（从其他数据源恢复）"""
    try:
        from ..models.schemas import WeeklyReport, BookMetadata
        import json as json_lib

        if request.method == 'GET':
            dry_run = True
        else:
            data = request.get_json(silent=True) or {}
            dry_run = data.get('dry_run', True)

        book_metadata_map = {}
        all_books = BookMetadata.query.all()
        for book in all_books:
            if book.isbn and book.title_cn:
                book_metadata_map[book.isbn] = book.title_cn

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
                            details.append({
                                'report_date': str(report.report_date),
                                'section': key,
                                'old_title': title,
                                'new_title': f'《{correct_title}》',
                                'source': 'book_metadata'
                            })
                            book['title'] = f'《{correct_title}》'
                            report_fixed = True

            if report_fixed:
                fixed_count += 1
                if not dry_run:
                    report.content = json_lib.dumps(content, ensure_ascii=False)

        if not dry_run and fixed_count > 0:
            db.session.commit()

        return APIResponse.success(data={
            'total_reports': len(reports),
            'fixed': fixed_count,
            'details': details[:50],
            'dry_run': dry_run,
            'message': '预览模式' if dry_run else f'已修复{fixed_count}份周报'
        })

    except Exception as e:
        logger.error(f"修复截断书名失败: {e}", exc_info=True)
        return APIResponse.error(f'修复失败: {str(e)}', 500)


@admin_bp.route('/translations/cleanup', methods=['GET', 'POST'])
def cleanup_translations():
    """清理翻译缓存和BookMetadata中污染的书名"""
    try:
        from ..models.schemas import TranslationCache, BookMetadata
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
            if '·' in text:
                if '《' not in text and len(text) > 10:
                    return True
                if re.search(r'[\u4e00-\u9fff]+\s*·\s*[\u4e00-\u9fff]+\s*·?\s*《', text):
                    return True
            if text.endswith('译') and len(text) > 2:
                return True
            if '《《' in text:
                return True
            bracket_match = re.search(r'《[^》]+》', text)
            if bracket_match and len(text[bracket_match.end():].strip()) > 5:
                return True
            if '\n' in text and len(text) > 30:
                return True
            return False

        fixable_translations = []
        fixable_metadata = []

        t_records = TranslationCache.query.filter(
            TranslationCache.target_lang == 'zh'
        ).all()
        for record in t_records:
            text = record.translated_text or ''
            if is_dirty(text):
                cleaned = clean_translation_text(text)
                if cleaned != text:
                    fixable_translations.append({
                        'id': record.id,
                        'source': record.source_text[:50],
                        'before': text[:100],
                        'after': cleaned[:100]
                    })

        m_records = BookMetadata.query.filter(
            BookMetadata.title_zh.isnot(None)
        ).all()
        for record in m_records:
            text = record.title_zh or ''
            if is_dirty(text):
                cleaned = clean_translation_text(text, field_type='title')
                if cleaned != text:
                    fixable_metadata.append({
                        'isbn': record.isbn,
                        'source': record.title[:50],
                        'before': text[:100],
                        'after': cleaned[:100]
                    })

        total_fixable = len(fixable_translations) + len(fixable_metadata)

        if not dry_run:
            t_updated = 0
            for item in fixable_translations:
                record = TranslationCache.query.get(item['id'])
                if record:
                    record.translated_text = clean_translation_text(record.translated_text)
                    t_updated += 1

            m_updated = 0
            for item in fixable_metadata:
                record = BookMetadata.query.get(item['isbn'])
                if record:
                    record.title_zh = clean_translation_text(record.title_zh, field_type='title')
                    m_updated += 1

            db.session.commit()
            return APIResponse.success(data={
                'translation_cache': {'total': len(t_records), 'fixed': t_updated},
                'book_metadata': {'total': len(m_records), 'fixed': m_updated},
                'details_translations': fixable_translations[:20],
                'details_metadata': fixable_metadata[:20]
            }, message=f"清理完成: 修复{t_updated}条缓存 + {m_updated}条元数据")
        else:
            return APIResponse.success(data={
                'translation_cache': {'total': len(t_records), 'fixable': len(fixable_translations)},
                'book_metadata': {'total': len(m_records), 'fixable': len(fixable_metadata)},
                'details_translations': fixable_translations[:20],
                'details_metadata': fixable_metadata[:20],
                'message': '预览模式，未实际修改。发送 dry_run=false 执行清理'
            }, message=f"预览: 发现{total_fixable}条被污染的翻译数据")

    except Exception as e:
        logger.error(f"清理翻译缓存失败: {e}", exc_info=True)
        return APIResponse.error(f'清理失败: {str(e)}', 500)
