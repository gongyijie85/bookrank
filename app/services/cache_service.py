import json
import time
import logging
import hashlib
from pathlib import Path
from abc import ABC, abstractmethod
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class CacheStrategy(ABC):
    """缓存策略抽象基类"""

    @abstractmethod
    def get(self, key: str) -> Any:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class MemoryCache(CacheStrategy):
    """内存缓存实现 - 带容量限制和 LRU 淘汰"""

    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            expiry_time, value = self._cache[key]
            if time.time() > expiry_time:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        with self._lock:
            # 如果缓存已满，删除最旧的条目
            if len(self._cache) >= self._max_size:
                self._evict_oldest()

            ttl = ttl or self._default_ttl
            expiry_time = time.time() + ttl
            self._cache[key] = (expiry_time, value)

    def _evict_oldest(self) -> None:
        """淘汰最旧的缓存条目"""
        if not self._cache:
            return

        # 找到最早过期的条目并删除
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
        del self._cache[oldest_key]

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2)
            }


class FileCache(CacheStrategy):
    """文件缓存实现 - 优化版本"""

    def __init__(self, cache_dir: Path, default_ttl: int = 3600):
        self._cache_dir = cache_dir
        self._default_ttl = default_ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Any:
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            file_age = time.time() - cache_path.stat().st_mtime
            if file_age > self._default_ttl:
                cache_path.unlink()
                return None

            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read cache file {cache_path}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        cache_path = self._get_cache_path(key)
        ttl = ttl or self._default_ttl

        try:
            # 先写入临时文件，再重命名（原子操作）
            tmp_path = cache_path.with_suffix('.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
            tmp_path.replace(cache_path)
        except IOError as e:
            logger.warning(f"Failed to write cache file {cache_path}: {e}")

    def delete(self, key: str) -> None:
        cache_path = self._get_cache_path(key)
        try:
            if cache_path.exists():
                cache_path.unlink()
        except IOError as e:
            logger.warning(f"Failed to delete cache file {cache_path}: {e}")

    def clear(self) -> None:
        for cache_file in self._cache_dir.glob('*.json'):
            try:
                cache_file.unlink()
            except IOError as e:
                logger.warning(f"Failed to delete cache file {cache_file}: {e}")


class CacheService:
    """缓存服务 - 组合多种缓存策略"""

    def __init__(self, memory_cache: MemoryCache, file_cache: FileCache, flask_cache = None):
        self._memory = memory_cache
        self._file = file_cache
        self._flask_cache = flask_cache

    def get(self, key: str) -> Any:
        """获取缓存（多层缓存：内存 -> Flask -> 文件）"""
        # 1. 尝试从内存缓存获取
        value = self._memory.get(key)
        if value is not None:
            logger.debug(f"Memory cache hit: {key}")
            return value

        # 2. 尝试从 Flask 缓存获取
        if self._flask_cache:
            try:
                value = self._flask_cache.get(key)
                if value is not None:
                    logger.debug(f"Flask cache hit: {key}")
                    # 同步到内存缓存
                    self._memory.set(key, value)
                    return value
            except Exception as e:
                logger.warning(f"Flask cache error: {e}")

        # 3. 尝试从文件缓存获取
        value = self._file.get(key)
        if value is not None:
            logger.debug(f"File cache hit: {key}")
            # 同步到内存缓存
            self._memory.set(key, value)
            return value

        logger.debug(f"Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存（同时写入多层缓存）"""
        self._memory.set(key, value, ttl)

        if self._flask_cache:
            try:
                self._flask_cache.set(key, value, timeout=ttl)
            except Exception as e:
                logger.warning(f"Flask cache set error: {e}")

        self._file.set(key, value, ttl)

        logger.debug(f"Cache set: {key}")

    def delete(self, key: str) -> None:
        """删除缓存"""
        self._memory.delete(key)
        if self._flask_cache:
            try:
                self._flask_cache.delete(key)
            except Exception as e:
                logger.warning(f"Flask cache delete error: {e}")
        self._file.delete(key)
        logger.debug(f"Cache deleted: {key}")

    def clear(self) -> None:
        """清空所有缓存"""
        self._memory.clear()
        if self._flask_cache:
            try:
                self._flask_cache.clear()
            except Exception as e:
                logger.warning(f"Flask cache clear error: {e}")
        self._file.clear()
        logger.info("All caches cleared")

    def get_cache_time(self, key: str) -> str | None:
        """获取缓存时间"""
        cache_path = self._file._get_cache_path(key)
        if not cache_path.exists():
            return None

        from datetime import datetime
        try:
            mtime = cache_path.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            return None

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            'memory': self._memory.get_stats()
        }
