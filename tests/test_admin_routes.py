"""admin.py 原始路由测试（非 Stage 4 部分）

覆盖以下路由处理器:
- POST /api/admin/award-covers/sync
- GET  /api/admin/award-covers/status
- POST /api/admin/weekly-report/regenerate
- POST /api/admin/weekly-report/regenerate-all
- GET|POST /api/admin/categories/cleanup
- GET|POST /api/admin/reports/clean-brackets
- GET|POST /api/admin/reports/fix-truncated-titles
- GET|POST /api/admin/translations/cleanup
- GET  /api/admin/errors
- POST /api/admin/errors/clear
"""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

# ==================== 奖项封面同步 ====================


class TestSyncAwardCovers:
    """POST /api/admin/award-covers/sync"""

    def test_sync_success(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.sync_missing_covers.return_value = {'updated': 3, 'skipped': 2}

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=MagicMock()),
            patch('app.routes.admin.get_image_cache_service', return_value=MagicMock()),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
        ):
            response = client.post(
                '/api/admin/award-covers/sync',
                data=json.dumps({'batch_size': 5}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True
            assert '3' in data['message']

    def test_sync_default_batch_size(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.sync_missing_covers.return_value = {'updated': 0}

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=MagicMock()),
            patch('app.routes.admin.get_image_cache_service', return_value=MagicMock()),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
        ):
            response = client.post(
                '/api/admin/award-covers/sync',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True
            call_kwargs = mock_sync_service.sync_missing_covers.call_args
            assert call_kwargs.kwargs['batch_size'] == 10

    def test_sync_batch_size_clamped(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.sync_missing_covers.return_value = {'updated': 0}

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=MagicMock()),
            patch('app.routes.admin.get_image_cache_service', return_value=MagicMock()),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
        ):
            client.post(
                '/api/admin/award-covers/sync',
                data=json.dumps({'batch_size': 100}),
                content_type='application/json',
                headers=admin_headers,
            )
            call_kwargs = mock_sync_service.sync_missing_covers.call_args
            assert call_kwargs.kwargs['batch_size'] == 50

    def test_sync_batch_size_minimum(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.sync_missing_covers.return_value = {'updated': 0}

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=MagicMock()),
            patch('app.routes.admin.get_image_cache_service', return_value=MagicMock()),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
        ):
            client.post(
                '/api/admin/award-covers/sync',
                data=json.dumps({'batch_size': 0}),
                content_type='application/json',
                headers=admin_headers,
            )
            call_kwargs = mock_sync_service.sync_missing_covers.call_args
            assert call_kwargs.kwargs['batch_size'] == 1

    def test_sync_creates_client_when_none(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.sync_missing_covers.return_value = {'updated': 1}

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=None),
            patch('app.routes.admin.get_image_cache_service', return_value=MagicMock()),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
            patch(
                'app.services.google_books_client.GoogleBooksClient',
                return_value=MagicMock(),
            ),
        ):
            response = client.post(
                '/api/admin/award-covers/sync',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True

    def test_sync_exception(self, client, admin_headers):
        with (
            patch('app.utils.service_helpers.get_google_books_client', return_value=None),
            patch('app.services.google_books_client.GoogleBooksClient', side_effect=RuntimeError('连接失败')),
            patch('app.routes.admin.log_error'),
        ):
            response = client.post(
                '/api/admin/award-covers/sync',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is False

    def test_sync_without_auth(self, client):
        response = client.post(
            '/api/admin/award-covers/sync',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (401, 403)


class TestGetAwardCoversStatus:
    """GET /api/admin/award-covers/status"""

    def test_get_status_success(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.get_sync_status.return_value = {
            'total_award_books': 200,
            'with_cover': 180,
            'without_cover': 20,
        }

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=MagicMock()),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
        ):
            response = client.get('/api/admin/award-covers/status', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['total_award_books'] == 200

    def test_get_status_no_google_client(self, client, admin_headers):
        mock_sync_service = MagicMock()
        mock_sync_service.get_sync_status.return_value = {'total_award_books': 0}

        with (
            patch('app.utils.service_helpers.get_or_create_google_books_client', return_value=None),
            patch(
                'app.services.award_cover_sync_service.AwardCoverSyncService',
                return_value=mock_sync_service,
            ),
            patch(
                'app.services.google_books_client.GoogleBooksClient',
                return_value=MagicMock(),
            ),
        ):
            response = client.get('/api/admin/award-covers/status', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is True

    def test_get_status_exception(self, client, admin_headers):
        with (
            patch('app.utils.service_helpers.get_google_books_client', return_value=None),
            patch('app.services.google_books_client.GoogleBooksClient', side_effect=RuntimeError('错误')),
            patch('app.routes.admin.log_error'),
        ):
            response = client.get('/api/admin/award-covers/status', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is False

    def test_get_status_without_auth(self, client):
        response = client.get('/api/admin/award-covers/status')
        assert response.status_code in (401, 403)


# ==================== 周报重新生成 ====================


class TestRegenerateWeeklyReport:
    """POST /api/admin/weekly-report/regenerate"""

    def test_regenerate_success(self, client, admin_headers, app):
        mock_report = MagicMock()
        mock_report.id = 1
        mock_report.title = '测试周报'

        mock_weekly_service = MagicMock()
        mock_weekly_service.generate_report.return_value = mock_report

        mock_book_service = MagicMock()
        app.extensions['book_service'] = mock_book_service

        with patch(
            'app.services.weekly_report_service.WeeklyReportService',
            return_value=mock_weekly_service,
        ):
            response = client.post(
                '/api/admin/weekly-report/regenerate',
                data=json.dumps({'report_date': '2025-05-20'}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['report_id'] == 1
            mock_weekly_service.generate_report.assert_called_once()

    def test_regenerate_missing_date(self, client, admin_headers):
        response = client.post(
            '/api/admin/weekly-report/regenerate',
            data=json.dumps({}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'report_date' in data['message']

    def test_regenerate_invalid_date_format(self, client, admin_headers):
        response = client.post(
            '/api/admin/weekly-report/regenerate',
            data=json.dumps({'report_date': 'not-a-date'}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert '格式' in data['message'] or '日期' in data['message']

    def test_regenerate_future_date(self, client, admin_headers):
        future = (date.today() + timedelta(days=10)).isoformat()
        response = client.post(
            '/api/admin/weekly-report/regenerate',
            data=json.dumps({'report_date': future}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert '未来' in data['message']

    def test_regenerate_no_book_service(self, client, admin_headers, app):
        app.extensions['book_service'] = None

        response = client.post(
            '/api/admin/weekly-report/regenerate',
            data=json.dumps({'report_date': '2025-05-20'}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert response.status_code == 503

    def test_regenerate_report_generation_failed(self, client, admin_headers, app):
        mock_weekly_service = MagicMock()
        mock_weekly_service.generate_report.return_value = None

        mock_book_service = MagicMock()
        app.extensions['book_service'] = mock_book_service

        with patch(
            'app.services.weekly_report_service.WeeklyReportService',
            return_value=mock_weekly_service,
        ):
            response = client.post(
                '/api/admin/weekly-report/regenerate',
                data=json.dumps({'report_date': '2025-05-20'}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is False
            assert response.status_code == 500

    def test_regenerate_exception(self, client, admin_headers, app):
        app.extensions['book_service'] = MagicMock()

        with (
            patch(
                'app.services.weekly_report_service.WeeklyReportService',
                side_effect=RuntimeError('内部错误'),
            ),
            patch('app.routes.admin.log_error'),
        ):
            response = client.post(
                '/api/admin/weekly-report/regenerate',
                data=json.dumps({'report_date': '2025-05-20'}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is False

    def test_regenerate_without_auth(self, client):
        response = client.post(
            '/api/admin/weekly-report/regenerate',
            data=json.dumps({'report_date': '2025-05-20'}),
            content_type='application/json',
        )
        assert response.status_code in (401, 403)


class TestRegenerateAllWeeklyReports:
    """POST /api/admin/weekly-report/regenerate-all"""

    def test_no_problematic_reports(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='正常周报',
            summary='这是一份正常的周报摘要',
        )
        db.session.add(report)
        db.session.commit()

        response = client.post(
            '/api/admin/weekly-report/regenerate-all',
            data=json.dumps({}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['regenerated'] == 0

    def test_with_problematic_reports(self, client, admin_headers, db, app):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='问题周报',
            summary='请为这本书写一段分析结果',
        )
        db.session.add(report)
        db.session.commit()

        mock_report = MagicMock()
        mock_report.id = 2

        mock_weekly_service = MagicMock()
        mock_weekly_service.generate_report.return_value = mock_report

        mock_book_service = MagicMock()
        app.extensions['book_service'] = mock_book_service

        with patch(
            'app.services.weekly_report_service.WeeklyReportService',
            return_value=mock_weekly_service,
        ):
            response = client.post(
                '/api/admin/weekly-report/regenerate-all',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['regenerated'] >= 1

    def test_problematic_report_generation_fails(self, client, admin_headers, db, app):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='问题周报',
            summary='基于以下分析结果生成',
        )
        db.session.add(report)
        db.session.commit()

        mock_weekly_service = MagicMock()
        mock_weekly_service.generate_report.return_value = None

        mock_book_service = MagicMock()
        app.extensions['book_service'] = mock_book_service

        with patch(
            'app.services.weekly_report_service.WeeklyReportService',
            return_value=mock_weekly_service,
        ):
            response = client.post(
                '/api/admin/weekly-report/regenerate-all',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['regenerated'] == 0

    def test_no_book_service(self, client, admin_headers, db, app):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='问题周报',
            summary='请为这本书写分析',
        )
        db.session.add(report)
        db.session.commit()

        app.extensions['book_service'] = None

        response = client.post(
            '/api/admin/weekly-report/regenerate-all',
            data=json.dumps({}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert response.status_code == 503

    def test_regenerate_all_empty_db(self, client, admin_headers, db):
        response = client.post(
            '/api/admin/weekly-report/regenerate-all',
            data=json.dumps({}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['regenerated'] == 0

    def test_regenerate_all_without_auth(self, client):
        response = client.post(
            '/api/admin/weekly-report/regenerate-all',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (401, 403)


# ==================== 分类清理 ====================


class TestCleanupCategories:
    """GET|POST /api/admin/categories/cleanup"""

    def test_dry_run_get(self, client, admin_headers, db):
        from app.models.new_book import NewBook, Publisher

        pub = Publisher(name='测试社', name_en='Test Pub', crawler_class='TestCrawler')
        db.session.add(pub)
        db.session.flush()

        book = NewBook(
            publisher_id=pub.id,
            title='测试书',
            author='作者',
            category='小说**营销文案**',
        )
        db.session.add(book)
        db.session.commit()

        with patch(
            'app.services.new_book_service.NewBookService._sanitize_category',
            return_value='小说',
            create=True,
        ):
            response = client.get('/api/admin/categories/cleanup', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['invalid_found'] >= 1

    def test_dry_run_post(self, client, admin_headers, db):
        from app.models.new_book import NewBook, Publisher

        pub = Publisher(name='测试社', name_en='Test Pub', crawler_class='TestCrawler')
        db.session.add(pub)
        db.session.flush()

        book = NewBook(
            publisher_id=pub.id,
            title='测试书',
            author='作者',
            category='干净分类',
        )
        db.session.add(book)
        db.session.commit()

        with patch(
            'app.services.new_book_service.NewBookService._sanitize_category',
            return_value='干净分类',
            create=True,
        ):
            response = client.post(
                '/api/admin/categories/cleanup',
                data=json.dumps({'dry_run': True}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True

    def test_execute_cleanup(self, client, admin_headers, db):
        from app.models.new_book import NewBook, Publisher

        pub = Publisher(name='测试社', name_en='Test Pub', crawler_class='TestCrawler')
        db.session.add(pub)
        db.session.flush()

        book = NewBook(
            publisher_id=pub.id,
            title='测试书',
            author='作者',
            category='**营销**',
        )
        db.session.add(book)
        db.session.commit()

        with patch(
            'app.services.new_book_service.NewBookService._sanitize_category',
            return_value='营销',
            create=True,
        ):
            response = client.post(
                '/api/admin/categories/cleanup',
                data=json.dumps({'dry_run': False}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True

    def test_no_invalid_categories(self, client, admin_headers, db):
        from app.models.new_book import NewBook, Publisher

        pub = Publisher(name='测试社', name_en='Test Pub', crawler_class='TestCrawler')
        db.session.add(pub)
        db.session.flush()

        book = NewBook(
            publisher_id=pub.id,
            title='测试书',
            author='作者',
            category='小说',
        )
        db.session.add(book)
        db.session.commit()

        with patch(
            'app.services.new_book_service.NewBookService._sanitize_category',
            return_value='小说',
            create=True,
        ):
            response = client.get('/api/admin/categories/cleanup', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['invalid_found'] == 0

    def test_cleanup_without_auth(self, client):
        response = client.get('/api/admin/categories/cleanup')
        assert response.status_code in (401, 403)

    def test_cleanup_empty_database(self, client, admin_headers, db):
        response = client.get('/api/admin/categories/cleanup', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['invalid_found'] == 0


# ==================== 周报书名号清理 ====================


class TestCleanReportBrackets:
    """GET|POST /api/admin/reports/clean-brackets"""

    def test_dry_run_get(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='这是《《重复书名号》》的摘要',
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/clean-brackets', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['fixable'] >= 1

    def test_dry_run_post(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='正常的摘要',
        )
        db.session.add(report)
        db.session.commit()

        response = client.post(
            '/api/admin/reports/clean-brackets',
            data=json.dumps({'dry_run': True}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True

    def test_execute_cleanup(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='这是《《重复书名号》》的摘要',
        )
        db.session.add(report)
        db.session.commit()

        response = client.post(
            '/api/admin/reports/clean-brackets',
            data=json.dumps({'dry_run': False}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['updated'] >= 1

    def test_content_json_fix(self, client, admin_headers, db):
        import json as json_lib

        from app.models.schemas import WeeklyReport

        content = {
            'top_changes': [{'title': '**《测试书》**', 'author': '作者'}],
            'new_books': [],
            'top_risers': [],
            'longest_running': [],
            'featured_books': [],
        }
        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='正常摘要',
            content=json_lib.dumps(content, ensure_ascii=False),
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/clean-brackets', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['fixable'] >= 1

    def test_no_fixable_reports(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='完全正常的摘要内容',
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/clean-brackets', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['fixable'] == 0

    def test_invalid_json_content(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='正常摘要',
            content='不是JSON',
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/clean-brackets', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True

    def test_clean_brackets_without_auth(self, client):
        response = client.get('/api/admin/reports/clean-brackets')
        assert response.status_code in (401, 403)

    def test_clean_brackets_exception(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        mock_q = MagicMock()
        mock_q.all.side_effect = RuntimeError('DB错误')

        with (
            patch.object(WeeklyReport, 'query', new=mock_q),
            patch('app.routes.admin.log_error'),
        ):
            response = client.get('/api/admin/reports/clean-brackets', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is False


# ==================== 截断书名修复 ====================


class TestFixTruncatedTitles:
    """GET|POST /api/admin/reports/fix-truncated-titles"""

    def test_dry_run_get(self, client, admin_headers, db):
        from app.models.schemas import BookMetadata, WeeklyReport

        bm = BookMetadata(
            isbn='9781234567890',
            title='Original Title',
            author='Author',
            title_zh='完整的中文书名',
        )
        db.session.add(bm)

        content = {
            'top_changes': [{'title': '《》', 'isbn': '9781234567890'}],
            'new_books': [],
            'top_risers': [],
            'longest_running': [],
            'featured_books': [],
        }
        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='摘要',
            content=json.dumps(content, ensure_ascii=False),
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/fix-truncated-titles', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['dry_run'] is True

    def test_execute_fix(self, client, admin_headers, db):
        from app.models.schemas import BookMetadata, WeeklyReport

        bm = BookMetadata(
            isbn='9781234567890',
            title='Original Title',
            author='Author',
            title_zh='完整的中文书名',
        )
        db.session.add(bm)

        content = {
            'top_changes': [{'title': '《》', 'isbn': '9781234567890'}],
            'new_books': [],
            'top_risers': [],
            'longest_running': [],
            'featured_books': [],
        }
        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='摘要',
            content=json.dumps(content, ensure_ascii=False),
        )
        db.session.add(report)
        db.session.commit()

        response = client.post(
            '/api/admin/reports/fix-truncated-titles',
            data=json.dumps({'dry_run': False}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['fixed'] >= 1

    def test_no_truncated_titles(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        content = {
            'top_changes': [{'title': '《正常书名》'}],
            'new_books': [],
            'top_risers': [],
            'longest_running': [],
            'featured_books': [],
        }
        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='摘要',
            content=json.dumps(content, ensure_ascii=False),
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/fix-truncated-titles', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['fixed'] == 0

    def test_report_without_content(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='摘要',
            content=None,
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/fix-truncated-titles', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['fixed'] == 0

    def test_invalid_json_content(self, client, admin_headers, db):
        from app.models.schemas import WeeklyReport

        report = WeeklyReport(
            report_date=date(2025, 5, 19),
            week_start=date(2025, 5, 12),
            week_end=date(2025, 5, 18),
            title='测试周报',
            summary='摘要',
            content='not-json',
        )
        db.session.add(report)
        db.session.commit()

        response = client.get('/api/admin/reports/fix-truncated-titles', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True

    def test_fix_truncated_without_auth(self, client):
        response = client.get('/api/admin/reports/fix-truncated-titles')
        assert response.status_code in (401, 403)

    def test_fix_truncated_exception(self, client, admin_headers, db):
        from app.models.schemas import BookMetadata

        mock_q = MagicMock()
        mock_q.all.side_effect = RuntimeError('DB错误')

        with (
            patch.object(BookMetadata, 'query', new=mock_q),
            patch('app.routes.admin.log_error'),
        ):
            response = client.get('/api/admin/reports/fix-truncated-titles', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is False


# ==================== 翻译清理 ====================


class TestCleanupTranslations:
    """GET|POST /api/admin/translations/cleanup"""

    def test_dry_run_get(self, client, admin_headers, db):
        from app.models.schemas import TranslationCache

        record = TranslationCache(
            source_hash='abc123',
            source_text='Hello World',
            source_lang='en',
            target_lang='zh',
            translated_text='**《书名》** 作者：张三',
        )
        db.session.add(record)
        db.session.commit()

        response = client.get('/api/admin/translations/cleanup', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'translation_cache' in data['data']

    def test_dry_run_post(self, client, admin_headers, db):
        from app.models.schemas import TranslationCache

        record = TranslationCache(
            source_hash='abc123',
            source_text='Hello',
            source_lang='en',
            target_lang='zh',
            translated_text='干净的翻译',
        )
        db.session.add(record)
        db.session.commit()

        response = client.post(
            '/api/admin/translations/cleanup',
            data=json.dumps({'dry_run': True}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True

    def test_execute_cleanup(self, client, admin_headers, db):
        from app.models.schemas import TranslationCache

        record = TranslationCache(
            source_hash='abc123',
            source_text='Hello World',
            source_lang='en',
            target_lang='zh',
            translated_text='**《书名》** 作者：张三',
        )
        db.session.add(record)
        db.session.commit()

        response = client.post(
            '/api/admin/translations/cleanup',
            data=json.dumps({'dry_run': False}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True

    def test_metadata_cleanup(self, client, admin_headers, db):
        from app.models.schemas import BookMetadata

        bm = BookMetadata(
            isbn='9781234567890',
            title='Test',
            author='Author',
            title_zh='**脏数据**书名',
        )
        db.session.add(bm)
        db.session.commit()

        response = client.get('/api/admin/translations/cleanup', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'book_metadata' in data['data']

    def test_no_dirty_translations(self, client, admin_headers, db):
        from app.models.schemas import TranslationCache

        record = TranslationCache(
            source_hash='abc123',
            source_text='Hello',
            source_lang='en',
            target_lang='zh',
            translated_text='你好',
        )
        db.session.add(record)
        db.session.commit()

        response = client.get('/api/admin/translations/cleanup', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        tc = data['data']['translation_cache']
        assert tc['fixable'] == 0

    def test_empty_database(self, client, admin_headers, db):
        response = client.get('/api/admin/translations/cleanup', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['translation_cache']['total'] == 0
        assert data['data']['book_metadata']['total'] == 0

    def test_cleanup_translations_without_auth(self, client):
        response = client.get('/api/admin/translations/cleanup')
        assert response.status_code in (401, 403)

    def test_cleanup_translations_exception(self, client, admin_headers, db):
        mock_log = MagicMock()

        with patch('app.routes.admin.log_error', mock_log):
            response = client.get('/api/admin/translations/cleanup', headers=admin_headers)
            data = json.loads(response.data)
            assert 'data' in data


# ==================== 错误查看与清空 ====================


class TestViewErrors:
    """GET /api/admin/errors"""

    def test_view_errors_success(self, client, admin_headers):
        mock_tracker = MagicMock()
        mock_tracker.get_stats.return_value = {'api_call': 5, 'db_query': 2}
        mock_tracker.get_recent.return_value = [
            {'error_type': 'api_call', 'message': '测试错误'},
        ]

        with patch('app.routes.admin.error_tracker', mock_tracker):
            response = client.get('/api/admin/errors', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['total_count'] == 7
            assert data['data']['error_stats'] == {'api_call': 5, 'db_query': 2}
            assert len(data['data']['recent_errors']) == 1

    def test_view_errors_empty(self, client, admin_headers):
        mock_tracker = MagicMock()
        mock_tracker.get_stats.return_value = {}
        mock_tracker.get_recent.return_value = []

        with patch('app.routes.admin.error_tracker', mock_tracker):
            response = client.get('/api/admin/errors', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['total_count'] == 0

    def test_view_errors_exception(self, client, admin_headers):
        mock_tracker = MagicMock()
        mock_tracker.get_stats.side_effect = RuntimeError('内存错误')

        with (
            patch('app.routes.admin.error_tracker', mock_tracker),
            patch('app.routes.admin.log_error'),
        ):
            response = client.get('/api/admin/errors', headers=admin_headers)
            data = json.loads(response.data)
            assert data['success'] is False

    def test_view_errors_without_auth(self, client):
        response = client.get('/api/admin/errors')
        assert response.status_code in (401, 403)


class TestClearErrors:
    """POST /api/admin/errors/clear"""

    def test_clear_errors_success(self, client, admin_headers):
        mock_tracker = MagicMock()
        mock_tracker.clear.return_value = None

        with patch('app.routes.admin.error_tracker', mock_tracker):
            response = client.post(
                '/api/admin/errors/clear',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is True
            mock_tracker.clear.assert_called_once()

    def test_clear_errors_exception(self, client, admin_headers):
        mock_tracker = MagicMock()
        mock_tracker.clear.side_effect = RuntimeError('清空失败')

        with (
            patch('app.routes.admin.error_tracker', mock_tracker),
            patch('app.routes.admin.log_error'),
        ):
            response = client.post(
                '/api/admin/errors/clear',
                data=json.dumps({}),
                content_type='application/json',
                headers=admin_headers,
            )
            data = json.loads(response.data)
            assert data['success'] is False

    def test_clear_errors_without_auth(self, client):
        response = client.post(
            '/api/admin/errors/clear',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (401, 403)


# ==================== 辅助函数测试 ====================


class TestCleanReportText:
    """_clean_report_text 辅助函数"""

    def test_clean_empty_text(self):
        from app.routes.admin import _clean_report_text

        assert _clean_report_text('') == ''
        assert _clean_report_text(None) is None

    def test_clean_double_brackets(self):
        from app.routes.admin import _clean_report_text

        result = _clean_report_text('《《书名》》')
        assert '《《' not in result

    def test_clean_markdown_bold(self):
        from app.routes.admin import _clean_report_text

        result = _clean_report_text('**《书名》**')
        assert '**' not in result
        assert '《书名》' in result

    def test_clean_markdown_italic(self):
        from app.routes.admin import _clean_report_text

        result = _clean_report_text('*《书名》*')
        assert '*《' not in result
        assert '《书名》' in result
