import time
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Barrier, Event, Lock
from unittest.mock import Mock

import pytest

from app.services.detail_cache import DetailCache


def test_cached_values_are_copied_on_load_and_each_read():
    cache = DetailCache()
    source = {'recommendations': [{'id': 'book-2'}]}
    calls = []

    def load():
        calls.append('load')
        return source

    first = cache.get_or_load(('book', 'book-1'), load)
    first['recommendations'][0]['id'] = 'changed-first'
    source['recommendations'][0]['id'] = 'changed-source'
    second = cache.get_or_load(('book', 'book-1'), load)
    second['recommendations'].clear()

    assert cache.get_or_load(('book', 'book-1'), load) == {'recommendations': [{'id': 'book-2'}]}
    assert calls == ['load']


@pytest.mark.parametrize(('value', 'expected_calls'), [(None, 2), ([], 1), ({}, 1)])
def test_only_missing_values_skip_cache(value, expected_calls):
    cache = DetailCache()
    loader = Mock(return_value=value)

    assert cache.get_or_load(('book', 'book-1'), loader) == value
    assert cache.get_or_load(('book', 'book-1'), loader) == value
    assert loader.call_count == expected_calls


def test_ttl_uses_monotonic_time_and_expires_at_boundary(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    cache = DetailCache(ttl=10)
    loader = Mock(side_effect=[{'title': 'old'}, {'title': 'new'}])

    assert cache.get_or_load(('book', 'book-1'), loader) == {'title': 'old'}
    now[0] = 109
    assert cache.get_or_load(('book', 'book-1'), loader) == {'title': 'old'}
    now[0] = 110
    assert cache.get_or_load(('book', 'book-1'), loader) == {'title': 'new'}
    assert loader.call_count == 2


def test_capacity_evicts_least_recently_used_entry():
    cache = DetailCache(max_size=2)
    loaders = {key: Mock(return_value={'id': key}) for key in ('book-1', 'book-2', 'book-3')}

    for key in ('book-1', 'book-2', 'book-1', 'book-3', 'book-1', 'book-2'):
        assert cache.get_or_load(('book', key), loaders[key]) == {'id': key}

    assert loaders['book-1'].call_count == 1
    assert loaders['book-2'].call_count == 2
    assert loaders['book-3'].call_count == 1


def test_invalidate_value_only_removes_matching_stored_value():
    cache = DetailCache()
    key = ('award-cover', 1)
    load = Mock(return_value='current')
    assert cache.get_or_load(key, load) == 'current'
    assert cache.invalidate_value(key, 'old') is False
    assert cache.get_or_load(key, load) == 'current'
    load.assert_called_once()
    assert cache.invalidate_value(key, 'current') is True
    assert cache.get_or_load(key, lambda: 'replacement') == 'replacement'


def test_invalidate_value_checks_optional_condition_only_after_value_matches():
    cache = DetailCache()
    key = ('award-cover', 1)
    cache.get_or_load(key, lambda: 'current')
    still_invalid = Mock(return_value=False)
    assert cache.invalidate_value(key, 'old', still_invalid) is False
    still_invalid.assert_not_called()
    assert cache.invalidate_value(key, 'current', still_invalid) is False
    assert cache.get_or_load(key, lambda: 'unexpected') == 'current'
    still_invalid.return_value = True
    assert cache.invalidate_value(key, 'current', still_invalid) is True
    assert cache.get_or_load(key, lambda: 'replacement') == 'replacement'


def test_old_value_observer_cannot_detach_replacement_flight():
    cache = DetailCache()
    key = ('award-cover', 1)
    assert cache.get_or_load(key, lambda: 'deleted-file') == 'deleted-file'
    assert cache.invalidate_value(key, 'deleted-file') is True
    started, release = Event(), Event()
    redundant_load = Mock(return_value='unexpected duplicate')

    def replacement():
        started.set()
        assert release.wait(5)
        return 'recovered-file'

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(cache.get_or_load, key, replacement)
        try:
            assert started.wait(5)
            # 另一请求已看见旧 URL，直到新回源开始后才报告文件已删除。
            assert cache.invalidate_value(key, 'deleted-file') is False
            follower = pool.submit(cache.get_or_load, key, redundant_load)
        finally:
            release.set()
        assert owner.result(timeout=5) == 'recovered-file'
        assert follower.result(timeout=5) == 'recovered-file'
    redundant_load.assert_not_called()
    assert cache.get_or_load(key, redundant_load) == 'recovered-file'


def test_same_key_loads_once_under_concurrent_requests():
    cache = DetailCache()
    start = Barrier(9)
    loading = Event()
    release = Event()
    calls = []
    calls_lock = Lock()

    def load():
        with calls_lock:
            calls.append('load')
        loading.set()
        assert release.wait(5)
        return {'recommendations': []}

    def request():
        start.wait(5)
        return cache.get_or_load(('book', 'book-1'), load)

    with ThreadPoolExecutor(max_workers=8) as executor:
        requests = [executor.submit(request) for _ in range(8)]
        try:
            start.wait(5)
            assert loading.wait(5)
            assert not wait(requests, timeout=0.05).done
        finally:
            release.set()
        results = [request.result(5) for request in requests]

    assert calls == ['load']
    results[0]['recommendations'].append('changed')
    assert results[1:] == [{'recommendations': []}] * 7


def test_clear_removes_all_cached_keys():
    cache = DetailCache()
    first = Mock(return_value={'id': 'book-1'})
    second = Mock(return_value={'id': 'book-2'})
    cache.get_or_load(('book', 'book-1'), first)
    cache.get_or_load(('book', 'book-2'), second)

    cache.clear()

    cache.get_or_load(('book', 'book-1'), first)
    cache.get_or_load(('book', 'book-2'), second)
    assert first.call_count == second.call_count == 2


def test_invalidate_removes_only_matching_keys():
    cache = DetailCache()
    keys = [('book', 'book-1', 'en'), ('recommendations', 'book-1', 'en'), ('book', 'book-2', 'en')]
    loaders = {key: Mock(return_value={'id': key[1]}) for key in keys}
    for key in keys:
        cache.get_or_load(key, loaders[key])

    cache.invalidate(lambda key: key[1] == 'book-1')

    for key in keys:
        cache.get_or_load(key, loaders[key])
    assert [loaders[key].call_count for key in keys] == [2, 2, 1]


@pytest.mark.parametrize('operation', ['invalidate', 'clear'])
@pytest.mark.parametrize('finish_order', ['old-first', 'old-last'])
def test_invalidation_detaches_running_load_and_prevents_stale_repopulation(operation, finish_order):
    cache = DetailCache()
    old_loading = Event()
    new_loading = Event()
    release_old = Event()
    release_new = Event()
    key = ('book', 'book-1')

    def load_old():
        old_loading.set()
        assert release_old.wait(5)
        return {'title': 'old'}

    def load_new():
        new_loading.set()
        assert release_new.wait(5)
        return {'title': 'new'}

    with ThreadPoolExecutor(max_workers=2) as executor:
        old_request = executor.submit(cache.get_or_load, key, load_old)
        try:
            assert old_loading.wait(5)
            if operation == 'invalidate':
                cache.invalidate(lambda candidate: candidate == key)
            else:
                cache.clear()
            new_request = executor.submit(cache.get_or_load, key, load_new)
            assert new_loading.wait(1)

            if finish_order == 'old-first':
                release_old.set()
                assert old_request.result(5) == {'title': 'old'}
                release_new.set()
                assert new_request.result(5) == {'title': 'new'}
            else:
                release_new.set()
                assert new_request.result(5) == {'title': 'new'}
                release_old.set()
                assert old_request.result(5) == {'title': 'old'}
        finally:
            release_old.set()
            release_new.set()

    unexpected_loader = Mock(return_value={'title': 'unexpected'})
    assert cache.get_or_load(key, unexpected_loader) == {'title': 'new'}
    unexpected_loader.assert_not_called()


def test_different_keys_load_in_parallel():
    cache = DetailCache()
    first_loading = Event()
    release_first = Event()

    def load_first():
        first_loading.set()
        assert release_first.wait(5)
        return {'id': 'book-1'}

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(cache.get_or_load, ('book', 'book-1'), load_first)
        try:
            assert first_loading.wait(5)
            second = executor.submit(cache.get_or_load, ('book', 'book-2'), lambda: {'id': 'book-2'})
            assert second.result(1) == {'id': 'book-2'}
        finally:
            release_first.set()
        assert first.result(5) == {'id': 'book-1'}


@pytest.mark.parametrize('exception_type', [RuntimeError, KeyboardInterrupt])
def test_loader_errors_reach_all_waiters_and_allow_retry(exception_type):
    cache = DetailCache()
    error = exception_type('load failed')
    start = Barrier(9)
    loading = Event()
    release = Event()
    calls = []
    calls_lock = Lock()

    def fail():
        with calls_lock:
            calls.append('load')
        loading.set()
        assert release.wait(5)
        raise error

    def request():
        start.wait(5)
        return cache.get_or_load(('book', 'book-1'), fail)

    with ThreadPoolExecutor(max_workers=8) as executor:
        requests = [executor.submit(request) for _ in range(8)]
        try:
            start.wait(5)
            assert loading.wait(5)
            assert not wait(requests, timeout=0.05).done
        finally:
            release.set()
        for request in requests:
            with pytest.raises(exception_type) as raised:
                request.result(5)
            assert raised.value is error

    assert calls == ['load']
    recover = Mock(return_value={'title': 'recovered'})
    assert cache.get_or_load(('book', 'book-1'), recover) == {'title': 'recovered'}
    assert cache.get_or_load(('book', 'book-1'), recover) == {'title': 'recovered'}
    recover.assert_called_once_with()


def test_existing_waiters_receive_detached_load_without_polluting_fresh_cache():
    cache = DetailCache()
    loading = Event()
    release = Event()
    key = ('book', 'book-1')

    def load_old():
        loading.set()
        assert release.wait(5)
        return {'title': 'old'}

    with ThreadPoolExecutor(max_workers=2) as executor:
        old_request = executor.submit(cache.get_or_load, key, load_old)
        try:
            assert loading.wait(5)
            waiter = executor.submit(cache.get_or_load, key, lambda: {'title': 'unexpected'})
            assert not wait([waiter], timeout=0.05).done
            cache.invalidate(lambda candidate: candidate == key)
            assert cache.get_or_load(key, lambda: {'title': 'new'}) == {'title': 'new'}
        finally:
            release.set()
        assert old_request.result(5) == {'title': 'old'}
        assert waiter.result(5) == {'title': 'old'}

    assert cache.get_or_load(key, lambda: {'title': 'unexpected'}) == {'title': 'new'}


def test_zero_ttl_disables_cache_reuse():
    cache = DetailCache(ttl=0)
    loader = Mock(side_effect=[{'title': 'old'}, {'title': 'new'}])

    assert cache.get_or_load(('book', 'book-1'), loader) == {'title': 'old'}
    assert cache.get_or_load(('book', 'book-1'), loader) == {'title': 'new'}
    assert loader.call_count == 2
