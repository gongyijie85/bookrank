"""周报功能测试"""

from datetime import date, timedelta
from unittest.mock import patch

from app.models.book import Book
from app.models.schemas import Award, AwardBook, WeeklyReport


def _create_test_award_books(app, db):
    """创建测试用的获奖图书数据"""
    with app.app_context():
        award = Award(name='测试奖项', name_en='Test Award', country='US', category_count=1)
        db.session.add(award)
        db.session.flush()

        for i in range(5):
            book = AwardBook(
                award_id=award.id,
                year=2026,
                category='Fiction',
                rank=i + 1,
                title=f'Test Book {i + 1}',
                author=f'Author {i + 1}',
                description='Test description',
                is_displayable=True,
            )
            db.session.add(book)
        db.session.commit()


def _make_mock_books(count=5):
    """创建模拟的Book对象列表"""
    books = []
    for i in range(count):
        book = Book(
            id=f'978000000000{i + 1}',
            title=f'Test Book {i + 1}',
            author=f'Author {i + 1}',
            publisher='Test Publisher',
            cover=f'https://example.com/cover{i + 1}.jpg',
            list_name='Hardcover Fiction',
            category_id='hardcover-fiction',
            category_name='精装小说',
            rank=i + 1,
            weeks_on_list=i + 1,
            rank_last_week=str(i + 2) if i > 0 else '0',
            published_date='2026-04-25',
            description=f'Description for book {i + 1}',
            details=f'Details for book {i + 1}',
            publication_dt='2026-04-25',
            page_count='300',
            language='en',
            buy_links=[],
            isbn13=f'978000000000{i + 1}',
            isbn10=f'000000000{i + 1}',
            price='$25.00',
            title_zh=f'测试书籍{i + 1}',
            description_zh=f'测试描述{i + 1}',
            details_zh=f'测试详情{i + 1}',
        )
        books.append(book)
    return books


def _create_book_service():
    """创建用于测试的BookService实例"""
    from pathlib import Path

    from app.services import (
        BookService,
        CacheService,
        FileCache,
        GoogleBooksClient,
        ImageCacheService,
        MemoryCache,
        NYTApiClient,
    )

    memory_cache = MemoryCache(default_ttl=3600, max_size=1000)
    file_cache = FileCache(cache_dir=Path('cache'), default_ttl=86400)
    cache_service = CacheService(memory_cache, file_cache)

    nyt_client = NYTApiClient(
        api_key='', base_url='https://api.nytimes.com/svc/books/v3', rate_limiter=None, timeout=15
    )

    google_client = GoogleBooksClient(api_key=None, base_url='https://www.googleapis.com/books/v1', timeout=8)

    image_cache = ImageCacheService(cache_dir=Path('static/cache'), default_cover='/static/default-cover.png')

    book_service = BookService(
        nyt_client=nyt_client,
        google_client=google_client,
        cache_service=cache_service,
        image_cache=image_cache,
        max_workers=4,
        categories=['Fiction', 'Nonfiction', 'Mystery', 'Science Fiction'],
    )
    return book_service


def test_weekly_report_model(app, db):
    """测试周报数据模型"""
    with app.app_context():
        report_date = date.today()
        week_start = report_date - timedelta(days=7)
        week_end = report_date - timedelta(days=1)

        report = WeeklyReport(
            report_date=report_date,
            week_start=week_start,
            week_end=week_end,
            title='测试周报',
            summary='测试摘要',
            content='{"top_changes": []}',
            top_changes='[]',
            featured_books='[]',
        )

        db.session.add(report)
        db.session.commit()

        saved_report = WeeklyReport.query.first()
        assert saved_report is not None
        assert saved_report.title == '测试周报'
        assert saved_report.week_start == week_start
        assert saved_report.week_end == week_end


def test_weekly_report_service(app, db):
    """测试周报服务"""
    with app.app_context():
        _create_test_award_books(app, db)

        book_service = _create_book_service()
        mock_books = _make_mock_books(5)

        from app.services.weekly_report_service import WeeklyReportService

        report_service = WeeklyReportService(book_service)

        week_start = date.today() - timedelta(days=14)
        week_end = date.today() - timedelta(days=8)

        with patch.object(book_service, 'get_books_by_category', return_value=mock_books):
            report = report_service.generate_report(week_start, week_end)

        assert report is not None
        assert report.title is not None
        assert report.summary is not None
        assert report.content is not None
        assert report.week_start == week_start
        assert report.week_end == week_end


def test_weekly_report_duplicate(app, db):
    """测试重复生成周报"""
    with app.app_context():
        _create_test_award_books(app, db)

        book_service = _create_book_service()
        mock_books = _make_mock_books(5)

        from app.services.weekly_report_service import WeeklyReportService

        report_service = WeeklyReportService(book_service)

        week_start = date.today() - timedelta(days=21)
        week_end = date.today() - timedelta(days=15)

        with patch.object(book_service, 'get_books_by_category', return_value=mock_books):
            report1 = report_service.generate_report(week_start, week_end)
        assert report1 is not None

        report2 = report_service.generate_report(week_start, week_end)
        assert report2 is not None
        assert report2.id == report1.id


def test_weekly_report_task(app, db):
    """测试周报定时任务"""
    with app.app_context():
        from app.tasks.weekly_report_task import generate_weekly_report

        report = generate_weekly_report()
        assert report is None or isinstance(report, WeeklyReport)


def test_weekly_report_analysis(app, db):
    """测试周报分析功能"""
    with app.app_context():
        _create_test_award_books(app, db)

        book_service = _create_book_service()
        mock_books = _make_mock_books(5)

        from app.services.weekly_report_service import WeeklyReportService

        report_service = WeeklyReportService(book_service)

        week_start = date.today() - timedelta(days=28)
        week_end = date.today() - timedelta(days=22)

        with patch.object(book_service, 'get_books_by_category', return_value=mock_books):
            weekly_data = report_service._collect_weekly_data(week_start, week_end)
        assert 'books' in weekly_data
        assert len(weekly_data['books']) > 0

        analysis = report_service._analyze_changes(weekly_data)
        assert 'top_changes' in analysis
        assert 'new_books' in analysis
        assert 'top_risers' in analysis
        assert 'longest_running' in analysis
        assert 'featured_books' in analysis

        summary = report_service._generate_default_summary(analysis, week_start, week_end)
        assert len(summary) > 0
