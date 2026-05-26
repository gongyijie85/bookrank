"""获奖图书服务测试"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import Award, AwardBook, SystemConfig
from app.services.award_book_service import AwardBookService


@pytest.fixture
def award_service(app):
    return AwardBookService(app=app)


@pytest.fixture
def sample_award(app, db):
    with app.app_context():
        award = Award(name='星云奖', description='星云奖获奖图书', country='美国')
        db.session.add(award)
        db.session.commit()
        return award.id


@pytest.fixture
def sample_award_book(app, db, sample_award):
    with app.app_context():
        book = AwardBook(
            award_id=sample_award,
            year=2024,
            category='最佳长篇小说',
            rank=1,
            title='Network Effect',
            author='Martha Wells',
            isbn13='9781250313195',
            is_displayable=True,
        )
        db.session.add(book)
        db.session.commit()
        return book.id


class TestShouldRefresh:
    """测试 should_refresh"""

    def test_force_refresh(self, award_service):
        assert award_service.should_refresh(force=True) is True

    def test_no_last_refresh(self, app, db, award_service):
        with app.app_context():
            SystemConfig.query.filter_by(key='award_books_last_refresh').delete()
            db.session.commit()
            assert award_service.should_refresh() is True

    def test_recent_refresh(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value('award_books_last_refresh', datetime.now().isoformat())
            db.session.commit()
            assert award_service.should_refresh() is False

    def test_old_refresh(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value('award_books_last_refresh', (datetime.now() - timedelta(days=10)).isoformat())
            db.session.commit()
            assert award_service.should_refresh() is True


class TestGetRefreshStatus:
    """测试 get_refresh_status"""

    def test_no_last_refresh(self, app, db, award_service):
        with app.app_context():
            SystemConfig.query.filter_by(key='award_books_last_refresh').delete()
            db.session.commit()
            status = award_service.get_refresh_status()
            assert status['needs_refresh'] is True
            assert status['last_refresh'] is None

    def test_with_last_refresh(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value('award_books_last_refresh', datetime.now().isoformat())
            db.session.commit()
            status = award_service.get_refresh_status()
            assert status['last_refresh'] is not None
            assert status['days_since_last'] is not None


class TestGetAllAwards:
    """测试 get_all_awards"""

    def test_with_data(self, app, db, award_service, sample_award):
        with app.app_context():
            awards = award_service.get_all_awards()
            assert len(awards) >= 1

    def test_empty_db(self, app, db, award_service):
        with app.app_context():
            Award.query.delete()
            db.session.commit()
            awards = award_service.get_all_awards()
            assert awards == []


class TestGetAwardById:
    """测试 get_award_by_id"""

    def test_existing(self, app, db, award_service, sample_award):
        with app.app_context():
            award = award_service.get_award_by_id(sample_award)
            assert award is not None
            assert award.name == '星云奖'

    def test_nonexistent(self, app, db, award_service):
        with app.app_context():
            award = award_service.get_award_by_id(99999)
            assert award is None


class TestGetAwardByName:
    """测试 get_award_by_name"""

    def test_existing(self, app, db, award_service, sample_award):
        with app.app_context():
            award = award_service.get_award_by_name('星云奖')
            assert award is not None

    def test_nonexistent(self, app, db, award_service):
        with app.app_context():
            award = award_service.get_award_by_name('不存在的奖')
            assert award is None


class TestGetAwardBooks:
    """测试 get_award_books"""

    def test_with_data(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.get_award_books()
            assert total >= 1

    def test_filter_by_award(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            _books, total = award_service.get_award_books(award_id=sample_award)
            assert total >= 1

    def test_filter_by_year(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.get_award_books(year=2024)
            assert total >= 1

    def test_displayable_only(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.get_award_books(include_displayable_only=True)
            assert total >= 1

    def test_keyword_search(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.get_award_books(keyword='Martha')
            assert total >= 1

    def test_pagination(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.get_award_books(page=1, limit=5)
            assert total >= 1


class TestGetAwardBookById:
    """测试 get_award_book_by_id"""

    def test_existing(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = award_service.get_award_book_by_id(sample_award_book)
            assert book is not None

    def test_nonexistent(self, app, db, award_service):
        with app.app_context():
            book = award_service.get_award_book_by_id(99999)
            assert book is None


class TestSearchAwardBooks:
    """测试 search_award_books"""

    def test_search_by_title(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.search_award_books('Network')
            assert total >= 1

    def test_search_no_results(self, app, db, award_service, sample_award_book):
        with app.app_context():
            _books, total = award_service.search_award_books('ZZZZNONEXISTENT')
            assert total == 0


class TestGetDistinctYears:
    """测试 get_distinct_years"""

    def test_with_data(self, app, db, award_service, sample_award_book):
        with app.app_context():
            years = award_service.get_distinct_years()
            assert 2024 in years

    def test_empty_db(self, app, db, award_service):
        with app.app_context():
            AwardBook.query.delete()
            db.session.commit()
            years = award_service.get_distinct_years()
            assert years == []


class TestGetBookCountsByAward:
    """测试 get_book_counts_by_award"""

    def test_with_data(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            counts = award_service.get_book_counts_by_award()
            assert sample_award in counts

    def test_displayable_only(self, app, db, award_service, sample_award, sample_award_book):
        with app.app_context():
            counts = award_service.get_book_counts_by_award(displayable_only=True)
            assert sample_award in counts


class TestFindAwardBookByISBN:
    """测试 find_award_book_by_isbn"""

    def test_existing(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = award_service.find_award_book_by_isbn('9781250313195')
            assert book is not None

    def test_nonexistent(self, app, db, award_service):
        with app.app_context():
            book = award_service.find_award_book_by_isbn('9780000000000')
            assert book is None


class TestRefreshAwardBooks:
    """测试 refresh_award_books"""

    def test_skipped_when_not_needed(self, app, db, award_service):
        with app.app_context():
            SystemConfig.set_value('award_books_last_refresh', datetime.now().isoformat())
            db.session.commit()
            result = award_service.refresh_award_books(force=False)
            assert result['status'] == 'skipped'

    @patch.object(AwardBookService, 'should_refresh', return_value=True)
    @patch.object(AwardBookService, 'update_refresh_time')
    def test_refresh_with_wikidata(self, mock_update, mock_should, app, db, award_service):
        with app.app_context():
            award_service.wikidata_client = MagicMock()
            award_service.wikidata_client.get_all_award_books.return_value = {}
            result = award_service.refresh_award_books(force=True)
            assert result['total_awards'] > 0


class TestFetchMissingCovers:
    """测试 fetch_missing_covers"""

    def test_no_image_cache(self, app, award_service):
        award_service.image_cache = None
        with app.app_context():
            result = award_service.fetch_missing_covers()
            assert result['success'] == 0

    def test_no_missing_covers(self, app, db, award_service, sample_award_book):
        with app.app_context():
            book = db.session.get(AwardBook, sample_award_book)
            book.cover_local_path = '/covers/test.jpg'
            db.session.commit()
            result = award_service.fetch_missing_covers()
            assert result['success'] == 0
