import os
import logging
from functools import wraps
from flask import Blueprint, request, current_app, session

from ..models.database import db
from ..utils.api_helpers import APIResponse, csrf_protect
from ..utils.service_helpers import get_book_service, get_google_books_client

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
logger = logging.getLogger(__name__)

ADMIN_SECRET = os.environ.get('ADMIN_SECRET', '')


def admin_required(f):
    """绠＄悊鍛樿璇佽楗板櫒锛氫粎閫氳繃 X-Admin-Secret 璇锋眰澶存垨 session 楠岃瘉"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not ADMIN_SECRET:
            logger.warning("ADMIN_SECRET 鏈厤缃紝绠＄悊鍛樻帴鍙ｅ凡绂佺敤")
            return APIResponse.error('绠＄悊鍛樻帴鍙ｆ湭閰嶇疆锛岃璁剧疆 ADMIN_SECRET 鐜鍙橀噺', 503)
        auth_header = request.headers.get('X-Admin-Secret', '')
        session_auth = session.get('is_admin', False)
        if auth_header != ADMIN_SECRET and not session_auth:
            return APIResponse.error('闇€瑕佺鐞嗗憳鏉冮檺', 403)
        return f(*args, **kwargs)
    return wrapped


@admin_bp.route('/award-covers/sync', methods=['POST'])
@csrf_protect
@admin_required
def sync_award_covers():
    """鎵嬪姩瑙﹀彂鑾峰涔︾睄灏侀潰鍚屾"""
    try:
        from ..services.award_cover_sync_service import AwardCoverSyncService

        google_client = get_google_books_client()
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

        return APIResponse.success(data=result, message=f"鍚屾瀹屾垚: 鏇存柊{result.get('updated', 0)}锟?)

    except Exception as e:
        logger.error(f"鍚屾鑾峰涔︾睄灏侀潰澶辫触: {e}", exc_info=True)
        return APIResponse.error('鍚屾澶辫触', 500)


@admin_bp.route('/award-covers/status')
@admin_required
def get_award_covers_status():
    """鑾峰彇鑾峰涔︾睄灏侀潰鍚屾鐘讹拷?""
    try:
        from ..services.award_cover_sync_service import AwardCoverSyncService

        google_client = get_google_books_client()
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
        logger.error(f"鑾峰彇灏侀潰鐘舵€佸け锟? {e}", exc_info=True)
        return APIResponse.error('鑾峰彇鐘舵€佸け锟?, 500)


@admin_bp.route('/weekly-report/regenerate', methods=['POST'])
@csrf_protect
@admin_required
def regenerate_weekly_report():
    """鎵嬪姩閲嶆柊鐢熸垚鎸囧畾鏃ユ湡鐨勫懆锟?""
    try:
        from ..services.weekly_report_service import WeeklyReportService
        from datetime import date, timedelta

        data = request.json or {}
        report_date_str = data.get('report_date')

        if not report_date_str:
            return APIResponse.error('缂哄皯report_date鍙傛暟', 400)

        try:
            report_date = date.fromisoformat(report_date_str)
        except ValueError:
            return APIResponse.error('鏃ユ湡鏍煎紡閿欒锛屽簲涓篩YYY-MM-DD', 400)

        if report_date > date.today():
            return APIResponse.error('涓嶈兘閲嶆柊鐢熸垚鏈潵鐨勫懆锟?, 400)

        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('鏈嶅姟涓嶅彲锟?, 503)
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
                'message': f"宸叉垚鍔熼噸鏂扮敓锟?{report_date} 鐨勫懆锟?
            }, message="鍛ㄦ姤閲嶆柊鐢熸垚鎴愬姛")
        else:
            return APIResponse.error('鐢熸垚澶辫触锛氭暟鎹笉瓒虫垨AI鏈嶅姟寮傚父', 500)

    except Exception as e:
        logger.error(f"閲嶆柊鐢熸垚鍛ㄦ姤澶辫触: {e}", exc_info=True)
        return APIResponse.error(f'閲嶆柊鐢熸垚澶辫触: {str(e)}', 500)


@admin_bp.route('/weekly-report/regenerate-all', methods=['POST'])
@csrf_protect
@admin_required
def regenerate_all_weekly_reports():
    """鎵归噺閲嶆柊鐢熸垚鎵€鏈夋湁闂鐨勫懆锟?""
    try:
        from ..services.weekly_report_service import WeeklyReportService
        from ..models.schemas import WeeklyReport

        prompt_markers = ['璇蜂负', '瑕佹眰锟?, '鍩轰簬浠ヤ笅鍒嗘瀽缁撴灉']
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
                'message': '鎵€鏈夊懆鎶ユ甯革紝鏃犻渶閲嶆柊鐢熸垚'
            }, message='鎵€鏈夊懆鎶ユ暟鎹锟?)

        book_service = get_book_service()
        if not book_service:
            return APIResponse.error('鏈嶅姟涓嶅彲锟?, 503)
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
                    'error': None if new_report else '鐢熸垚澶辫触'
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
            'message': f"鎴愬姛淇 {success_count}/{len(problematic_reports)} 浠藉懆锟?
        }, message=f"鎵归噺淇瀹屾垚锛歿success_count}浠芥垚锟?)

    except Exception as e:
        logger.error(f"鎵归噺閲嶆柊鐢熸垚鍛ㄦ姤澶辫触: {e}", exc_info=True)
        return APIResponse.error(f'鎵归噺淇澶辫触: {str(e)}', 500)


@admin_bp.route('/categories/cleanup', methods=['GET', 'POST'])
@admin_required
def cleanup_categories():
    """娓呯悊鏂颁功鍒嗙被涓殑钀ラ攢鏂囨鏁版嵁"""
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
            id_to_category = {item['id']: item['new_category'] for item in invalid_books}
            books_to_update = db.session.query(NewBook).filter(
                NewBook.id.in_(id_to_category.keys())
            ).all()
            for book in books_to_update:
                book.category = id_to_category[book.id]
            db.session.commit()
            return APIResponse.success(data={
                'total_checked': len(books),
                'invalid_found': len(invalid_books),
                'updated': len(books_to_update),
                'details': invalid_books[:50]
            }, message=f"娓呯悊瀹屾垚: 淇{len(books_to_update)}鏉″垎绫绘暟锟?)
        else:
            return APIResponse.success(data={
                'total_checked': len(books),
                'invalid_found': len(invalid_books),
                'details': invalid_books[:50],
                'message': '棰勮妯″紡锛屾湭瀹為檯淇敼銆傚彂锟?dry_run=false 鎵ц娓呯悊'
            }, message=f"棰勮: 鍙戠幇{len(invalid_books)}鏉℃棤鏁堝垎锟?)

    except Exception as e:
        logger.error(f"娓呯悊鍒嗙被鏁版嵁澶辫触: {e}", exc_info=True)
        return APIResponse.error(f'娓呯悊澶辫触: {str(e)}', 500)


def _clean_report_text(text: str) -> str:
    """娓呯悊鍛ㄦ姤鏂囨湰涓殑涔﹀悕姹℃煋"""
    if not text:
        return text
    from ..services.weekly_report_service import _format_book_title
    text = re.sub(r'銆妠2,}', '锟?, text)
    text = re.sub(r'銆媨2,}', '锟?, text)
    text = re.sub(r'\*\*锟?[^銆媇+)銆媆*\*', r'銆奬1锟?, text)
    text = re.sub(r'\*锟?[^銆媇+)銆媆*', r'銆奬1锟?, text)
    text = re.sub(r'锟?[^銆媆n]+)銆媆n[^銆奬n]*(?:\n[^銆奬n]*)*', lambda m: _format_book_title(m.group(0)), text)
    return text


@admin_bp.route('/reports/clean-brackets', methods=['GET', 'POST'])
@admin_required
def clean_report_brackets():
    """娓呯悊鍛ㄦ姤涓殑涔﹀悕姹℃煋锛堝弻涔﹀悕鍙枫€乵arkdown銆佷綔鑰呭悕娣峰叆銆侀暱鎻忚堪绛夛級"""
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
                report = db.session.get(WeeklyReport, item['id'])
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
                'updated': len(books_to_update),
                'details': fixable
            }, message=f"娓呯悊瀹屾垚: 淇{len(books_to_update)}浠藉懆锟?)
        else:
            return APIResponse.success(data={
                'total_reports': len(reports),
                'fixable': len(fixable),
                'details': fixable,
                'message': '棰勮妯″紡锛屾湭瀹為檯淇敼銆傚彂锟?dry_run=false 鎵ц娓呯悊'
            }, message=f"棰勮: 鍙戠幇{len(fixable)}浠藉懆鎶ユ湁闂")

    except Exception as e:
        db.session.rollback()
        logger.error(f"娓呯悊鍛ㄦ姤涔﹀悕鍙峰け锟? {e}", exc_info=True)
        return APIResponse.error(f'娓呯悊澶辫触: {str(e)}', 500)


@admin_bp.route('/reports/fix-truncated-titles', methods=['GET', 'POST'])
@admin_required
def fix_truncated_titles():
    """淇琚埅鏂殑涔﹀悕锛堜粠鍏朵粬鏁版嵁婧愭仮澶嶏級"""
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

                    clean_title = title.strip('銆婏拷?).strip()
                    if len(clean_title) <= 2 and '锟? in title:
                        isbn = book.get('isbn', '')
                        if isbn and isbn in book_metadata_map:
                            correct_title = book_metadata_map[isbn]
                            details.append({
                                'report_date': str(report.report_date),
                                'section': key,
                                'old_title': title,
                                'new_title': f'銆妠correct_title}锟?,
                                'source': 'book_metadata'
                            })
                            book['title'] = f'銆妠correct_title}锟?
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
            'message': '棰勮妯″紡' if dry_run else f'宸蹭慨澶峽fixed_count}浠藉懆锟?
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"淇鎴柇涔﹀悕澶辫触: {e}", exc_info=True)
        return APIResponse.error(f'淇澶辫触: {str(e)}', 500)


@admin_bp.route('/translations/cleanup', methods=['GET', 'POST'])
@admin_required
def cleanup_translations():
    """娓呯悊缈昏瘧缂撳瓨鍜孊ookMetadata涓薄鏌撶殑涔﹀悕"""
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
            if any(label in text for label in ['涔﹀悕锟?, '浣滆€咃細', '绠€浠嬶細', 'Title:', 'Author:']):
                return True
            if '路' in text:
                if '锟? not in text and len(text) > 10:
                    return True
                if re.search(r'[\u4e00-\u9fff]+\s*路\s*[\u4e00-\u9fff]+\s*路?\s*锟?, text):
                    return True
            if text.endswith('锟?) and len(text) > 2:
                return True
            if '銆婏拷? in text:
                return True
            bracket_match = re.search(r'銆奫^銆媇+锟?, text)
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
            t_ids = [item['id'] for item in fixable_translations]
            if t_ids:
                t_records_to_update = db.session.query(TranslationCache).filter(
                    TranslationCache.id.in_(t_ids)
                ).all()
                for record in t_records_to_update:
                    record.translated_text = clean_translation_text(record.translated_text)
            else:
                t_records_to_update = []

            m_isbn_list = [item['isbn'] for item in fixable_metadata]
            if m_isbn_list:
                m_records_to_update = db.session.query(BookMetadata).filter(
                    BookMetadata.isbn.in_(m_isbn_list)
                ).all()
                for record in m_records_to_update:
                    record.title_zh = clean_translation_text(record.title_zh, field_type='title')
            else:
                m_records_to_update = []

            db.session.commit()
            return APIResponse.success(data={
                'translation_cache': {'total': len(t_records), 'fixed': len(t_records_to_update)},
                'book_metadata': {'total': len(m_records), 'fixed': len(m_records_to_update)},
                'details_translations': fixable_translations[:20],
                'details_metadata': fixable_metadata[:20]
            }, message=f"娓呯悊瀹屾垚: 淇{len(t_records_to_update)}鏉＄紦锟?+ {len(m_records_to_update)}鏉″厓鏁版嵁")
        else:
            return APIResponse.success(data={
                'translation_cache': {'total': len(t_records), 'fixable': len(fixable_translations)},
                'book_metadata': {'total': len(m_records), 'fixable': len(fixable_metadata)},
                'details_translations': fixable_translations[:20],
                'details_metadata': fixable_metadata[:20],
                'message': '棰勮妯″紡锛屾湭瀹為檯淇敼銆傚彂锟?dry_run=false 鎵ц娓呯悊'
            }, message=f"棰勮: 鍙戠幇{total_fixable}鏉¤姹℃煋鐨勭炕璇戞暟锟?)

    except Exception as e:
        logger.error(f"娓呯悊缈昏瘧缂撳瓨澶辫触: {e}", exc_info=True)
        return APIResponse.error(f'娓呯悊澶辫触: {str(e)}', 500)


