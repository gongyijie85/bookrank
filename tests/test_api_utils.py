"""API 工具函数测试"""

import time
from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.api_utils import ImageCacheService, _safe_cache_set, create_session_with_retry


class TestCreateSessionWithRetry:
    """测试 create_session_with_retry"""

    def test_returns_session(self):
        session = create_session_with_retry()
        assert session is not None
        assert 'User-Agent' in session.headers

    def test_custom_retries(self):
        session = create_session_with_retry(max_retries=5, backoff_factor=1.0)
        assert session is not None

    def test_session_has_adapters(self):
        session = create_session_with_retry()
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters


class TestSafeCacheSet:
    """测试 _safe_cache_set"""

    def test_none_cache_service(self):
        _safe_cache_set(None, 'ns', 'key', 'data')

    def test_successful_set(self):
        mock_cache = MagicMock()
        _safe_cache_set(mock_cache, 'ns', 'key', {'data': 1}, ttl_seconds=300)
        mock_cache.set.assert_called_once()

    def test_failed_set(self):
        mock_cache = MagicMock()
        mock_cache.set.side_effect = Exception('DB error')
        _safe_cache_set(mock_cache, 'ns', 'key', 'data')

    def test_error_cache(self):
        mock_cache = MagicMock()
        _safe_cache_set(mock_cache, 'ns', 'key', 'error', is_error=True, error_message='fail')
        mock_cache.set.assert_called_once_with(
            'ns', 'key', 'error', ttl_seconds=300, is_error=True, error_message='fail'
        )


class TestImageCacheService:
    """测试 ImageCacheService"""

    @pytest.fixture
    def cache_dir(self, tmp_path):
        return tmp_path / 'image_cache'

    @pytest.fixture
    def image_service(self, cache_dir):
        return ImageCacheService(cache_dir)

    def test_init_creates_dir(self, cache_dir):
        ImageCacheService(cache_dir)
        assert cache_dir.exists()

    def test_get_cached_image_url_empty(self, image_service):
        result = image_service.get_cached_image_url('')
        assert result == '/static/default-cover.png'

    def test_get_cached_image_url_none(self, image_service):
        result = image_service.get_cached_image_url(None)
        assert result == '/static/default-cover.png'

    @patch.object(ImageCacheService, '__init__', lambda self, *a, **kw: None)
    def test_memory_cache_hit(self):
        service = ImageCacheService.__new__(ImageCacheService)
        service._default_cover = '/static/default-cover.png'
        service._memory_cache = OrderedDict()
        service._memory_cache_ttl = 3600
        service._memory_cache_max_size = 1000
        service._cache_dir = Path('/tmp/test_cache')

        current_time = time.time()
        service._memory_cache['http://example.com/cover.jpg'] = ('/cache/images/test.jpg', current_time)

        result = service.get_cached_image_url('http://example.com/cover.jpg')
        assert result == '/cache/images/test.jpg'

    @patch.object(ImageCacheService, '__init__', lambda self, *a, **kw: None)
    def test_memory_cache_expired(self):
        service = ImageCacheService.__new__(ImageCacheService)
        service._default_cover = '/static/default-cover.png'
        service._memory_cache = OrderedDict()
        service._memory_cache_ttl = 1
        service._memory_cache_max_size = 1000
        service._cache_dir = Path('/nonexistent/path')
        service._session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception('Network error')
        service._session.get.return_value = mock_response

        old_time = time.time() - 100
        service._memory_cache['http://example.com/old.jpg'] = ('/cache/images/old.jpg', old_time)

        result = service.get_cached_image_url('http://example.com/old.jpg')
        assert result == '/static/default-cover.png'

    def test_update_memory_cache(self, image_service):
        image_service._update_memory_cache('key1', 'value1', time.time())
        assert 'key1' in image_service._memory_cache

    def test_update_memory_cache_evicts_old(self, image_service):
        image_service._memory_cache_max_size = 2
        image_service._update_memory_cache('k1', 'v1', time.time())
        image_service._update_memory_cache('k2', 'v2', time.time())
        image_service._update_memory_cache('k3', 'v3', time.time())
        assert len(image_service._memory_cache) <= 2
