"""Image misses share downloads and publish only complete files."""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Barrier, Event
from unittest.mock import Mock

import pytest
import requests

from app.services.api_utils import ImageCacheService

URL = 'https://books.google.com/books/content?id=shared-cover'
IMAGE = b'\xff\xd8\xff' + b'x' * 16384


def _path(cache_dir):
    return cache_dir / (hashlib.md5(URL.encode(), usedforsecurity=False).hexdigest() + '.jpg')


def _response(chunks=None):
    response = Mock()
    response.headers = {'Content-Type': 'image/jpeg'}
    response.iter_content.side_effect = lambda size: iter(chunks or [IMAGE])
    return response


def test_concurrent_missing_memory_files_can_both_recover(tmp_path, monkeypatch):
    service = ImageCacheService(tmp_path)
    service._update_memory_cache(URL, '/cache/images/deleted.jpg', time.time())
    observed = Barrier(2)

    def missing_file(path):
        observed.wait(5)
        return False

    monkeypatch.setattr(service, 'is_cached_file_present', missing_file)
    monkeypatch.setattr(service, '_download_to_cache', Mock(return_value='/downloaded'))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.get_cached_image_url, URL) for _ in range(2)]
        assert [future.result(5) for future in futures] == ['/downloaded', '/downloaded']


@pytest.mark.parametrize('failed', [False, True])
def test_concurrent_sync_misses_share_success_or_failure(tmp_path, monkeypatch, failed):
    service = ImageCacheService(tmp_path)
    started, release = Event(), Event()
    ready = Barrier(5)
    responses = []
    monkeypatch.setattr('app.services.api_utils.time.sleep', lambda seconds: None)

    def fetch(*args, **kwargs):
        started.set()
        assert release.wait(5)
        response = _response()
        if failed:
            response.iter_content.side_effect = requests.ConnectionError('interrupted stream')
        responses.append(response)
        return response

    monkeypatch.setattr(service._session, 'get', Mock(side_effect=fetch))

    def read():
        ready.wait(5)
        return service.get_cached_image_url(URL)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(read) for _ in range(4)]
        try:
            ready.wait(5)
            assert started.wait(5)
            assert not wait(futures, timeout=0.05).done
        finally:
            release.set()
        results = [future.result(5) for future in futures]

    assert len(responses) == (3 if failed else 1)
    assert len(set(results)) == 1
    for response in responses:
        response.close.assert_called_once()
    if failed:
        assert results[0] == '/static/default-cover.png'
        assert list(tmp_path.iterdir()) == []
        recovered = _response()
        monkeypatch.setattr(service._session, 'get', Mock(return_value=recovered))
        assert service.get_cached_image_url(URL).startswith('/cache/images/')
        service._session.get.assert_called_once()
    else:
        assert _path(tmp_path).read_bytes() == IMAGE


def test_async_and_sync_misses_share_the_same_download(tmp_path, monkeypatch):
    service = ImageCacheService(tmp_path)
    started, release = Event(), Event()
    response = _response()

    def fetch(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return response

    monkeypatch.setattr(service._session, 'get', Mock(side_effect=fetch))
    with ThreadPoolExecutor(max_workers=2) as pool:
        background = []
        monkeypatch.setattr(
            'app.utils.service_helpers.submit_background_task', lambda fn: background.append(pool.submit(fn))
        )
        assert service.get_cached_image_url(URL, block=False) == '/static/default-cover.png'
        try:
            assert started.wait(5)
            foreground = pool.submit(service.get_cached_image_url, URL)
            assert not wait([foreground], timeout=0.05).done
        finally:
            release.set()
        assert foreground.result(5).startswith('/cache/images/')
        background[0].result(5)

    service._session.get.assert_called_once()
    response.close.assert_called_once()
    assert service._prefetch_pending == set()


@pytest.mark.parametrize('existing', [False, True])
def test_download_exposes_complete_file_only_and_preserves_old_file(tmp_path, monkeypatch, existing):
    service = ImageCacheService(tmp_path)
    target = _path(tmp_path)
    if existing:
        target.write_bytes(b'old complete image' * 100)
    previous = target.read_bytes() if existing else None
    started, release = Event(), Event()
    response = _response()

    def chunks(size):
        yield IMAGE
        started.set()
        assert release.wait(5)
        yield b'ending'

    response.iter_content.side_effect = chunks
    monkeypatch.setattr(service._session, 'get', Mock(return_value=response))
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(service._download_to_cache, URL, ttl=0)
        try:
            assert started.wait(5)
            assert (target.read_bytes() if target.exists() else None) == previous
        finally:
            release.set()
        assert result.result(5).startswith('/cache/images/')

    assert target.read_bytes() == IMAGE + b'ending'
    assert list(tmp_path.iterdir()) == [target]
    response.close.assert_called_once()


@pytest.mark.parametrize('existing', [False, True])
def test_failed_stream_cleans_temporary_data_and_keeps_previous_snapshot(tmp_path, monkeypatch, existing):
    service = ImageCacheService(tmp_path)
    target = _path(tmp_path)
    previous = b'old complete image' * 100
    if existing:
        target.write_bytes(previous)
    response = _response()

    def chunks(size):
        yield IMAGE
        raise requests.ConnectionError('interrupted stream')

    response.iter_content.side_effect = chunks
    monkeypatch.setattr(service._session, 'get', Mock(return_value=response))
    monkeypatch.setattr('app.services.api_utils.time.sleep', lambda seconds: None)

    with pytest.raises(requests.ConnectionError):
        service._download_to_cache(URL, ttl=0)

    assert list(tmp_path.iterdir()) == ([target] if existing else [])
    if existing:
        assert target.read_bytes() == previous
    assert response.close.call_count == 3
