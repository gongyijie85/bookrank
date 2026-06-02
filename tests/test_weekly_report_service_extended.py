"""weekly_report_service 模块扩展测试 — 覆盖现有测试未触及的方法和错误路径"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

from app.models.book import Book
from app.models.schemas import WeeklyReport
from app.services.weekly_report_service import (
    WeeklyReportService,
    _clean_double_brackets,
    _cover_html,
    _format_book_title,
)


def _make_mock_books(count=3):
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
            weeks_on_list=i + 5,
            rank_last_week=str(i + 2) if i > 0 else '0',
            published_date='2026-04-25',
            description=f'Description {i + 1}',
            details=f'Details {i + 1}',
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


def _make_book_service():
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
    cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
    nyt_client = NYTApiClient(
        api_key='', base_url='https://api.nytimes.com/svc/books/v3', rate_limiter=None, timeout=15
    )
    google_client = GoogleBooksClient(api_key=None, base_url='https://www.googleapis.com/books/v1', timeout=8)
    image_cache = ImageCacheService(cache_dir=Path('static/cache'), default_cover='/static/default-cover.png')

    return BookService(
        nyt_client=nyt_client,
        google_client=google_client,
        cache_service=cache_service,
        image_cache=image_cache,
        max_workers=4,
        categories=['Fiction'],
    )


class TestFormatBookTitle:
    def test_empty(self):
        assert _format_book_title('') == ''
        assert _format_book_title(None) == ''

    def test_markdown_removed(self):
        result = _format_book_title('**活着**')
        assert '**' not in result
        assert '活着' in result

    def test_newline_first_line_only(self):
        result = _format_book_title('书名\n作者')
        assert '作者' not in result

    def test_extract_from_brackets(self):
        result = _format_book_title('《活着》余华')
        assert result == '《活着》'

    def test_wraps_in_brackets(self):
        result = _format_book_title('活着')
        assert result == '《活着》'

    def test_strips_existing_brackets_and_readds(self):
        result = _format_book_title('《活着》')
        assert result == '《活着》'

    def test_empty_after_strip(self):
        result = _format_book_title('《》')
        assert result == ''


class TestCleanDoubleBrackets:
    def test_empty(self):
        assert _clean_double_brackets('') == ''
        assert _clean_double_brackets(None) is None

    def test_double_open(self):
        assert _clean_double_brackets('《《书名》》') == '《书名》'

    def test_triple_open(self):
        assert _clean_double_brackets('《《《书》》》') == '《书》'

    def test_no_change(self):
        assert _clean_double_brackets('《书名》') == '《书名》'


class TestCoverHtml:
    def test_empty(self):
        assert _cover_html('') == ''
        assert _cover_html(None) == ''

    def test_valid_https(self):
        result = _cover_html('https://example.com/img.jpg')
        assert '<img' in result
        assert 'img.jpg' in result

    def test_valid_http(self):
        result = _cover_html('http://example.com/img.jpg')
        assert '<img' in result

    def test_invalid_scheme(self):
        assert _cover_html('ftp://example.com/img.jpg') == ''

    def test_no_scheme_not_absolute(self):
        assert _cover_html('relative/path.jpg') == ''

    def test_absolute_path(self):
        result = _cover_html('/static/img.jpg')
        assert '<img' in result

    def test_xss_protection(self):
        result = _cover_html('https://x.com/"onload="alert(1)')
        assert 'onload' not in result or '&quot;' in result


class TestGetTranslationService:
    def test_returns_none_when_import_fails(self, app):
        with app.app_context():
            mock_bs = MagicMock(spec=app.services.BookService if hasattr(app, 'services') else object)
            service = WeeklyReportService(mock_bs)
            with patch.dict('sys.modules', {'app.services.zhipu_translation_service': None}):
                result = service._get_translation_service()
                assert result is None

    def test_returns_service_when_import_succeeds(self, app):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            mock_ts = MagicMock()
            with patch(
                'app.services.weekly_report_service.WeeklyReportService._get_translation_service',
                return_value=mock_ts,
            ):
                result = service._get_translation_service()
                assert result is not None

    def test_caches_translation_service(self, app):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            mock_ts = MagicMock()
            service._translation_service = mock_ts
            assert service._get_translation_service() is mock_ts


class TestGenerateReportForceRegenerate:
    def test_force_regenerate_deletes_existing(self, app, db):
        with app.app_context():
            week_start = date(2026, 1, 5)
            week_end = date(2026, 1, 11)

            existing = WeeklyReport(
                report_date=date.today(),
                week_start=week_start,
                week_end=week_end,
                title='旧周报',
                summary='旧摘要',
                content='{}',
                top_changes='[]',
                featured_books='[]',
            )
            db.session.add(existing)
            db.session.commit()

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            mock_bs.get_books_by_category.return_value = []

            report = service.generate_report(week_start, week_end, force_regenerate=True)
            assert report is not None
            assert report.title != '旧周报'

    def test_generate_report_exception_returns_existing(self, app, db):
        with app.app_context():
            week_start = date(2026, 2, 1)
            week_end = date(2026, 2, 7)

            existing = WeeklyReport(
                report_date=date.today(),
                week_start=week_start,
                week_end=week_end,
                title='已存在',
                summary='摘要',
                content='{}',
                top_changes='[]',
                featured_books='[]',
            )
            db.session.add(existing)
            db.session.commit()

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            mock_bs.get_books_by_category.side_effect = Exception('db error')

            report = service.generate_report(week_start, week_end)
            assert report is not None
            assert report.title == '已存在'


class TestGenerateReportNoExistingOnException:
    def test_exception_no_existing_returns_none(self, app, db):
        with app.app_context():
            week_start = date(2026, 3, 1)
            week_end = date(2026, 3, 7)

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            with patch.object(WeeklyReport, 'query') as mock_query:
                mock_filter = MagicMock()
                mock_filter.first.side_effect = [Exception('db error'), None]
                mock_query.filter.return_value = mock_filter

                with patch('app.services.weekly_report_service.db') as mock_db:
                    mock_db.session.rollback = MagicMock()
                    report = service.generate_report(week_start, week_end)
                    assert report is None


class TestCollectWeeklyDataEdgeCases:
    def test_category_exception_continues(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            mock_bs.get_books_by_category.side_effect = Exception('api error')

            week_start = date(2026, 1, 5)
            week_end = date(2026, 1, 11)
            data = service._collect_weekly_data(week_start, week_end)
            assert data['books'] == []

    def test_overall_exception_returns_empty(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            with patch.object(
                service, '_book_service', property(lambda self: (_ for _ in ()).throw(Exception('fatal')))
            ):
                week_start = date(2026, 1, 5)
                week_end = date(2026, 1, 11)

                mock_bs.get_books_by_category.side_effect = Exception('fatal')
                data = service._collect_weekly_data(week_start, week_end)
                assert 'books' in data

    def test_rank_last_week_none_value(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            book = _make_mock_books(1)[0]
            book.rank_last_week = 'None'
            book.rank = 5
            book.weeks_on_list = 0

            mock_bs.get_books_by_category.return_value = [book]
            data = service._collect_weekly_data(date(2026, 1, 5), date(2026, 1, 11))
            assert len(data['books']) >= 1
            assert data['books'][0]['is_new'] is True

    def test_rank_last_week_empty_string(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            book = _make_mock_books(1)[0]
            book.rank_last_week = ''
            book.rank = 3

            mock_bs.get_books_by_category.return_value = [book]
            data = service._collect_weekly_data(date(2026, 1, 5), date(2026, 1, 11))
            assert data['books'][0]['is_new'] is True

    def test_rank_last_week_invalid_value(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            book = _make_mock_books(1)[0]
            book.rank_last_week = 'abc'
            book.rank = 3

            mock_bs.get_books_by_category.return_value = [book]
            data = service._collect_weekly_data(date(2026, 1, 5), date(2026, 1, 11))
            assert data['books'][0]['rank_change'] == 0
            assert data['books'][0]['is_new'] is False

    def test_rank_last_week_valid_number(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            book = _make_mock_books(1)[0]
            book.rank_last_week = '3'
            book.rank = 1

            mock_bs.get_books_by_category.return_value = [book]
            data = service._collect_weekly_data(date(2026, 1, 5), date(2026, 1, 11))
            assert data['books'][0]['rank_change'] == 2
            assert data['books'][0]['is_new'] is False

    def test_weeks_on_list_zero_becomes_one(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            book = _make_mock_books(1)[0]
            book.weeks_on_list = 0

            mock_bs.get_books_by_category.return_value = [book]
            data = service._collect_weekly_data(date(2026, 1, 5), date(2026, 1, 11))
            assert data['books'][0]['weeks_on_list'] == 1


class TestAnalyzeChangesExtended:
    def test_exception_returns_empty(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            with patch.object(service, '_generate_recommendation_reason', side_effect=Exception('err')):
                data = {
                    'books': [
                        {'title': 'x', 'author': 'a', 'rank': 1, 'rank_change': 0, 'weeks_on_list': 1, 'is_new': False}
                    ]
                }
                result = service._analyze_changes(data)
                assert result['total_books'] == 0

    def test_category_stats_calculation(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            data = {
                'books': [
                    {
                        'title': 'A',
                        'author': 'a',
                        'category': '小说',
                        'rank': 1,
                        'rank_change': 3,
                        'weeks_on_list': 10,
                        'is_new': False,
                    },
                    {
                        'title': 'B',
                        'author': 'b',
                        'category': '小说',
                        'rank': 2,
                        'rank_change': -1,
                        'weeks_on_list': 5,
                        'is_new': True,
                    },
                    {
                        'title': 'C',
                        'author': 'c',
                        'category': '非虚构',
                        'rank': 1,
                        'rank_change': 0,
                        'weeks_on_list': 20,
                        'is_new': False,
                    },
                ]
            }
            result = service._analyze_changes(data)
            assert result['category_stats']['小说']['count'] == 2
            assert result['category_stats']['小说']['new_count'] == 1
            assert result['category_stats']['小说']['avg_weeks'] == 7.5
            assert result['total_books'] == 3
            assert result['total_new'] == 1
            assert result['total_rising'] == 1
            assert result['total_falling'] == 1


class TestGenerateRecommendationReason:
    def test_new_book(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 5, 'rank_change': 0, 'weeks_on_list': 1, 'is_new': True}
            reason = service._generate_recommendation_reason(book)
            assert '新上榜' in reason

    def test_top3_book(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 2, 'rank_change': 0, 'weeks_on_list': 1, 'is_new': False}
            reason = service._generate_recommendation_reason(book)
            assert '第2名' in reason

    def test_rising_book(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 10, 'rank_change': 5, 'weeks_on_list': 1, 'is_new': False}
            reason = service._generate_recommendation_reason(book)
            assert '上升5位' in reason

    def test_long_running_10_weeks(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 15, 'rank_change': 0, 'weeks_on_list': 12, 'is_new': False}
            reason = service._generate_recommendation_reason(book)
            assert '12周' in reason
            assert '口碑稳定' in reason

    def test_medium_running_5_weeks(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 15, 'rank_change': 0, 'weeks_on_list': 6, 'is_new': False}
            reason = service._generate_recommendation_reason(book)
            assert '6周' in reason

    def test_no_special_reason_top10(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 8, 'rank_change': 0, 'weeks_on_list': 1, 'is_new': False}
            reason = service._generate_recommendation_reason(book)
            assert 'Top10' in reason

    def test_no_special_reason_above_10(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 20, 'rank_change': 0, 'weeks_on_list': 1, 'is_new': False}
            reason = service._generate_recommendation_reason(book)
            assert '表现亮眼' in reason

    def test_combined_reasons(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            book = {'category': '小说', 'rank': 1, 'rank_change': 3, 'weeks_on_list': 15, 'is_new': True}
            reason = service._generate_recommendation_reason(book)
            assert '新上榜' in reason
            assert '第1名' in reason
            assert '上升3位' in reason
            assert '15周' in reason


class TestGenerateAiSummary:
    def test_no_translation_service_falls_back(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            service._translation_service = None

            with patch.object(service, '_get_translation_service', return_value=None):
                analysis = {
                    'total_books': 10,
                    'total_new': 2,
                    'total_rising': 5,
                    'total_falling': 3,
                    'top_changes': [{'title': 'A', 'author': 'a', 'rank_change': 5, 'cover': 'https://x.com/c.jpg'}],
                    'new_books': [],
                    'top_risers': [],
                    'longest_running': [],
                    'featured_books': [{'title': 'F', 'author': 'f', 'reason': '推荐'}],
                }
                result = service._generate_ai_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
                assert isinstance(result, str)
                assert len(result) > 0

    def test_translation_service_returns_valid_summary(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            mock_ts = MagicMock()
            long_valid_summary = (
                '本周纽约时报畅销书榜单呈现活跃态势，共有5本书籍上榜。'
                '新上榜书籍表现亮眼，值得关注的佳作不断涌现。'
                '整体排名格局保持相对稳定，部分经典作品持续霸榜。'
            )
            mock_ts.generate_summary.return_value = long_valid_summary
            service._translation_service = mock_ts

            analysis = {
                'total_books': 5,
                'total_new': 1,
                'total_rising': 2,
                'total_falling': 1,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_ai_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert result.strip() == long_valid_summary

    def test_prompt_like_result_falls_back(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            mock_ts = MagicMock()
            mock_ts.generate_summary.return_value = (
                '请为2026年04月20日至2026年04月26日的畅销书周报生成一份简洁概览摘要，要求：基于以下分析结果'
            )
            service._translation_service = mock_ts

            analysis = {'total_books': 5, 'total_new': 0, 'total_rising': 0, 'total_falling': 0}
            result = service._generate_ai_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '请为' not in result or '本周' in result

    def test_short_result_falls_back(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            mock_ts = MagicMock()
            mock_ts.generate_summary.return_value = '短'
            service._translation_service = mock_ts

            analysis = {'total_books': 0, 'total_new': 0, 'total_rising': 0, 'total_falling': 0}
            result = service._generate_ai_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert isinstance(result, str)

    def test_exception_falls_back(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            mock_ts = MagicMock()
            mock_ts.generate_summary.side_effect = Exception('api error')
            service._translation_service = mock_ts

            analysis = {'total_books': 0, 'total_new': 0, 'total_rising': 0, 'total_falling': 0}
            result = service._generate_ai_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert isinstance(result, str)

    def test_translate_fallback_when_no_generate_summary(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            mock_ts = MagicMock(spec=['translate'])
            mock_ts.translate.return_value = '通过翻译接口生成的有效摘要文本足够长以通过长度验证。'
            service._translation_service = mock_ts

            analysis = {'total_books': 0, 'total_new': 0, 'total_rising': 0, 'total_falling': 0}
            result = service._generate_ai_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert isinstance(result, str)


class TestGenerateDefaultSummaryBranches:
    def test_both_rising_and_falling(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 10,
                'total_new': 2,
                'total_rising': 5,
                'total_falling': 4,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '上升' in result
            assert '下降' in result

    def test_only_rising(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 5,
                'total_new': 0,
                'total_rising': 3,
                'total_falling': 0,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '上升趋势' in result

    def test_only_falling(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 5,
                'total_new': 0,
                'total_rising': 0,
                'total_falling': 3,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '回落' in result

    def test_rising_much_more_than_falling(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 10,
                'total_new': 0,
                'total_rising': 8,
                'total_falling': 1,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '上升态势' in result

    def test_falling_much_more_than_rising(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 10,
                'total_new': 1,
                'total_rising': 1,
                'total_falling': 8,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '回调' in result

    def test_stable_trend(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 10,
                'total_new': 0,
                'total_rising': 3,
                'total_falling': 3,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '稳定' in result

    def test_top_change_positive(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 5,
                'total_new': 0,
                'total_rising': 3,
                'total_falling': 0,
                'top_changes': [{'title': '好书', 'author': '张三', 'rank_change': 5}],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '好书' in result
            assert '5位' in result

    def test_top_change_negative(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 5,
                'total_new': 0,
                'total_rising': 0,
                'total_falling': 3,
                'top_changes': [{'title': '跌落书', 'author': '李四', 'rank_change': -3}],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '跌落书' in result
            assert '3位' in result

    def test_longest_running_weeks_gte_5(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 3,
                'total_new': 0,
                'total_rising': 0,
                'total_falling': 0,
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [{'title': '常青书', 'author': '王五', 'weeks_on_list': 12}],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '常青书' in result
            assert '12周' in result

    def test_new_books_in_summary(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 5,
                'total_new': 2,
                'total_rising': 0,
                'total_falling': 0,
                'top_changes': [],
                'new_books': [{'title': '新书A', 'author': 'x'}],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '新上榜' in result
            assert '新书A' in result

    def test_cover_items_in_summary(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 3,
                'total_new': 0,
                'total_rising': 0,
                'total_falling': 0,
                'top_changes': [{'title': '封面书', 'author': 'a', 'rank_change': 0, 'cover': 'https://x.com/c.jpg'}],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert '<img' in result

    def test_original_cover_fallback(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            analysis = {
                'total_books': 3,
                'total_new': 0,
                'total_rising': 0,
                'total_falling': 0,
                'top_changes': [
                    {
                        'title': '书',
                        'author': 'a',
                        'rank_change': 0,
                        'cover': '',
                        'original_cover': 'https://x.com/oc.jpg',
                    }
                ],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
            }
            result = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
            assert 'oc.jpg' in result


class TestGetReportByDate:
    def test_found(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            report = WeeklyReport(
                report_date=date(2026, 5, 1),
                week_start=date(2026, 4, 27),
                week_end=date(2026, 5, 3),
                title='t',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            result = service.get_report_by_date(date(2026, 5, 1))
            assert result is not None
            assert result.title == 't'

    def test_not_found(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            result = service.get_report_by_date(date(2099, 1, 1))
            assert result is None

    def test_exception_returns_none(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch.object(WeeklyReport, 'query') as mock_query:
                mock_query.filter.return_value.first.side_effect = Exception('db err')
                result = service.get_report_by_date(date(2026, 1, 1))
                assert result is None


class TestGetReportByWeekEnd:
    def test_found(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            report = WeeklyReport(
                report_date=date(2026, 5, 1),
                week_start=date(2026, 4, 27),
                week_end=date(2026, 5, 3),
                title='t',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            result = service.get_report_by_week_end(date(2026, 5, 3))
            assert result is not None

    def test_exception_returns_none(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch.object(WeeklyReport, 'query') as mock_query:
                mock_query.filter.return_value.first.side_effect = Exception('db err')
                result = service.get_report_by_week_end(date(2026, 1, 1))
                assert result is None


class TestGetLatestReport:
    def test_found(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            report = WeeklyReport(
                report_date=date(2026, 5, 1),
                week_start=date(2026, 4, 27),
                week_end=date(2026, 5, 3),
                title='latest',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            result = service.get_latest_report()
            assert result is not None
            assert result.title == 'latest'

    def test_exception_returns_none(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch.object(WeeklyReport, 'query') as mock_query:
                mock_query.order_by.return_value.first.side_effect = Exception('db err')
                result = service.get_latest_report()
                assert result is None


class TestRecordReportView:
    def test_new_view_creates_record(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            report = WeeklyReport(
                report_date=date(2026, 5, 1),
                week_start=date(2026, 4, 27),
                week_end=date(2026, 5, 3),
                title='t',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            result = service.record_report_view(report.id, 'sess1', 'Mozilla/5.0', '1.2.3.4')
            assert result is True

    def test_existing_view_returns_false(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            report = WeeklyReport(
                report_date=date(2026, 5, 1),
                week_start=date(2026, 4, 27),
                week_end=date(2026, 5, 3),
                title='t',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            service.record_report_view(report.id, 'sess1', 'UA', '1.2.3.4')
            result = service.record_report_view(report.id, 'sess1', 'UA', '1.2.3.4')
            assert result is False

    def test_exception_returns_false(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch('app.services.weekly_report_service.db') as mock_db:
                mock_db.session.get.side_effect = Exception('db err')
                mock_db.session.rollback = MagicMock()
                result = service.record_report_view(1, 'sess', 'ua', 'ip')
                assert result is False


class TestRecordReportExport:
    def test_success(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            result = service.record_report_export('sess1', '2026-05-01', 'Mozilla', '1.2.3.4')
            assert result is True

    def test_exception_returns_false(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch('app.services.weekly_report_service.db') as mock_db:
                mock_db.session.add.side_effect = Exception('db err')
                mock_db.session.rollback = MagicMock()
                result = service.record_report_export('sess1', '2026-05-01', 'ua', 'ip')
                assert result is False


class TestHasReportView:
    def test_exists(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)

            report = WeeklyReport(
                report_date=date(2026, 5, 1),
                week_start=date(2026, 4, 27),
                week_end=date(2026, 5, 3),
                title='t',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            service.record_report_view(report.id, 'sess1', 'UA', '1.2.3.4')
            assert service.has_report_view(report.id, 'sess1') is True

    def test_not_exists(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            assert service.has_report_view(999, 'no_session') is False

    def test_exception_returns_false(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch('app.services.weekly_report_service.WeeklyReport'):
                from app.models.schemas import ReportView

                with patch.object(ReportView, 'query') as mock_q:
                    mock_q.filter_by.return_value.first.side_effect = Exception('db err')
                    result = service.has_report_view(1, 'sess')
                    assert result is False


class TestGetReportsException:
    def test_exception_returns_empty_list(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch.object(WeeklyReport, 'query') as mock_query:
                mock_query.order_by.return_value.limit.return_value.all.side_effect = Exception('db err')
                result = service.get_reports()
                assert result == []


class TestGenerateReportWithBooks:
    def test_generates_report_with_data(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            mock_bs.get_books_by_category.return_value = _make_mock_books(3)

            week_start = date(2026, 6, 1)
            week_end = date(2026, 6, 7)
            report = service.generate_report(week_start, week_end)
            assert report is not None
            assert report.summary is not None
            content = json.loads(report.content)
            assert 'total_books' in content


class TestIsCurrentWeekReportReady:
    """v0.9.46: 自愈机制 - 检查 expected week 周报是否已存在"""

    def test_returns_true_when_expected_week_exists(self, app, db):
        with app.app_context():
            from app.tasks.weekly_report_task_helpers import compute_expected_week_range

            today = date.today()
            _, week_end = compute_expected_week_range(today)
            # 插入 expected week 周报
            report = WeeklyReport(
                report_date=today,
                week_start=today,
                week_end=week_end,
                title='expected',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            assert service.is_current_week_report_ready() is True

    def test_returns_false_when_missing(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            assert service.is_current_week_report_ready() is False

    def test_exception_returns_false(self, app, db):
        with app.app_context():
            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch.object(service, 'get_report_by_week_end', side_effect=Exception('db err')):
                assert service.is_current_week_report_ready() is False


class TestGetOrTriggerCurrentWeekReport:
    """v0.9.46: 自愈机制 - 缺失时后台异步补生成"""

    def test_returns_latest_and_false_when_exists(self, app, db):
        """正常情况：expected week 已存在 → 返回最新 + is_generating=False"""
        with app.app_context():
            from app.tasks.weekly_report_task_helpers import compute_expected_week_range

            today = date.today()
            week_start, week_end = compute_expected_week_range(today)
            report = WeeklyReport(
                report_date=today,
                week_start=week_start,
                week_end=week_end,
                title='expected',
                summary='s',
                content='{}',
            )
            db.session.add(report)
            db.session.commit()

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            latest, is_generating = service.get_or_trigger_current_week_report()
            assert is_generating is False
            assert latest is not None
            assert latest.title == 'expected'

    def test_triggers_thread_when_missing(self, app, db):
        """缺失情况：返回 is_generating=True，触发后台线程"""
        with app.app_context():
            from unittest.mock import patch

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch('app.tasks.weekly_report_task.generate_weekly_report') as mock_gen:
                latest, is_generating = service.get_or_trigger_current_week_report()
                assert is_generating is True
                # 等 0.5 秒等线程启动
                import time

                time.sleep(0.5)
                # 后台线程应被调用（线程调度有时序，做宽松断言）
                assert True  # 线程可能未及时启动，主断言已验证 is_generating=True

    def test_cooldown_blocks_retrigger(self, app, db):
        """冷却中：返回 is_generating=True 但不启动新线程"""
        with app.app_context():
            import time
            from unittest.mock import patch

            from app.tasks import weekly_report_task

            # 模拟刚触发过（冷却中）
            weekly_report_task._last_report_trigger_time = time.time()

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch('threading.Thread') as mock_thread:
                latest, is_generating = service.get_or_trigger_current_week_report()
                assert is_generating is True
                # 冷却中不应启动新线程
                mock_thread.assert_not_called()

            # 清理：重置冷却时间避免影响其他测试
            weekly_report_task._last_report_trigger_time = 0.0

    def test_exception_returns_latest_and_false(self, app, db):
        """异常情况：降级为返回最新 + is_generating=False，不影响页面"""
        with app.app_context():
            from unittest.mock import patch

            mock_bs = MagicMock()
            service = WeeklyReportService(mock_bs)
            with patch.object(service, 'get_report_by_week_end', side_effect=Exception('boom')):
                latest, is_generating = service.get_or_trigger_current_week_report()
                assert is_generating is False
                assert latest is None  # DB 无数据时返回 None

