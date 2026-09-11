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


class TestImageCachePrefetch:
    """Async prefetch (#178): block=False fast placeholder + dedupe + backfill."""

    @pytest.fixture
    def service(self, tmp_path):
        import threading as _threading

        svc = ImageCacheService.__new__(ImageCacheService)
        svc._default_cover = '/static/default-cover.png'
        svc._memory_cache = OrderedDict()
        svc._memory_cache_ttl = 3600
        svc._memory_cache_max_size = 1000
        svc._cache_dir = tmp_path / 'cache'
        svc._cache_dir.mkdir()
        svc._prefetch_lock = _threading.Lock()
        svc._prefetch_pending = set()
        return svc

    def test_block_false_returns_placeholder_immediately(self, service):
        with (
            patch('app.services.api_utils._is_safe_image_url', return_value=True),
            patch('app.utils.service_helpers.submit_background_task') as mock_submit,
        ):
            result = service.get_cached_image_url('https://cdn.example.com/x.jpg', block=False)
            assert result == '/static/default-cover.png'
            assert mock_submit.called

    def test_prefetch_dedupes_same_url(self, service):
        with (
            patch('app.services.api_utils._is_safe_image_url', return_value=True),
            patch('app.utils.service_helpers.submit_background_task') as mock_submit,
        ):
            service._enqueue_prefetch('https://cdn.example.com/x.jpg')
            service._enqueue_prefetch('https://cdn.example.com/x.jpg')
            assert mock_submit.call_count == 1

    def test_prefetch_worker_download_and_backfills(self, service):
        class Resp:
            def __init__(self):
                self.headers = {'Content-Type': 'image/jpeg'}

            def raise_for_status(self):
                pass

            def iter_content(self, size):
                yield b'fake-jpeg-bytes' * 200

        session = MagicMock()
        session.get.return_value = Resp()
        service._session = session
        with (
            patch('app.services.api_utils._is_safe_image_url', return_value=True),
            patch('app.utils.service_helpers.submit_background_task', side_effect=lambda fn: fn()),
        ):
            result = service.get_cached_image_url('https://cdn.example.com/y.jpg', block=False)
            assert result == '/static/default-cover.png'
            cached = service._memory_cache.get('https://cdn.example.com/y.jpg')
            assert cached is not None
            assert cached[0].startswith('/cache/images/')

    def test_unsafe_url_not_prefetched(self, service):
        with (
            patch('app.services.api_utils._is_safe_image_url', return_value=False),
            patch('app.utils.service_helpers.submit_background_task') as mock_submit,
        ):
            result = service.get_cached_image_url('http://169.254.169.254/meta', block=False)
            assert result == '/static/default-cover.png'
            assert not mock_submit.called

    def test_download_retries_transient_ssl_error(self, service):
        """NYT CDN 偶发 SSL EOF：首次失败、重试成功应回填缓存（#178 follow-up）。"""
        import requests as _requests

        session = MagicMock()
        session.get.side_effect = [
            _requests.exceptions.SSLError('unexpected EOF'),
            _FakeOKResp(),
        ]
        service._session = session
        result = service._download_to_cache('https://static01.nyt.com/fake.jpg')
        assert result.startswith('/cache/images/')
        assert session.get.call_count == 2


class _FakeOKResp:
    def __init__(self):
        self.headers = {'Content-Type': 'image/jpeg'}

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield b'fake-jpeg-bytes' * 200


class _FakeResp:
    """可指定响应体的流式响应替身。"""

    def __init__(self, body: bytes, ctype: str = 'image/jpeg'):
        self.headers = {'Content-Type': ctype}
        self._body = body

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        for i in range(0, len(self._body), size):
            yield self._body[i : i + size]


# Open Library 对无封面 ISBN 的实际响应（从生产缓存文件抓取）：43 字节
# 1×1 GIF89a，却带 Content-Type: image/jpeg 且被我们存成 .jpg
OL_STUB = (
    b'GIF89a\x01\x00\x01\x00\xf0\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x05\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


class TestImageCachePlaceholderGuard:
    """占位图不得作为有效封面入库/被探测为可用。"""

    @pytest.fixture
    def service(self, tmp_path):
        import threading as _threading

        svc = ImageCacheService.__new__(ImageCacheService)
        svc._default_cover = '/static/default-cover.png'
        svc._memory_cache = OrderedDict()
        svc._memory_cache_ttl = 3600
        svc._memory_cache_max_size = 1000
        svc._cache_dir = tmp_path / 'cache'
        svc._cache_dir.mkdir()
        svc._prefetch_lock = _threading.Lock()
        svc._prefetch_pending = set()
        return svc

    def _cache_file(self, service, url):
        import hashlib

        return service._cache_dir / (hashlib.md5(url.encode(), usedforsecurity=False).hexdigest() + '.jpg')

    def test_stub_is_not_written_and_not_retried(self, service):
        url = 'https://covers.openlibrary.org/b/isbn/9780593491930-L.jpg'
        session = MagicMock()
        session.get.return_value = _FakeResp(OL_STUB)
        service._session = session

        with pytest.raises(ValueError, match='placeholder'):
            service._download_to_cache(url)

        assert not self._cache_file(service, url).exists()
        assert session.get.call_count == 1
        assert url not in service._memory_cache

    def test_public_api_degrades_to_default_cover(self, service):
        url = 'https://covers.openlibrary.org/b/isbn/9781555978896-L.jpg'
        service._session = MagicMock()
        service._session.get.return_value = _FakeResp(OL_STUB)

        assert service.get_cached_image_url(url) == '/static/default-cover.png'

    def test_real_image_still_cached(self, service):
        url = 'https://books.google.com/books/content?id=abc'
        body = b'\xff\xd8\xff' + b'x' * 4096
        service._session = MagicMock()
        service._session.get.return_value = _FakeResp(body)

        assert service.get_cached_image_url(url).startswith('/cache/images/')
        assert self._cache_file(service, url).stat().st_size == len(body)

    def test_preexisting_stub_discarded_then_refetched(self, service):
        url = 'https://covers.openlibrary.org/b/isbn/9780802163784-L.jpg'
        path = self._cache_file(service, url)
        path.write_bytes(OL_STUB)
        body = b'\xff\xd8\xff' + b'y' * 4096
        session = MagicMock()
        session.get.return_value = _FakeResp(body)
        service._session = session

        assert service.get_cached_image_url(url).startswith('/cache/images/')
        assert path.stat().st_size == len(body)
        assert session.get.call_count == 1

    def test_non_image_content_type_still_rejected(self, service):
        url = 'https://example.com/not-an-image'
        service._session = MagicMock()
        service._session.get.return_value = _FakeResp(b'<html>' + b'<' * 4096, ctype='text/html')

        assert service.get_cached_image_url(url) == '/static/default-cover.png'

    def test_is_cached_file_present_distinguishes_stub_from_real(self, service):
        stub = service._cache_dir / 'stub.jpg'
        stub.write_bytes(OL_STUB)
        real = service._cache_dir / 'real.jpg'
        real.write_bytes(b'z' * 4096)

        assert service.is_cached_file_present('/cache/images/stub.jpg') is False
        assert service.is_cached_file_present('/cache/images/real.jpg') is True
        assert service.is_cached_file_present('/cache/images/gone.jpg') is False
        assert service.is_cached_file_present('/static/other.png') is True
        assert service.is_cached_file_present('') is False
