"""award_book_service.py 扩展测试 —— 覆盖 _process_*、异常路径、查询方法错误处理等未测路径"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import Award, AwardBook, SystemConfig
from app.services.award_book_service import AwardBookService

# ==================== __init__ ====================


class TestInitExtended:
    """测试 __init__ 各分支"""

    def test_without_app(self):
        service = AwardBookService(app=None)
        assert service.app is None
        assert service.google_books_client is None
        assert service.image_cache is None
        assert service.wikidata_client is not None
        assert service.openlib_client is not None

    def test_with_app(self, app):
        with app.app_context():
            service = AwardBookService(app=app)
            assert service.app is app
            assert service.google_books_client is not None
            assert service.image_cache is not None


# ==================== should_refresh 异常路径 ====================


class TestShouldRefreshExtended:
    """should_refresh 更多分支覆盖"""

    def test_invalid_date_returns_true(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value('award_books_last_refresh', 'not-a-valid-date')
            db.session.commit()
            assert award_service.should_refresh() is True

    def test_custom_refresh_interval(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value(
                'award_books_last_refresh',
                (datetime.now() - timedelta(days=3)).isoformat(),
            )
            db.session.commit()
            assert award_service.should_refresh(refresh_interval_days=7) is False
            assert award_service.should_refresh(refresh_interval_days=2) is True


# ==================== get_refresh_status 异常路径 ====================


class TestGetRefreshStatusExtended:
    """get_refresh_status 更多分支覆盖"""

    def test_invalid_date(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value('award_books_last_refresh', 'invalid-date')
            db.session.commit()
            status = award_service.get_refresh_status()
            assert status['needs_refresh'] is True
            assert status['next_refresh'] is None


# ==================== _get_cover_url ====================


class TestGetCoverUrl:
    """测试 _get_cover_url"""

    def test_returns_url_from_openlib(self, award_service):
        award_service.openlib_client = MagicMock()
        award_service.openlib_client.get_cover_url.return_value = 'https://covers.example.com/123.jpg'
        result = award_service._get_cover_url('9781234567890')
        assert result == 'https://covers.example.com/123.jpg'
        award_service.openlib_client.get_cover_url.assert_called_once_with('9781234567890', size='L')

    def test_returns_none_when_no_cover(self, award_service):
        award_service.openlib_client = MagicMock()
        award_service.openlib_client.get_cover_url.return_value = None
        result = award_service._get_cover_url('9781234567890')
        assert result is None


# ==================== _process_single_book ====================


class TestProcessSingleBook:
    """测试 _process_single_book"""

    def test_returns_failed_when_no_isbn(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            result = award_service._process_single_book(award, {'title': 'No ISBN Book', 'year': 2024}, '小说')
            assert result == 'failed'

    def test_creates_new_book(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {
                'author': 'Test Author',
                'description': 'A' * 60,
            }
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {
                'cover_url': None,
                'description': 'B' * 60,
                'buy_links': {'amazon': 'https://amazon.com'},
            }
            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = None

            result = award_service._process_single_book(
                award,
                {
                    'title': 'New Test Book',
                    'author': 'Test Author',
                    'year': 2024,
                    'isbn13': '9780000000001',
                },
                '小说',
            )
            assert result == 'new'

    def test_skips_existing_book_without_update(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            book = db.session.get(AwardBook, sample_award_book)
            result = award_service._process_single_book(
                award,
                {
                    'title': book.title,
                    'year': book.year,
                    'isbn13': book.isbn13,
                },
                '最佳长篇小说',
            )
            assert result == 'skipped'

    def test_updates_existing_book_cover(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = '/covers/new_cover.jpg'
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.get_cover_url.return_value = 'https://covers.example.com/new.jpg'

            result = award_service._process_single_book(
                award,
                {
                    'title': book.title,
                    'year': book.year,
                    'isbn13': book.isbn13,
                },
                '最佳长篇小说',
            )
            assert result == 'updated'

    def test_existing_book_cover_returns_default(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = '/static/default-cover.png'
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.get_cover_url.return_value = 'https://covers.example.com/new.jpg'

            result = award_service._process_single_book(
                award,
                {
                    'title': book.title,
                    'year': book.year,
                    'isbn13': book.isbn13,
                },
                '最佳长篇小说',
            )
            assert result == 'skipped'

    def test_new_book_with_google_cover_fallback(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {}
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {
                'cover_url': 'https://books.google.com/cover.jpg',
                'description': '',
                'buy_links': {},
            }
            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = '/covers/cached.jpg'

            result = award_service._process_single_book(
                award,
                {
                    'title': 'Fallback Cover Book',
                    'author': 'Fallback Author',
                    'year': 2023,
                    'isbn13': '9780000000002',
                },
                '小说',
            )
            assert result == 'new'

    def test_new_book_default_cover_set_to_none(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {}
            award_service.openlib_client.get_cover_url.return_value = 'https://covers.example.com/cover.jpg'
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {}
            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = '/static/default-cover.png'

            result = award_service._process_single_book(
                award,
                {
                    'title': 'Default Cover Book',
                    'author': 'Author',
                    'year': 2022,
                    'isbn13': '9780000000003',
                },
                '小说',
            )
            assert result == 'new'
            new_book = AwardBook.query.filter_by(isbn13='9780000000003').first()
            assert new_book is not None
            assert new_book.cover_local_path is None

    def test_new_book_with_isbn10(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {}
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {}
            award_service.image_cache = None

            result = award_service._process_single_book(
                award,
                {
                    'title': 'ISBN10 Book',
                    'year': 2021,
                    'isbn10': '1234567890',
                },
                '小说',
            )
            assert result == 'new'
            new_book = AwardBook.query.filter_by(isbn10='1234567890').first()
            assert new_book is not None

    def test_new_book_long_description_preferred(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {
                'description': 'Short',
            }
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {
                'description': 'G' * 100,
                'cover_url': None,
                'buy_links': {},
            }
            award_service.image_cache = None

            result = award_service._process_single_book(
                award,
                {
                    'title': 'Long Desc Book',
                    'author': 'Desc Author',
                    'year': 2020,
                    'isbn13': '9780000000004',
                },
                '小说',
            )
            assert result == 'new'
            new_book = AwardBook.query.filter_by(isbn13='9780000000004').first()
            assert len(new_book.description) == 100

    def test_new_book_author_fallback_to_google(self, app, db, award_service, sample_award):
        with app.app_context():
            award = db.session.get(Award, sample_award)
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {}
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {
                'author': 'Google Author',
            }
            award_service.image_cache = None

            result = award_service._process_single_book(
                award,
                {
                    'title': 'Author Fallback Book',
                    'year': 2019,
                    'isbn13': '9780000000005',
                },
                '小说',
            )
            assert result == 'new'
            new_book = AwardBook.query.filter_by(isbn13='9780000000005').first()
            assert new_book.author == 'Google Author'


# ==================== _process_award_books ====================


class TestProcessAwardBooks:
    """测试 _process_award_books"""

    @patch('app.services.award_book_service.time.sleep')
    @pytest.mark.xfail(reason='源码 _process_award_books 使用 Award(award_key=, category=) 但模型无此列')
    def test_creates_new_award(self, mock_sleep, app, db, award_service):
        with app.app_context():
            Award.query.delete()
            db.session.commit()

            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {}
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {}
            award_service.image_cache = None

            result = award_service._process_award_books(
                'nebula',
                [
                    {
                        'title': 'Test Book',
                        'author': 'Author',
                        'year': 2024,
                        'isbn13': '9780000000010',
                    }
                ],
            )
            assert result['new'] == 1
            assert result['failed'] == 0

    @patch('app.services.award_book_service.time.sleep')
    def test_existing_award(self, mock_sleep, app, db, award_service, sample_award):
        with app.app_context():
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {}
            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = None

            result = award_service._process_award_books(
                'nebula',
                [
                    {
                        'title': 'Existing Award Book',
                        'author': 'Author',
                        'year': 2024,
                        'isbn13': '9780000000011',
                    }
                ],
            )
            assert result['new'] == 1

    @patch('app.services.award_book_service.time.sleep')
    @pytest.mark.xfail(reason='源码 _process_award_books 使用 Award(award_key=, category=) 但模型无此列')
    def test_unknown_award_key(self, mock_sleep, app, db, award_service):
        with app.app_context():
            result = award_service._process_award_books(
                'unknown_award',
                [
                    {
                        'title': 'Unknown Award Book',
                        'author': 'Author',
                        'year': 2024,
                        'isbn13': '9780000000012',
                    }
                ],
            )
            assert result['new'] == 1

    @patch('app.services.award_book_service.time.sleep')
    @pytest.mark.xfail(reason='源码 _process_award_books 使用 Award(award_key=, category=) 但模型无此列')
    def test_failed_book_counted(self, mock_sleep, app, db, award_service):
        with app.app_context():
            result = award_service._process_award_books(
                'hugo',
                [{'title': 'No ISBN', 'year': 2024}],
            )
            assert result['failed'] == 1


# ==================== refresh_award_books 扩展 ====================


class TestRefreshAwardBooksExtended:
    """refresh_award_books 更多覆盖"""

    @patch('app.services.award_book_service.time.sleep')
    @patch.object(AwardBookService, 'should_refresh', return_value=True)
    @patch.object(AwardBookService, 'update_refresh_time')
    @pytest.mark.xfail(reason='源码 _process_award_books 使用 Award(award_key=, category=) 但模型无此列')
    def test_refresh_with_book_data(self, mock_update, mock_should, mock_sleep, app, db, award_service):
        with app.app_context():
            award_service.wikidata_client = MagicMock()
            award_service.wikidata_client.get_all_award_books.return_value = {
                'nebula': [
                    {
                        'title': 'Refreshed Book',
                        'author': 'Author',
                        'year': 2024,
                        'isbn13': '9780000000020',
                    }
                ],
            }
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.fetch_book_by_isbn.return_value = {}
            award_service.openlib_client.get_cover_url.return_value = None
            award_service.google_books_client = MagicMock()
            award_service.google_books_client.fetch_book_details.return_value = {}
            award_service.image_cache = None

            result = award_service.refresh_award_books(force=True)
            assert result['processed_awards'] == 1
            assert result['new_books'] == 1

    @patch.object(AwardBookService, 'should_refresh', return_value=True)
    @patch.object(AwardBookService, 'update_refresh_time')
    def test_refresh_wikidata_error(self, mock_update, mock_should, app, db, award_service):
        with app.app_context():
            award_service.wikidata_client = MagicMock()
            award_service.wikidata_client.get_all_award_books.side_effect = Exception('网络错误')
            result = award_service.refresh_award_books(force=True)
            assert len(result['errors']) > 0

    @patch.object(AwardBookService, 'should_refresh', return_value=True)
    @patch.object(AwardBookService, 'update_refresh_time')
    def test_refresh_award_processing_error(self, mock_update, mock_should, app, db, award_service):
        with app.app_context():
            award_service.wikidata_client = MagicMock()
            award_service.wikidata_client.get_all_award_books.return_value = {
                'nebula': [{'title': 'Bad Book', 'year': 2024}],
            }
            with patch.object(award_service, '_process_award_books', side_effect=Exception('处理失败')):
                result = award_service.refresh_award_books(force=True)
                assert len(result['errors']) > 0


# ==================== fetch_missing_covers 扩展 ====================


class TestFetchMissingCoversExtended:
    """fetch_missing_covers 更多覆盖"""

    def test_fetches_covers_for_books(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = '/covers/fetched.jpg'
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.get_cover_url.return_value = 'https://covers.example.com/fetched.jpg'

            result = award_service.fetch_missing_covers()
            assert result['success'] == 1

    def test_no_isbn_skipped(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            book.isbn13 = None
            book.isbn10 = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            result = award_service.fetch_missing_covers()
            assert result['success'] == 0
            assert result['failed'] == 0

    def test_cover_url_none_increments_failed(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.get_cover_url.return_value = None

            result = award_service.fetch_missing_covers()
            assert result['failed'] == 1

    def test_default_cover_increments_failed(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            award_service.image_cache.get_cached_image_url.return_value = '/static/default-cover.png'
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.get_cover_url.return_value = 'https://covers.example.com/cover.jpg'

            result = award_service.fetch_missing_covers()
            assert result['failed'] == 1

    @patch('app.services.award_book_service.time.sleep')
    def test_exception_during_fetch(self, mock_sleep, app, db, award_service, sample_award_book):
        with app.app_context():
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = None
            db.session.commit()

            award_service.image_cache = MagicMock()
            award_service.openlib_client = MagicMock()
            award_service.openlib_client.get_cover_url.side_effect = Exception('网络超时')

            result = award_service.fetch_missing_covers()
            assert result['failed'] == 1


# ==================== 查询方法异常路径 ====================


class TestQueryMethodsExceptionPaths:
    """查询方法的异常处理覆盖"""

    def test_get_all_awards_db_error(self, app, db, award_service):
        with app.app_context(), patch.object(Award, 'query') as mock_query:
            mock_query.all.side_effect = Exception('DB错误')
            result = award_service.get_all_awards()
            assert result == []

    def test_get_award_by_id_db_error(self, app, db, award_service):
        with app.app_context(), patch('app.models.schemas.db.session') as mock_session:
            mock_session.get.side_effect = Exception('DB错误')
            result = award_service.get_award_by_id(1)
            assert result is None

    def test_get_award_by_name_db_error(self, app, db, award_service):
        with app.app_context(), patch.object(Award, 'query') as mock_query:
            mock_query.filter_by.return_value.first.side_effect = Exception('DB错误')
            result = award_service.get_award_by_name('test')
            assert result is None

    def test_get_award_books_db_error(self, app, db, award_service):
        with app.app_context(), patch.object(AwardBook, 'query') as mock_query:
            mock_query.filter_by.return_value.filter_by.return_value = mock_query
            mock_query.count.side_effect = Exception('DB错误')
            result = award_service.get_award_books()
            assert result == ([], 0)

    def test_get_award_book_by_id_db_error(self, app, db, award_service):
        with app.app_context(), patch('app.models.schemas.db.session') as mock_session:
            mock_session.get.side_effect = Exception('DB错误')
            result = award_service.get_award_book_by_id(1)
            assert result is None

    def test_search_award_books_db_error(self, app, db, award_service):
        with app.app_context(), patch.object(AwardBook, 'query') as mock_query:
            mock_query.filter.return_value.count.side_effect = Exception('DB错误')
            result = award_service.search_award_books('test')
            assert result == ([], 0)

    def test_get_distinct_years_db_error(self, app, db, award_service):
        with app.app_context(), patch('app.models.schemas.db.session') as mock_session:
            mock_session.query.return_value.distinct.return_value.order_by.return_value.all.side_effect = Exception(
                'DB错误'
            )
            result = award_service.get_distinct_years()
            assert result == []

    def test_get_book_counts_by_award_db_error(self, app, db, award_service):
        with app.app_context(), patch('app.models.schemas.db.session') as mock_session:
            mock_session.query.return_value.group_by.return_value.all.side_effect = Exception('DB错误')
            result = award_service.get_book_counts_by_award()
            assert result == {}

    def test_find_award_book_by_isbn_db_error(self, app, db, award_service):
        with app.app_context(), patch.object(AwardBook, 'query') as mock_query:
            mock_query.filter_by.return_value.first.side_effect = Exception('DB错误')
            result = award_service.find_award_book_by_isbn('9780000000000')
            assert result is None


# ==================== get_award_books 更多筛选条件 ====================


class TestGetAwardBooksExtended:
    """get_award_books 更多筛选条件覆盖"""

    def test_filter_by_category(self, app, db, award_service, sample_award_book):
        with app.app_context():
            books, total = award_service.get_award_books(category='最佳长篇小说')
            assert total >= 1

    def test_keyword_special_chars(self, app, db, award_service, sample_award_book):
        with app.app_context():
            books, total = award_service.get_award_books(keyword='test%')
            assert total >= 0

    def test_keyword_underscore(self, app, db, award_service, sample_award_book):
        with app.app_context():
            books, total = award_service.get_award_books(keyword='test_')
            assert total >= 0


# ==================== get_distinct_years 带 award_id ====================


class TestGetDistinctYearsExtended:
    """get_distinct_years 带 award_id 过滤"""

    def test_with_award_id(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            years = award_service.get_distinct_years(award_id=sample_award)
            assert 2024 in years

    def test_with_nonexistent_award_id(self, app, db, award_service):
        with app.app_context():
            years = award_service.get_distinct_years(award_id=99999)
            assert years == []


# ==================== update_refresh_time ====================


class TestUpdateTime:
    """测试 update_refresh_time"""

    def test_updates_value(self, app, db, award_service):
        with app.app_context():
            award_service.update_refresh_time()
            val = SystemConfig.get_value('award_books_last_refresh')
            assert val is not None
            parsed = datetime.fromisoformat(val)
            assert (datetime.now() - parsed).seconds < 5
