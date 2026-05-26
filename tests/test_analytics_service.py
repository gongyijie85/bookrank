"""用户行为分析服务测试"""

from datetime import datetime

import pytest

from app.models.schemas import UserBehavior, WeeklyReport
from app.services.analytics_service import AnalyticsService, get_analytics_service


@pytest.fixture
def analytics_service():
    return AnalyticsService()


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

    def test_with_data(self, app, db, analytics_service, sample_reports):
        with app.app_context():
            result = analytics_service.get_report_view_stats(days=365)
            assert result['total_views'] == 300
            assert result['average_views'] == 150.0
            assert len(result['view_stats']) == 2

    def test_empty_db(self, app, db, analytics_service):
        with app.app_context():
            result = analytics_service.get_report_view_stats()
            assert result['total_views'] == 0
            assert result['average_views'] == 0


class TestGetUserBehaviorStats:
    """测试 get_user_behavior_stats"""

    def test_with_data(self, app, db, analytics_service, sample_behaviors):
        with app.app_context():
            result = analytics_service.get_user_behavior_stats(days=365)
            assert result['total_behaviors'] == 5
            assert len(result['behavior_stats']) >= 1

    def test_empty_db(self, app, db, analytics_service):
        with app.app_context():
            result = analytics_service.get_user_behavior_stats()
            assert result['total_behaviors'] == 0


class TestGetDailyStats:
    """测试 get_daily_stats"""

    def test_with_data(self, app, db, analytics_service, sample_behaviors):
        with app.app_context():
            result = analytics_service.get_daily_stats(days=365)
            assert 'daily_stats' in result

    def test_empty_db(self, app, db, analytics_service):
        with app.app_context():
            result = analytics_service.get_daily_stats()
            assert result['daily_stats'] == []


class TestGetTopReports:
    """测试 get_top_reports"""

    def test_with_data(self, app, db, analytics_service, sample_reports):
        with app.app_context():
            result = analytics_service.get_top_reports(limit=5)
            assert len(result) == 2
            assert result[0]['view_count'] >= result[1]['view_count']

    def test_empty_db(self, app, db, analytics_service):
        with app.app_context():
            result = analytics_service.get_top_reports()
            assert result == []


class TestGetUserSessionStats:
    """测试 get_user_session_stats"""

    def test_with_data(self, app, db, analytics_service, sample_behaviors):
        with app.app_context():
            result = analytics_service.get_user_session_stats(days=365)
            assert result['session_count'] == 2
            assert result['average_behaviors_per_session'] > 0

    def test_empty_db(self, app, db, analytics_service):
        with app.app_context():
            result = analytics_service.get_user_session_stats()
            assert result['session_count'] == 0


class TestGetAnalyticsService:
    """测试单例获取"""

    def test_singleton(self):
        import app.services.analytics_service as mod

        mod._analytics_service = None
        s1 = get_analytics_service()
        s2 = get_analytics_service()
        assert s1 is s2
        mod._analytics_service = None
