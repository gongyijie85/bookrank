"""Layer promotion must not extend freshness or collide on temporary writes."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from app.services.cache_service import CacheService, FileCache, MemoryCache


def test_zero_ttl_does_not_fall_back_to_default(monkeypatch):
    monkeypatch.setattr('app.services.cache_service.time.time', lambda: 100.0)
    cache = MemoryCache(default_ttl=300)
    cache.set('key', 'value', ttl=0)
    assert cache.get('key') is None


def test_file_promotion_preserves_remaining_ttl(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('app.services.cache_service.time.time', lambda: now[0])
    memory = MemoryCache(default_ttl=300)
    files = FileCache(tmp_path)
    files.set('key', 'value', ttl=10)
    cache = CacheService(memory, files)
    now[0] = 109.0
    assert cache.get('key') == 'value'
    now[0] = 110.0
    assert cache.get('key') is None
    assert cache.get_stale('key') == 'value'


def test_concurrent_file_writes_use_distinct_temporary_paths(tmp_path, monkeypatch):
    cache = FileCache(tmp_path)
    ready = Barrier(4)
    paths = []
    replace = Path.replace

    def synchronized_replace(path, destination):
        paths.append(path)
        ready.wait(5)
        return replace(path, destination)

    monkeypatch.setattr(Path, 'replace', synchronized_replace)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda value: cache.set('key', {'value': value}), range(4)))

    assert len(set(paths)) == 4
    assert cache.get('key') in [{'value': value} for value in range(4)]
    assert sorted(tmp_path.iterdir()) == [cache.get_cache_path('key')]
