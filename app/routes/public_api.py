import logging
import re
from datetime import datetime

from flask import Blueprint, current_app, request
from ..services.award_book_service import AwardBookService
from ..utils.api_helpers import PublicAPIResponse, public_rate_limit, validate_isbn
from ..utils.service_helpers import get_book_service

logger = logging.getLogger(__name__)

public_api_bp = Blueprint('public_api', __name__, url_prefix='/api/public')

_award_service = AwardBookService()


@public_api_bp.route('/bestsellers')
@public_rate_limit(max_requests=60, window=60)
def get_all_bestsellers():
    try:
        limit = min(request.args.get('limit', 10, type=int), 50)
        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        categories = current_app.config.get('CATEGORIES', {})

        all_books = {}
        for cat_id, cat_name in categories.items():
            books = book_service.get_books_by_category(cat_id)
            all_books[cat_id] = {'category_name': cat_name, 'books': [book.to_dict() for book in books[:limit]]}

        return PublicAPIResponse.success(
            data={'categories': categories, 'books': all_books, 'last_updated': book_service.get_latest_cache_time()}
        )

    except Exception as e:
        logger.error(f'Error in get_all_bestsellers: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/bestsellers/<category>')
@public_rate_limit(max_requests=60, window=60)
def get_bestsellers_by_category(category: str):
    try:
        categories = current_app.config.get('CATEGORIES', {})
        if category not in categories:
            return PublicAPIResponse.error(f'Invalid category. Available categories: {list(categories.keys())}', 400)

        limit = min(request.args.get('limit', 20, type=int), 50)
        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        books = book_service.get_books_by_category(category)

        return PublicAPIResponse.success(
            data={
                'category_id': category,
                'category_name': categories[category],
                'books': [book.to_dict() for book in books[:limit]],
                'total': len(books),
                'last_updated': book_service.get_latest_cache_time(),
            }
        )

    except Exception as e:
        logger.error(f'Error in get_bestsellers_by_category: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/bestsellers/search')
@public_rate_limit(max_requests=30, window=60)
def search_bestsellers():
    try:
        keyword = request.args.get('keyword', '').strip()

        if not keyword:
            return PublicAPIResponse.error('Keyword is required', 400)
        if len(keyword) < 2:
            return PublicAPIResponse.error('Keyword must be at least 2 characters', 400)
        if len(keyword) > 100:
            return PublicAPIResponse.error('Keyword must be at most 100 characters', 400)
        if not re.match(r'^[\w\s\-\u4e00-\u9fff]+$', keyword):
            return PublicAPIResponse.error('Invalid keyword format', 400)

        limit = min(request.args.get('limit', 20, type=int), 50)
        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        results = book_service.search_books(keyword)

        return PublicAPIResponse.success(
            data={'keyword': keyword, 'books': [book.to_dict() for book in results[:limit]], 'total': len(results)}
        )

    except Exception as e:
        logger.error(f'Error in search_bestsellers: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/awards')
@public_rate_limit(max_requests=60, window=60)
def get_all_awards():
    try:
        awards = _award_service.get_all_awards()

        book_counts = _award_service.get_book_counts_by_award(displayable_only=True)

        awards_data = []
        for award in awards:
            awards_data.append(
                {
                    'id': award.id,
                    'name': award.name,
                    'name_en': award.name_en,
                    'description': award.description,
                    'book_count': book_counts.get(award.id, 0),
                }
            )

        return PublicAPIResponse.success(data={'awards': awards_data, 'total': len(awards_data)})

    except Exception as e:
        logger.error(f'Error in get_all_awards: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/awards/<award_name>')
@public_rate_limit(max_requests=60, window=60)
def get_award_books(award_name: str):
    try:
        award = _award_service.get_award_by_name(award_name)
        if not award:
            return PublicAPIResponse.error('Award not found', 404)

        year = request.args.get('year', type=int)
        limit = min(request.args.get('limit', 20, type=int), 50)
        books, _ = _award_service.get_award_books(
            award_id=award.id, year=year, include_displayable_only=True, page=1, limit=limit
        )

        years = _award_service.get_distinct_years(award_id=award.id)

        return PublicAPIResponse.success(
            data={
                'award': {
                    'id': award.id,
                    'name': award.name,
                    'name_en': award.name_en,
                    'description': award.description,
                },
                'books': [book.to_dict() for book in books],
                'total': len(books),
                'years': years,
            }
        )

    except Exception as e:
        logger.error(f'Error in get_award_books: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/awards/<award_name>/<int:year>')
