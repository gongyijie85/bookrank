from app.utils.error_tracker import ErrorTracker, error_tracker


class TestErrorTracker:
    """error_tracker 环形缓冲区单元测试"""

    def setup_method(self) -> None:
        error_tracker.clear()

    def test_singleton(self) -> None:
        tracker1 = ErrorTracker()
        tracker2 = ErrorTracker()
        assert tracker1 is tracker2

    def test_record_and_retrieve(self) -> None:
        error_tracker.record('500', '测试错误', '/test', 'GET')
        recent = error_tracker.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]['error_type'] == '500'
        assert recent[0]['message'] == '测试错误'
        assert recent[0]['path'] == '/test'
        assert recent[0]['method'] == 'GET'

    def test_get_recent_reverse_order(self) -> None:
        error_tracker.record('500', '错误1', '/a', 'GET')
        error_tracker.record('400', '错误2', '/b', 'POST')
        error_tracker.record('500', '错误3', '/c', 'PUT')
        recent = error_tracker.get_recent(limit=2)
        assert len(recent) == 2
        assert recent[0]['message'] == '错误3'
        assert recent[1]['message'] == '错误2'

    def test_get_stats(self) -> None:
        error_tracker.record('500', '错误1', '/a', 'GET')
        error_tracker.record('500', '错误2', '/b', 'GET')
        error_tracker.record('400', '错误3', '/c', 'POST')
        stats = error_tracker.get_stats()
        assert stats['500'] == 2
        assert stats['400'] == 1

    def test_filter_by_type(self) -> None:
        error_tracker.record('500', '错误A', '/a', 'GET')
        error_tracker.record('400', '错误B', '/b', 'GET')
        filtered = error_tracker.get_recent(error_type='400')
        assert len(filtered) == 1
        assert filtered[0]['message'] == '错误B'

    def test_clear(self) -> None:
        error_tracker.record('500', '错误', '/a', 'GET')
        assert len(error_tracker.get_recent()) == 1
        error_tracker.clear()
        assert len(error_tracker.get_recent()) == 0

    def test_ring_buffer_limit(self) -> None:
        for i in range(600):
            error_tracker.record('500', f'错误{i}', '/a', 'GET')
        recent = error_tracker.get_recent(limit=600)
        assert len(recent) == 500

    def test_message_truncation(self) -> None:
        long_msg = 'x' * 1000
        error_tracker.record('500', long_msg, '/a', 'GET')
        recent = error_tracker.get_recent()
        assert len(recent[0]['message']) <= 500

    def test_empty_stats(self) -> None:
        stats = error_tracker.get_stats()
        assert stats == {}


class TestErrorTrackerAPI:
    """错误追踪 API 端点测试"""

    def test_view_errors_unauthorized(self, client) -> None:
        """无认证访问应被拒绝"""
        response = client.get('/api/admin/errors')
        assert response.status_code in (302, 401, 403)

    def test_clear_errors_unauthorized(self, client) -> None:
        """无认证清空应被拒绝"""
        response = client.post('/api/admin/errors/clear')
        assert response.status_code in (302, 401, 403)
