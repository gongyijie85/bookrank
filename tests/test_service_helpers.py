"""service_helpers 工具函数测试"""

from unittest.mock import MagicMock

import pytest

from app.utils.service_helpers import (
    db_transaction,
    get_book_service,
    get_cache_service,
    get_google_books_client,
    get_image_cache_service,
    get_or_create_recommendation_service,
    get_or_create_smart_search_service,
    get_recommendation_service,
    get_smart_search_service,
    get_translation_service,
    hash_client_ip,
    require_book_service,
    require_cache_service,
    require_image_cache_service,
    require_translation_service,
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


class TestRequireCacheService:
    """require_cache_service 异常路径"""

    def test_not_initialized_raises(self, app):
        original = app.extensions.get('cache_service')
        with app.app_context():
            app.extensions.pop('cache_service', None)
            with pytest.raises(RuntimeError, match='缓存服务未初始化'):
                require_cache_service()
        if original is not None:
            app.extensions['cache_service'] = original


class TestRequireTranslationService:
    """require_translation_service 异常路径"""

    def test_not_initialized_raises(self, app):
        original = app.extensions.get('translation_service')
        with app.app_context():
            app.extensions.pop('translation_service', None)
            with pytest.raises(RuntimeError, match='翻译服务未初始化'):
                require_translation_service()
        if original is not None:
            app.extensions['translation_service'] = original


class TestRequireImageCacheService:
    """require_image_cache_service 异常路径"""

    def test_not_initialized_raises(self, app):
        original = app.extensions.get('image_cache_service')
        with app.app_context():
            app.extensions.pop('image_cache_service', None)
            with pytest.raises(RuntimeError, match='图片缓存服务未初始化'):
                require_image_cache_service()
        if original is not None:
            app.extensions['image_cache_service'] = original


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
            # 同一 IP 应产生稳定哈希
            assert hash_client_ip('1.2.3.4') == digest
            # 不同 IP 应不同
            assert hash_client_ip('5.6.7.8') != digest


class TestRecommendationAndSearchSingletons:
    """RecommendationService/SmartSearchService 单例 helper"""

    def test_recommendation_get_returns_none_when_missing(self, app):
        with app.app_context():
            app.extensions.pop('recommendation_service', None)
            assert get_recommendation_service() is None

    def test_recommendation_get_or_create_creates_when_missing(self, app):
        with app.app_context():
            app.extensions.pop('recommendation_service', None)
            svc = get_or_create_recommendation_service()
            assert svc is not None

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

    def test_smart_search_get_returns_none_when_missing(self, app):
        with app.app_context():
            app.extensions.pop('smart_search_service', None)
            assert get_smart_search_service() is None

    def test_smart_search_get_or_create_creates_when_missing(self, app):
        with app.app_context():
            app.extensions.pop('smart_search_service', None)
            svc = get_or_create_smart_search_service()
            assert svc is not None

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
