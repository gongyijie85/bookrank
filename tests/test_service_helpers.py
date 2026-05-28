"""service_helpers 工具函数测试"""

from unittest.mock import MagicMock

import pytest

from app.utils.service_helpers import (
    db_transaction,
    get_book_service,
    get_cache_service,
    get_google_books_client,
    get_image_cache_service,
    get_translation_service,
    require_book_service,
    submit_background_task,
)


class TestGetBookService:
    """测试 get_book_service"""

    def test_service_exists(self, app):
        mock_service = MagicMock()
        with app.app_context():
            app.extensions['book_service'] = mock_service
            result = get_book_service()
            assert result is mock_service
            del app.extensions['book_service']

    def test_service_not_exists(self, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            result = get_book_service()
            assert result is None


class TestGetCacheService:
    """测试 get_cache_service"""

    def test_service_exists(self, app):
        mock_service = MagicMock()
        original = app.extensions.get('cache_service')
        with app.app_context():
            app.extensions['cache_service'] = mock_service
            result = get_cache_service()
            assert result is mock_service
        if original is not None:
            app.extensions['cache_service'] = original
        else:
            app.extensions.pop('cache_service', None)

    def test_service_not_exists(self, app):
        original = app.extensions.get('cache_service')
        with app.app_context():
            app.extensions.pop('cache_service', None)
            result = get_cache_service()
            assert result is None
        if original is not None:
            app.extensions['cache_service'] = original


class TestGetImageCacheService:
    """测试 get_image_cache_service"""

    def test_service_not_exists(self, app):
        original = app.extensions.get('image_cache_service')
        with app.app_context():
            app.extensions.pop('image_cache_service', None)
            result = get_image_cache_service()
            assert result is None
        if original is not None:
            app.extensions['image_cache_service'] = original


class TestGetTranslationService:
    """测试 get_translation_service"""

    def test_service_not_exists(self, app):
        original = app.extensions.get('translation_service')
        with app.app_context():
            app.extensions.pop('translation_service', None)
            result = get_translation_service()
            assert result is None
        if original is not None:
            app.extensions['translation_service'] = original


class TestRequireBookService:
    """测试 require_book_service"""

    def test_service_exists(self, app):
        mock_service = MagicMock()
        original = app.extensions.get('book_service')
        with app.app_context():
            app.extensions['book_service'] = mock_service
            result = require_book_service()
            assert result is mock_service
        if original is not None:
            app.extensions['book_service'] = original
        else:
            app.extensions.pop('book_service', None)

    def test_service_not_exists_raises(self, app):
        original = app.extensions.get('book_service')
        with app.app_context():
            app.extensions.pop('book_service', None)
            with pytest.raises(RuntimeError, match='图书服务未初始化'):
                require_book_service()
        if original is not None:
            app.extensions['book_service'] = original


class TestDbTransaction:
    """测试 db_transaction"""

    def test_successful_transaction(self, app, db):
        with app.app_context(), db_transaction():
            pass

    def test_failed_transaction(self, app, db):
        with app.app_context(), pytest.raises(ValueError), db_transaction():
            raise ValueError('test error')


class TestSubmitBackgroundTask:
    """测试 submit_background_task"""

    def test_submit(self):
        def dummy_task(x, y):
            return x + y

        future = submit_background_task(dummy_task, 1, 2)
        result = future.result(timeout=5)
        assert result == 3


class TestGetGoogleBooksClient:
    """测试 get_google_books_client"""

    def test_with_client(self, app):
        mock_service = MagicMock()
        mock_client = MagicMock()
        mock_service._google_client = mock_client

        with app.app_context():
            app.extensions['book_service'] = mock_service
            result = get_google_books_client()
            assert result is mock_client
            del app.extensions['book_service']

    def test_without_service(self, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            result = get_google_books_client()
            assert result is None
