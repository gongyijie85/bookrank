"""榜单快照落库测试：快照行的字段完整性 + save_week_snapshot 的幂等写入"""

from datetime import date
from typing import Any

from app.models.book import Book
from app.models.schemas import ListSnapshot
from app.services.list_snapshot_service import save_week_snapshot
from app.services.weekly_report_service import WeeklyReportService

WEEK_START = date(2026, 9, 7)
WEEK_END = date(2026, 9, 13)


def _book(**overrides: Any) -> Book:
    defaults: dict[str, Any] = {
        'id': '9780385550369',
        'title': 'James',
        'author': 'Percival Everett',
        'publisher': 'Doubleday',
        'cover': '/cache/images/abc.jpg',
        'list_name': 'Hardcover Fiction',
        'category_id': 'hardcover-fiction',
        'category_name': '精装小说',
        'rank': 4,
        'weeks_on_list': 12,
        'rank_last_week': '7',
        'published_date': '2026-09-13',
        'description': 'desc',
        'details': 'details',
        'publication_dt': '2024-03-05',
        'page_count': '300',
        'language': 'en',
        'buy_links': [],
        'isbn13': '9780385550369',
        'isbn10': '0385550369',
        'price': '28.00',
        'title_zh': '詹姆斯',
    }
    defaults.update(overrides)
    return Book(**defaults)


def _row(
    book_overrides: dict[str, Any] | None = None,
    *,
    category_id: str = 'hardcover-fiction',
    category_name: str = '精装小说',
    update_frequency: str = 'weekly',
    rank_change: int = 3,
    is_new: bool = False,
    is_returning: bool = True,
) -> dict[str, Any]:
    return WeeklyReportService._build_snapshot_row(
        _book(**(book_overrides or {})),
        category_id=category_id,
        category_name=category_name,
        update_frequency=update_frequency,
        rank_change=rank_change,
        is_new=is_new,
        is_returning=is_returning,
    )


class TestBuildSnapshotRow:
    def test_keeps_fields_the_report_digest_drops(self):
        """周报摘要省略了分类 ID、英文原名、出版社与上周名次，快照必须保留"""
        row = _row()

        assert row['category_id'] == 'hardcover-fiction'
        assert row['book_id'] == '9780385550369'
        assert row['title'] == 'James'
        assert row['title_zh'] == '詹姆斯'
        assert row['publisher'] == 'Doubleday'
        assert row['rank'] == 4
        assert row['rank_last_week'] == '7'
        assert row['rank_change'] == 3
        assert row['weeks_on_list'] == 12
        assert row['is_returning'] is True
        assert row['update_frequency'] == 'weekly'
        assert row['list_published_date'] == '2026-09-13'

    def test_negative_weeks_on_list_is_clamped(self):
        assert _row({'weeks_on_list': -5})['weeks_on_list'] == 0

    def test_original_cover_is_captured_for_history_rendering(self):
        book = _book()
        book._original_cover = 'https://static01.nyt.com/x.jpg'

        row = WeeklyReportService._build_snapshot_row(
            book,
            category_id='hardcover-fiction',
            category_name='精装小说',
            update_frequency='weekly',
            rank_change=0,
            is_new=False,
            is_returning=False,
        )

        assert row['original_cover'] == 'https://static01.nyt.com/x.jpg'


class TestSaveWeekSnapshot:
    def test_writes_rows(self, app, db):
        with app.app_context():
            assert save_week_snapshot([_row()], WEEK_START, WEEK_END) == 1
            saved = ListSnapshot.query.filter_by(week_start=WEEK_START).all()

        assert len(saved) == 1
        assert saved[0].category_id == 'hardcover-fiction'
        assert saved[0].book_id == '9780385550369'
        assert saved[0].week_end == WEEK_END

    def test_rerunning_the_same_week_replaces_instead_of_duplicating(self, app, db):
        with app.app_context():
            save_week_snapshot([_row()], WEEK_START, WEEK_END)
            replacement = _row({'id': '9780000000001', 'title': 'Other', 'isbn13': ''})

            assert save_week_snapshot([replacement], WEEK_START, WEEK_END) == 1
            assert ListSnapshot.query.filter_by(week_start=WEEK_START).count() == 1
            assert ListSnapshot.query.filter_by(week_start=WEEK_START).first().title == 'Other'

    def test_deduplicates_same_category_and_book_within_a_week(self, app, db):
        with app.app_context():
            written = save_week_snapshot([_row(), _row()], WEEK_START, WEEK_END)

            assert written == 1
            assert ListSnapshot.query.filter_by(week_start=WEEK_START).count() == 1

    def test_same_book_in_two_categories_is_two_rows(self, app, db):
        """跨榜的同一作品在不同分类榜各占一行，靠 category_id 区分"""
        paperback = _row(
            {'id': '9780385550370', 'isbn13': '9780385550370'},
            category_id='trade-fiction-paperback',
            category_name='平装小说',
        )
        with app.app_context():
            assert save_week_snapshot([_row(), paperback], WEEK_START, WEEK_END) == 2

    def test_rows_missing_required_fields_are_skipped(self, app, db):
        broken = [
            _row(category_id=''),
            _row({'id': ''}),
            _row({'title': ''}),
        ]
        with app.app_context():
            assert save_week_snapshot(broken, WEEK_START, WEEK_END) == 0
            assert ListSnapshot.query.count() == 0

    def test_empty_input_does_not_wipe_an_existing_week(self, app, db):
        with app.app_context():
            save_week_snapshot([_row()], WEEK_START, WEEK_END)

            assert save_week_snapshot([], WEEK_START, WEEK_END) == 0
            assert ListSnapshot.query.filter_by(week_start=WEEK_START).count() == 1

    def test_only_the_target_week_is_touched(self, app, db):
        with app.app_context():
            previous = _row(category_id='business-books')
            save_week_snapshot([previous], date(2026, 8, 31), date(2026, 9, 6))
            save_week_snapshot([_row()], WEEK_START, WEEK_END)

            assert ListSnapshot.query.filter_by(week_start=date(2026, 8, 31)).count() == 1
            assert ListSnapshot.query.filter_by(week_start=WEEK_START).count() == 1
