"""用户行为分析服务测试"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app.models.schemas import UserBehavior, WeeklyReport
from app.services.analytics_service import (
    get_daily_stats,
    get_report_view_stats,
    get_top_reports,
    get_user_behavior_stats,
    get_user_session_stats,
)


@pytest.fixture
def sample_reports(app, db):
    with app.app_context():
        reports = [
            WeeklyReport(
                title='Week 1 Report',
                report_date=datetime(2024, 1, 7).date(),
                week_start=datetime(2024, 1, 1).date(),
                week_end=datetime(2024, 1, 7).date(),
                summary='Summary 1',
                view_count=100,
            ),
            WeeklyReport(
                title='Week 2 Report',
                report_date=datetime(2024, 1, 14).date(),
                week_start=datetime(2024, 1, 8).date(),
                week_end=datetime(2024, 1, 14).date(),
                summary='Summary 2',
                view_count=200,
            ),
        ]
        for r in reports:
            db.session.add(r)
        db.session.commit()
        return [r.id for r in reports]


@pytest.fixture
def sample_behaviors(app, db):
    with app.app_context():
        behaviors = [
            UserBehavior(session_id='s1', event_type='view_book', target_id='9780000000001', target_type='book'),
            UserBehavior(session_id='s1', event_type='view_book', target_id='9780000000002', target_type='book'),
            UserBehavior(session_id='s2', event_type='search', target_id='', target_type=''),
            UserBehavior(session_id='s2', event_type='view_book', target_id='9780000000003', target_type='book'),
            UserBehavior(session_id='s2', event_type='view_book', target_id='9780000000004', target_type='book'),
        ]
        for b in behaviors:
            db.session.add(b)
        db.session.commit()


class TestGetReportViewStats:
    """测试 get_report_view_stats"""

    def test_with_data(self, app, db, sample_reports):
        with app.app_context():
            result = get_report_view_stats(days=365)
            assert result['total_views'] == 300
            assert result['average_views'] == 150.0
            assert len(result['view_stats']) == 2

    def test_empty_db(self, app, db):
        with app.app_context():
            result = get_report_view_stats()
            assert result['total_views'] == 0
            assert result['average_views'] == 0


class TestGetUserBehaviorStats:
    """测试 get_user_behavior_stats"""

    def test_with_data(self, app, db, sample_behaviors):
        with app.app_context():
            result = get_user_behavior_stats(days=365)
            assert result['total_behaviors'] == 5
            assert len(result['behavior_stats']) >= 1

    def test_empty_db(self, app, db):
        with app.app_context():
            result = get_user_behavior_stats()
            assert result['total_behaviors'] == 0


class TestGetDailyStats:
    """测试 get_daily_stats"""

    def test_with_data(self, app, db, sample_behaviors):
        with app.app_context():
            result = get_daily_stats(days=365)
            assert 'daily_stats' in result

    def test_empty_db(self, app, db):
        with app.app_context():
            today = datetime.now(UTC).date()
            result = get_daily_stats()
            expected = [{'date': (today - timedelta(days=i)).isoformat(), 'count': 0} for i in range(29, -1, -1)]
            assert result['daily_stats'] == expected
            assert 'error' not in result

    @pytest.mark.parametrize('empty', [True, False])
    def test_fixed_utc_axis(self, app, db, monkeypatch, empty):
        class Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 9, 30, 0, 5, tzinfo=UTC)

        monkeypatch.setattr('app.services.analytics_service.datetime', Fixed)
        with app.app_context():
            if not empty:
                stamps = (
                    datetime(2026, 9, 27, 23, 59, tzinfo=UTC),
                    datetime(2026, 9, 28, tzinfo=UTC),
                    datetime(2026, 9, 30, 23, 59, tzinfo=UTC),
                    datetime(2026, 10, 1, tzinfo=UTC),
                )
                for n, ts in enumerate(stamps):
                    db.session.add(
                        UserBehavior(session_id=f'w{n}', event_type='view', target_id='', target_type='', created_at=ts)
                    )
                db.session.commit()
            result = get_daily_stats(days=3)
        counts = (0, 0, 0) if empty else (1, 0, 1)
        assert result['daily_stats'] == [
            {'date': f'2026-09-{day:02d}', 'count': count} for day, count in zip((28, 29, 30), counts, strict=True)
        ]
        assert 'error' not in result

    def test_sql_error_keeps_marker_without_zerofill(self, app, db):
        def fail(conn, cursor, statement, parameters, context, executemany):
            sql = str(statement).lower()
            if 'select' in sql and ('user_behavior' in sql or 'weekly_report' in sql):
                raise SQLAlchemyError('boom')

        event.listen(db.engine, 'before_cursor_execute', fail)
        try:
            with app.app_context():
                result = get_daily_stats(days=3)
        finally:
            event.remove(db.engine, 'before_cursor_execute', fail)
            db.session.rollback()
        assert result.get('error')
        assert result['daily_stats'] == []


class TestGetTopReports:
    """测试 get_top_reports"""

    def test_with_data(self, app, db, sample_reports):
        with app.app_context():
            result = get_top_reports(limit=5)
            assert len(result) == 2
            assert result[0]['view_count'] >= result[1]['view_count']

    def test_empty_db(self, app, db):
        with app.app_context():
            result = get_top_reports()
            assert result == []


class TestGetUserSessionStats:
    """测试 get_user_session_stats"""

    def test_with_data(self, app, db, sample_behaviors):
        with app.app_context():
            result = get_user_session_stats(days=365)
            assert result['session_count'] == 2
            assert result['average_behaviors_per_session'] > 0

    def test_empty_db(self, app, db):
        with app.app_context():
            result = get_user_session_stats()
            assert result['session_count'] == 0
