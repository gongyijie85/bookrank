"""service_helpers 工具函数测试"""

from unittest.mock import MagicMock

import pytest

from app.utils.service_helpers import (
    get_google_books_client,
    get_or_create_recommendation_service,
    get_or_create_smart_search_service,
    get_service,
    hash_client_ip,
    require_service,
    submit_background_task,
)


class TestGetService:
    """测试 get_service"""

    def test_service_exists(self, app):
        mock_service = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_service
            assert get_service('book_service') is mock_service
            del app.extensions['book_service']

    def test_service_not_exists(self, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            assert get_service('book_service') is None


class TestRequireService:
    """测试 require_service"""

    def test_service_exists(self, app):
        mock_service = MagicMock()
        original = app.extensions.get('book_service')
        with app.app_context():
            app.extensions['book_service'] = mock_service
            assert require_service('book_service') is mock_service
        if original is not None:
            app.extensions['book_service'] = original
        else:
            app.extensions.pop('book_service', None)

    def test_service_not_exists_raises(self, app):
        original = app.extensions.get('book_service')
        with app.app_context():
            app.extensions.pop('book_service', None)
            with pytest.raises(RuntimeError, match='图书服务未初始化'):
                require_service('book_service', '图书服务')
        if original is not None:
            app.extensions['book_service'] = original


class TestSubmitBackgroundTask:
    """测试 submit_background_task"""

    def test_submit(self):
        def dummy_task(x, y):
            return x + y

        future = submit_background_task(dummy_task, 1, 2)
        assert future.result(timeout=5) == 3


class TestGetGoogleBooksClient:
    """测试 get_google_books_client"""

    def test_with_client(self, app):
        mock_service = MagicMock()
        mock_client = MagicMock()
        mock_service._google_client = mock_client

        with app.app_context():
            app.extensions['book_service'] = mock_service
            assert get_google_books_client() is mock_client
            del app.extensions['book_service']

    def test_without_service(self, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            assert get_google_books_client() is None


class TestHashClientIp:
    """hash_client_ip"""

    def test_returns_none_for_empty(self, app):
        with app.test_request_context():
            assert hash_client_ip('') is None

    def test_hashes_provided_ip(self, app):
        with app.test_request_context():
            digest = hash_client_ip('1.2.3.4')
            assert digest is not None
            assert len(digest) == 16
            assert hash_client_ip('1.2.3.4') == digest
            assert hash_client_ip('5.6.7.8') != digest


class TestServiceSingletons:
    """RecommendationService/SmartSearchService 单例 helper"""

    def test_recommendation_get_or_create_creates_when_missing(self, app):
        with app.app_context():
            app.extensions.pop('recommendation_service', None)
            assert get_or_create_recommendation_service() is not None

    def test_recommendation_get_or_create_returns_singleton(self, app):
        mock_svc = MagicMock()
        original = app.extensions.get('recommendation_service')
        with app.app_context():
            app.extensions['recommendation_service'] = mock_svc
            assert get_or_create_recommendation_service() is mock_svc
        if original is not None:
            app.extensions['recommendation_service'] = original
        else:
            app.extensions.pop('recommendation_service', None)

    def test_smart_search_get_or_create_creates_when_missing(self, app):
        with app.app_context():
            app.extensions.pop('smart_search_service', None)
            assert get_or_create_smart_search_service() is not None

    def test_smart_search_get_or_create_returns_singleton(self, app):
        mock_svc = MagicMock()
        original = app.extensions.get('smart_search_service')
        with app.app_context():
            app.extensions['smart_search_service'] = mock_svc
            assert get_or_create_smart_search_service() is mock_svc
        if original is not None:
            app.extensions['smart_search_service'] = original
        else:
            app.extensions.pop('smart_search_service', None)
