"""setup.py 扩展测试 —— 覆盖 _init_*、_start_background_tasks、任务函数等未测路径"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

# ==================== _init_nyt_client ====================


class TestInitNytClient:
    """测试 _init_nyt_client 辅助函数"""

    def test_success(self, app):
        from app.setup import _init_nyt_client

        with app.app_context():
            client = _init_nyt_client(app.config, app)
            assert client is not None

    def test_success_uses_config_values(self, app):
        from app.setup import _init_nyt_client

        with app.app_context():
            client = _init_nyt_client(app.config, app)
            assert client._api_key == app.config.get('NYT_API_KEY', '')

    @patch('app.setup.NYTApiClient', side_effect=Exception('NYT构造失败'))
    def test_returns_none_on_exception(self, mock_cls, app):
        from app.setup import _init_nyt_client

        with app.app_context():
            client = _init_nyt_client(app.config, app)
            assert client is None


# ==================== _init_google_client ====================


class TestInitGoogleClient:
    """测试 _init_google_client 辅助函数"""

    def test_success(self, app):
        from app.setup import _init_google_client

        with app.app_context():
            client = _init_google_client(app.config, app)
            assert client is not None

    @patch('app.setup.GoogleBooksClient', side_effect=Exception('Google构造失败'))
    def test_returns_none_on_exception(self, mock_cls, app):
        from app.setup import _init_google_client

        with app.app_context():
            client = _init_google_client(app.config, app)
            assert client is None


# ==================== _init_image_cache ====================


class TestInitImageCache:
    """测试 _init_image_cache 辅助函数"""

    def test_success(self, app):
        from app.setup import _init_image_cache

        with app.app_context():
            result = _init_image_cache(app.config, app)
            assert result is not None

    def test_returns_none_on_exception(self, app):
        from app.setup import _init_image_cache

        with app.app_context():
            bad_cfg = dict(app.config)
            bad_cfg['IMAGE_CACHE_DIR'] = None
            result = _init_image_cache(bad_cfg, app)
            assert result is None


# ==================== _init_translation_service ====================


class TestInitTranslationService:
    """测试 _init_translation_service 辅助函数"""

    @patch('app.setup.register_service')
    def test_success(self, mock_register, app):
        from app.setup import _init_translation_service

        mock_translation = MagicMock()
        with (
            app.app_context(),
            patch(
                'app.services.zhipu_translation_service.get_translation_service',
                return_value=mock_translation,
            ),
        ):
            result = _init_translation_service(app)
            assert result is mock_translation
            mock_register.assert_called_once_with(app, 'translation_service', mock_translation)

    @patch('app.setup.register_service')
    def test_returns_none_on_exception(self, mock_register, app):
        from app.setup import _init_translation_service

        with (
            app.app_context(),
            patch(
                'app.services.zhipu_translation_service.get_translation_service',
                side_effect=RuntimeError('翻译服务不可用'),
            ),
        ):
            result = _init_translation_service(app)
            assert result is None


# ==================== _init_book_service ====================


class TestInitBookService:
    """测试 _init_book_service 辅助函数"""

    def test_returns_none_when_no_nyt_client(self, app):
        from app.setup import _init_book_service

        with app.app_context():
            result = _init_book_service(
                nyt_client=None,
                google_client=MagicMock(),
                cache_service=MagicMock(),
                image_cache=MagicMock(),
                app=app,
                cfg=app.config,
            )
            assert result is None

    def test_returns_none_when_no_cache_service(self, app):
        from app.setup import _init_book_service

        with app.app_context():
            result = _init_book_service(
                nyt_client=MagicMock(),
                google_client=MagicMock(),
                cache_service=None,
                image_cache=MagicMock(),
                app=app,
                cfg=app.config,
            )
            assert result is None

    @patch('app.setup.register_service')
    def test_success(self, mock_register, app):
        from app.setup import _init_book_service

        with app.app_context():
            result = _init_book_service(
                nyt_client=MagicMock(),
                google_client=MagicMock(),
                cache_service=MagicMock(),
                image_cache=MagicMock(),
                app=app,
                cfg=app.config,
            )
            assert result is not None
            mock_register.assert_called()

    @patch('app.setup.register_service')
    def test_registers_data_refreshed_callback(self, mock_register, app):
        from app.setup import _init_book_service

        with app.app_context():
            result = _init_book_service(
                nyt_client=MagicMock(),
                google_client=MagicMock(),
                cache_service=MagicMock(),
                image_cache=MagicMock(),
                app=app,
                cfg=app.config,
            )
            assert result is not None
            assert callable(getattr(result, 'on_data_refreshed', None))

    @patch('app.setup.log_error')
    @patch('app.setup.register_service', side_effect=Exception('注册失败'))
    def test_returns_none_on_exception(self, mock_register, mock_log_error, app):
        from app.setup import _init_book_service

        with app.app_context():
            result = _init_book_service(
                nyt_client=MagicMock(),
                google_client=MagicMock(),
                cache_service=MagicMock(),
                image_cache=MagicMock(),
                app=app,
                cfg=app.config,
            )
            assert result is None


# ==================== _start_background_tasks ====================


class TestStartBackgroundTasks:
    """测试 _start_background_tasks 函数"""

    def test_skips_in_testing_mode(self, app):
        from app.setup import _start_background_tasks

        with app.app_context():
            app.config['TESTING'] = True
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            assert app.extensions.get('_scheduler') is None

    @patch.dict('os.environ', {'DISABLE_BACKGROUND_THREADS': 'true'})
    def test_skips_when_disabled(self, app):
        from app.setup import _start_background_tasks

        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            assert app.extensions.get('_scheduler') is None

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_creates_scheduler(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            mock_sched_cls.assert_called_once()
            mock_scheduler.start.assert_called_once()

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_with_book_service_adds_weekly_and_nyt_jobs(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            book_svc = MagicMock()
            _start_background_tasks(app, book_svc, MagicMock(), MagicMock())
            job_ids = [call.kwargs.get('id') for call in mock_scheduler.add_job.call_args_list]
            assert 'weekly_report_init' in job_ids
            assert 'nyt_ranking_sync' in job_ids
            assert 'auto_sync' in job_ids

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_with_google_client_adds_cover_sync(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            job_ids = [call.kwargs.get('id') for call in mock_scheduler.add_job.call_args_list]
            assert 'cover_sync_init' in job_ids

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_with_translation_service_adds_cleanup_job(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            job_ids = [call.kwargs.get('id') for call in mock_scheduler.add_job.call_args_list]
            assert 'translation_cache_cleanup' in job_ids

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_without_book_service_skips_weekly_and_nyt(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, None, MagicMock(), MagicMock())
            job_ids = [call.kwargs.get('id') for call in mock_scheduler.add_job.call_args_list]
            assert 'weekly_report_init' not in job_ids
            assert 'nyt_ranking_sync' not in job_ids

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_without_google_client_skips_cover_sync(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), None)
            job_ids = [call.kwargs.get('id') for call in mock_scheduler.add_job.call_args_list]
            assert 'cover_sync_init' not in job_ids

    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_without_translation_skips_cleanup(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), None, MagicMock())
            job_ids = [call.kwargs.get('id') for call in mock_scheduler.add_job.call_args_list]
            assert 'translation_cache_cleanup' not in job_ids

    @patch('app.setup._scheduler')
    @patch('app.setup.BackgroundScheduler')
    def test_skips_when_scheduler_already_running(self, mock_sched_cls, mock_global, app):
        from app.setup import _start_background_tasks

        mock_global.running = True
        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            mock_sched_cls.assert_not_called()

    @patch.dict('os.environ', {'RENDER': 'true'})
    @patch('app.setup._scheduler', None)
    @patch('app.setup.BackgroundScheduler')
    def test_render_free_uses_longer_delays(self, mock_sched_cls, app):
        from app.setup import _start_background_tasks

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_sched_cls.return_value = mock_scheduler

        app.config['TESTING'] = False
        with app.app_context():
            _start_background_tasks(app, MagicMock(), MagicMock(), MagicMock())
            date_triggers = [
                call.kwargs['trigger']
                for call in mock_scheduler.add_job.call_args_list
                if hasattr(call.kwargs.get('trigger'), 'run_date')
            ]
            assert len(date_triggers) > 0


# ==================== _scheduler_wrapper ====================


class TestSchedulerWrapper:
    """测试 _scheduler_wrapper 辅助函数"""

    def test_wrapper_calls_task_in_app_context(self, app):
        from app.setup import _scheduler_wrapper

        with app.app_context():
            mock_task = MagicMock()
            mock_task.__name__ = 'test_task'

            wrapper = _scheduler_wrapper(app, mock_task)
            wrapper()
            mock_task.assert_called_once_with(app)

    def test_wrapper_catches_exceptions(self, app):
        from app.setup import _scheduler_wrapper

        with app.app_context():
            mock_task = MagicMock(side_effect=Exception('任务崩溃'))
            mock_task.__name__ = 'failing_task'

            wrapper = _scheduler_wrapper(app, mock_task)
            wrapper()

    def test_wrapper_preserves_function_name(self, app):
        from app.setup import _scheduler_wrapper

        with app.app_context():
            mock_task = MagicMock()
            mock_task.__name__ = 'my_custom_task'

            wrapper = _scheduler_wrapper(app, mock_task)
            assert wrapper.__name__ == 'my_custom_task'


# ==================== shutdown_scheduler ====================


class TestShutdownSchedulerExtended:
    """shutdown_scheduler 扩展测试"""

    def test_shutdown_when_not_running(self, app):
        from app.setup import shutdown_scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        with patch('app.setup._scheduler', mock_scheduler):
            shutdown_scheduler(app)
            mock_scheduler.shutdown.assert_not_called()

    def test_shutdown_sets_scheduler_to_none(self, app):
        from app.setup import shutdown_scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        with patch('app.setup._scheduler', mock_scheduler):
            shutdown_scheduler(app)
            import app.setup as setup_mod

            assert setup_mod._scheduler is None


# ==================== 任务函数 ====================


class TestWeeklyReportTask:
    """测试 _weekly_report_task"""

    @patch('app.setup.log_error')
    def test_calls_generate_weekly_report(self, mock_log_error, app):
        from app.setup import _weekly_report_task

        with app.app_context():
            mock_report = MagicMock()
            mock_report.title = '测试周报'
            with patch(
                'app.tasks.weekly_report_task.generate_weekly_report',
                return_value=mock_report,
            ):
                _weekly_report_task(app)

    @patch('app.setup.log_error')
    def test_handles_none_report(self, mock_log_error, app):
        from app.setup import _weekly_report_task

        with (
            app.app_context(),
            patch(
                'app.tasks.weekly_report_task.generate_weekly_report',
                return_value=None,
            ),
        ):
            _weekly_report_task(app)

    @patch('app.setup.log_error')
    @patch('app.setup._log_failure')
    def test_handles_exception(self, mock_log_failure, mock_log_error, app):
        from app.setup import _weekly_report_task

        with (
            app.app_context(),
            patch(
                'app.tasks.weekly_report_task.generate_weekly_report',
                side_effect=Exception('生成失败'),
            ),
        ):
            _weekly_report_task(app)
            mock_log_failure.assert_called_once_with(app, 'last_report_failure')


class TestAutoSyncTask:
    """测试 _auto_sync_task"""

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    def test_skips_when_recently_synced(self, mock_log_error, mock_config, app):
        from app.setup import _auto_sync_task

        mock_config.get_value.return_value = datetime.now(UTC).isoformat()
        with app.app_context():
            _auto_sync_task(app)

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    def test_syncs_when_old_or_no_previous(self, mock_log_error, mock_config, app):
        from app.setup import _auto_sync_task

        mock_config.get_value.return_value = None
        mock_service = MagicMock()
        mock_service.sync_all_publishers.return_value = [{'added': 2, 'updated': 1}]
        with app.app_context():
            with patch('app.services.new_book_service.NewBookService', return_value=mock_service):
                with patch('app.utils.service_helpers.get_translation_service', return_value=MagicMock()):
                    _auto_sync_task(app)
                    mock_service.sync_all_publishers.assert_called_once()

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    @patch('app.setup._log_failure')
    def test_handles_exception(self, mock_log_failure, mock_log_error, mock_config, app):
        from app.setup import _auto_sync_task

        mock_config.get_value.side_effect = Exception('DB错误')
        with app.app_context():
            _auto_sync_task(app)
            mock_log_failure.assert_called_once_with(app, 'last_sync_failure')


class TestNytRankingSyncTask:
    """测试 _nyt_ranking_sync_task"""

    @patch('app.setup.log_error')
    def test_skips_when_no_book_service(self, mock_log_error, app):
        from app.setup import _nyt_ranking_sync_task

        with app.app_context(), patch('app.utils.service_helpers.get_book_service', return_value=None):
            _nyt_ranking_sync_task(app)

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    def test_skips_when_recently_synced(self, mock_log_error, mock_config, app):
        from app.setup import _nyt_ranking_sync_task

        mock_config.get_value.return_value = datetime.now(UTC).isoformat()
        mock_book_svc = MagicMock()
        with app.app_context(), patch('app.utils.service_helpers.get_book_service', return_value=mock_book_svc):
            _nyt_ranking_sync_task(app)
            mock_book_svc.sync_all_categories.assert_not_called()

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    def test_syncs_when_old(self, mock_log_error, mock_config, app):
        from app.setup import _nyt_ranking_sync_task

        mock_config.get_value.return_value = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        mock_book_svc = MagicMock()
        mock_book_svc.sync_all_categories.return_value = [
            {'success': True, 'books': 5, 'metadata_saved': 3, 'language_pack': {'fields_translated': 2}},
        ]
        with app.app_context(), patch('app.utils.service_helpers.get_book_service', return_value=mock_book_svc):
            with patch('app.utils.service_helpers.get_translation_service', return_value=MagicMock()):
                _nyt_ranking_sync_task(app)
                mock_book_svc.sync_all_categories.assert_called_once()

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    def test_handles_partial_failure(self, mock_log_error, mock_config, app):
        from app.setup import _nyt_ranking_sync_task

        mock_config.get_value.return_value = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        mock_book_svc = MagicMock()
        mock_book_svc.sync_all_categories.return_value = [
            {'success': True, 'books': 5, 'metadata_saved': 3, 'language_pack': {'fields_translated': 2}},
            {'success': False, 'books': 0, 'metadata_saved': 0, 'language_pack': {}},
        ]
        with app.app_context(), patch('app.utils.service_helpers.get_book_service', return_value=mock_book_svc):
            with patch('app.utils.service_helpers.get_translation_service', return_value=MagicMock()):
                _nyt_ranking_sync_task(app)

    @patch('app.setup.SystemConfig')
    @patch('app.setup.log_error')
    @patch('app.setup._log_failure')
    @patch('app.utils.service_helpers.get_book_service')
    def test_handles_exception(self, mock_get_book, mock_log_failure, mock_log_error, mock_config, app):
        from app.setup import _nyt_ranking_sync_task

        mock_get_book.return_value = MagicMock()
        mock_config.get_value.side_effect = Exception('DB错误')
        with app.app_context():
            _nyt_ranking_sync_task(app)
            mock_log_failure.assert_called()


class TestCoverSyncTask:
    """测试 _cover_sync_task"""

    @patch('app.setup.log_error')
    def test_success_status(self, mock_log_error, app):
        from app.setup import _cover_sync_task

        mock_sync_svc = MagicMock()
        mock_sync_svc.sync_missing_covers.return_value = {'status': 'success', 'updated': 3, 'skipped': 1}
        with app.app_context():
            with patch('app.utils.service_helpers.get_google_books_client', return_value=MagicMock()):
                with patch('app.utils.service_helpers.get_image_cache_service', return_value=MagicMock()):
                    with patch(
                        'app.services.award_cover_sync_service.AwardCoverSyncService',
                        return_value=mock_sync_svc,
                    ):
                        _cover_sync_task(app)

    @patch('app.setup.log_error')
    def test_complete_status(self, mock_log_error, app):
        from app.setup import _cover_sync_task

        mock_sync_svc = MagicMock()
        mock_sync_svc.sync_missing_covers.return_value = {'status': 'complete'}
        with app.app_context():
            with patch('app.utils.service_helpers.get_google_books_client', return_value=MagicMock()):
                with patch('app.utils.service_helpers.get_image_cache_service', return_value=MagicMock()):
                    with patch(
                        'app.services.award_cover_sync_service.AwardCoverSyncService',
                        return_value=mock_sync_svc,
                    ):
                        _cover_sync_task(app)

    @patch('app.setup.log_error')
    def test_other_status(self, mock_log_error, app):
        from app.setup import _cover_sync_task

        mock_sync_svc = MagicMock()
        mock_sync_svc.sync_missing_covers.return_value = {'status': 'unknown'}
        with app.app_context():
            with patch('app.utils.service_helpers.get_google_books_client', return_value=MagicMock()):
                with patch('app.utils.service_helpers.get_image_cache_service', return_value=MagicMock()):
                    with patch(
                        'app.services.award_cover_sync_service.AwardCoverSyncService',
                        return_value=mock_sync_svc,
                    ):
                        _cover_sync_task(app)

    @patch('app.setup.log_error')
    def test_creates_client_when_none(self, mock_log_error, app):
        from app.setup import _cover_sync_task

        mock_sync_svc = MagicMock()
        mock_sync_svc.sync_missing_covers.return_value = {'status': 'success', 'updated': 0, 'skipped': 0}
        with app.app_context(), patch('app.utils.service_helpers.get_google_books_client', return_value=None):
            with patch('app.utils.service_helpers.get_image_cache_service', return_value=MagicMock()):
                with patch(
                    'app.services.award_cover_sync_service.AwardCoverSyncService',
                    return_value=mock_sync_svc,
                ):
                    with patch('app.services.google_books_client.GoogleBooksClient'):
                        _cover_sync_task(app)

    @patch('app.setup.log_error')
    def test_handles_exception(self, mock_log_error, app):
        from app.setup import _cover_sync_task

        with app.app_context():
            with patch('app.utils.service_helpers.get_google_books_client', side_effect=Exception('连接失败')):
                _cover_sync_task(app)
                mock_log_error.assert_called()


class TestTranslationCacheCleanupTask:
    """测试 _translation_cache_cleanup_task"""

    def test_success(self, app):
        from app.setup import _translation_cache_cleanup_task

        mock_cache_svc = MagicMock()
        with (
            app.app_context(),
            patch(
                'app.services.translation_cache_service.get_translation_cache_service',
                return_value=mock_cache_svc,
            ),
        ):
            _translation_cache_cleanup_task(app)
            mock_cache_svc.auto_cleanup.assert_called_once_with(max_items=8000, keep_recent_days=30)

    def test_handles_none_cache_service(self, app):
        from app.setup import _translation_cache_cleanup_task

        with (
            app.app_context(),
            patch(
                'app.services.translation_cache_service.get_translation_cache_service',
                return_value=None,
            ),
        ):
            _translation_cache_cleanup_task(app)

    @patch('app.setup.log_error')
    def test_handles_exception(self, mock_log_error, app):
        from app.setup import _translation_cache_cleanup_task

        with (
            app.app_context(),
            patch(
                'app.services.translation_cache_service.get_translation_cache_service',
                side_effect=Exception('缓存服务不可用'),
            ),
        ):
            _translation_cache_cleanup_task(app)
            mock_log_error.assert_called()


class TestLogFailure:
    """测试 _log_failure 辅助函数"""

    def test_success(self, app):
        from app.setup import _log_failure

        with app.app_context():
            _log_failure(app, 'test_failure_key')

    @patch('app.setup.log_error')
    def test_handles_exception(self, mock_log_error, app):
        from app.setup import _log_failure

        with app.app_context():
            with patch('app.models.schemas.SystemConfig.set_value', side_effect=Exception('DB错误')):
                _log_failure(app, 'test_key')
                mock_log_error.assert_called()


# ==================== init_services 集成测试 ====================


class TestInitServicesExtended:
    """init_services 更多覆盖测试"""

    def test_all_services_registered(self, app):

        with app.app_context():
            assert 'cache_service' in app.extensions

    @patch('app.setup._start_background_tasks')
    @patch('app.setup._init_book_service')
    @patch('app.setup._init_translation_service')
    @patch('app.setup._init_image_cache')
    @patch('app.setup._init_google_client')
    @patch('app.setup._init_nyt_client')
    @patch('app.setup.register_service')
    def test_calls_all_init_helpers(
        self,
        mock_reg,
        mock_nyt,
        mock_google,
        mock_image,
        mock_trans,
        mock_book,
        mock_bg,
        app,
    ):
        from app.setup import init_services

        mock_nyt.return_value = MagicMock()
        mock_google.return_value = MagicMock()
        mock_image.return_value = MagicMock()
        mock_trans.return_value = MagicMock()
        mock_book.return_value = MagicMock()

        with app.app_context():
            init_services(app)

            mock_nyt.assert_called_once()
            mock_google.assert_called_once()
            mock_image.assert_called_once()
            mock_trans.assert_called_once()
            mock_book.assert_called_once()
            mock_bg.assert_called_once()

    @patch('app.setup._start_background_tasks')
    @patch('app.setup._init_book_service', return_value=None)
    @patch('app.setup._init_translation_service', return_value=None)
    @patch('app.setup._init_image_cache', return_value=None)
    @patch('app.setup._init_google_client', return_value=None)
    @patch('app.setup._init_nyt_client', return_value=None)
    @patch('app.setup.register_service')
    def test_still_calls_background_tasks_when_book_service_none(
        self,
        mock_reg,
        mock_nyt,
        mock_google,
        mock_image,
        mock_trans,
        mock_book,
        mock_bg,
        app,
    ):
        from app.setup import init_services

        with app.app_context():
            init_services(app)
            mock_bg.assert_called_once()
            call_args = mock_bg.call_args[0]
            assert call_args[1] is None