@public_rate_limit(max_requests=60, window=60)
def get_award_books_by_year(award_name: str, year: int):
    try:
        award = _award_service.get_award_by_name(award_name)
        if not award:
            return PublicAPIResponse.error('Award not found', 404)

        books, _ = _award_service.get_award_books(
            award_id=award.id, year=year, include_displayable_only=True, page=1, limit=1000
        )

        if not books:
            return PublicAPIResponse.error(f'No books found for {award_name} in {year}', 404)

        return PublicAPIResponse.success(
            data={
                'award': {'id': award.id, 'name': award.name, 'name_en': award.name_en},
                'year': year,
                'books': [book.to_dict() for book in books],
                'total': len(books),
            }
        )

    except Exception as e:
        logger.error(f'Error in get_award_books_by_year: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/book/<isbn>')
@public_rate_limit(max_requests=60, window=60)
def get_book_details(isbn: str):
    try:
        if not validate_isbn(isbn):
            return PublicAPIResponse.error('Invalid ISBN format', 400)

        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        all_books = []
        for cat_id in current_app.config['CATEGORIES']:
            all_books.extend(book_service.get_books_by_category(cat_id))

        book = next((b for b in all_books if b.isbn13 == isbn), None)
        if book:
            return PublicAPIResponse.success(data={'book': book.to_dict(), 'source': 'bestseller'})

        award_book = _award_service.find_award_book_by_isbn(isbn)
        if award_book:
            return PublicAPIResponse.success(data={'book': award_book.to_dict(), 'source': 'award'})

        return PublicAPIResponse.error('Book not found', 404)

    except Exception as e:
        logger.error(f'Error in get_book_details: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/reports/weekly')
@public_rate_limit(max_requests=60, window=60)
def get_weekly_reports():
    try:
        from ..services.weekly_report_service import WeeklyReportService

        limit = min(request.args.get('limit', 10, type=int), 50)
        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        report_service = WeeklyReportService(book_service)
        reports = report_service.get_reports(limit)

        return PublicAPIResponse.success(
            data={'reports': [report.to_dict() for report in reports], 'total': len(reports)}
        )

    except Exception as e:
        logger.error(f'Error in get_weekly_reports: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/reports/weekly/latest')
@public_rate_limit(max_requests=60, window=60)
def get_latest_weekly_report():
    try:
        from ..services.weekly_report_service import WeeklyReportService

        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        report_service = WeeklyReportService(book_service)
        report = report_service.get_latest_report()

        if not report:
            return PublicAPIResponse.error('No report available', 404)

        return PublicAPIResponse.success(data={'report': report.to_dict()})

    except Exception as e:
        logger.error(f'Error in get_latest_weekly_report: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/reports/weekly/<date>')
@public_rate_limit(max_requests=60, window=60)
def get_weekly_report_by_date(date: str):
    try:
        from ..services.weekly_report_service import WeeklyReportService

        try:
            report_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return PublicAPIResponse.error('Invalid date format. Use YYYY-MM-DD', 400)

        book_service = get_book_service()
        if not book_service:
            return PublicAPIResponse.error('Service unavailable', 503)
        report_service = WeeklyReportService(book_service)
        report = report_service.get_report_by_date(report_date)

        if not report:
            return PublicAPIResponse.error('Report not found', 404)

        return PublicAPIResponse.success(data={'report': report.to_dict()})

    except Exception as e:
        logger.error(f'Error in get_weekly_report_by_date: {e}', exc_info=True)
        return PublicAPIResponse.error('Internal server error', 500)


@public_api_bp.route('/')
def api_info():
    return PublicAPIResponse.success(
        data={
            'name': 'BookRank Public API',
            'version': '1.1.0',
            'description': '提供畅销书排行榜和获奖图书数据的公开API',
            'endpoints': [
                {'path': '/api/public/bestsellers', 'method': 'GET', 'description': '获取所有分类畅销书'},
                {'path': '/api/public/bestsellers/<category>', 'method': 'GET', 'description': '获取指定分类畅销书'},
                {'path': '/api/public/bestsellers/search', 'method': 'GET', 'description': '搜索畅销书'},
                {'path': '/api/public/awards', 'method': 'GET', 'description': '获取所有奖项列表'},
                {'path': '/api/public/awards/<award_name>', 'method': 'GET', 'description': '获取指定奖项的获奖图书'},
                {
                    'path': '/api/public/awards/<award_name>/<year>',
                    'method': 'GET',
                    'description': '获取指定奖项和年份的获奖图书',
                },
                {'path': '/api/public/book/<isbn>', 'method': 'GET', 'description': '获取图书详细信息'},
                {'path': '/api/public/reports/weekly', 'method': 'GET', 'description': '获取周报列表'},
                {'path': '/api/public/reports/weekly/latest', 'method': 'GET', 'description': '获取最新周报'},
                {'path': '/api/public/reports/weekly/<date>', 'method': 'GET', 'description': '根据日期获取周报'},
            ],
            'rate_limit': '60 requests per minute per IP',
            'documentation': 'https://github.com/gongyijie85/bookrank#api-documentation',
        }
    )
