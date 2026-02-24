import json
import time
import logging
import hashlib
from pathlib import Path
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class CacheStrategy(ABC):
    """缓存策略抽象基类"""
    
    @abstractmethod
    def get(self, key: str) -> any:
        pass
    
    @abstractmethod
    def set(self, key: str, value: any, ttl: int = 300) -> None:
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        pass
    
    @abstractmethod
    def clear(self) -> None:
        pass


class MemoryCache(CacheStrategy):
    """内存缓存实现"""
    
    def __init__(self, default_ttl: int = 300):
        self._cache: dict[str, tuple] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> any:
        if key not in self._cache:
            return None
        
        expiry_time, value = self._cache[key]
        if time.time() > expiry_time:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: any, ttl: int = None) -> None:
        ttl = ttl or self._default_ttl
        expiry_time = time.time() + ttl
        self._cache[key] = (expiry_time, value)
    
    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def clear(self) -> None:
        self._cache.clear()


class FileCache(CacheStrategy):
    """文件缓存实现"""
    
    def __init__(self, cache_dir: Path, default_ttl: int = 3600):
        self._cache_dir = cache_dir
        self._default_ttl = default_ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> Path:
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{safe_key}.json"
    
    def get(self, key: str) -> any:
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
    
    def set(self, key: str, value: any, ttl: int = None) -> None:
        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
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
    
    def get(self, key: str) -> any:
        value = self._memory.get(key)
        if value is not None:
            logger.debug(f"Memory cache hit: {key}")
            return value
        
        if self._flask_cache:
            value = self._flask_cache.get(key)
            if value is not None:
                logger.debug(f"Flask cache hit: {key}")
                self._memory.set(key, value)
                return value
        
        value = self._file.get(key)
        if value is not None:
            logger.debug(f"File cache hit: {key}")
            self._memory.set(key, value)
            return value
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(self, key: str, value: any, ttl: int = None) -> None:
        self._memory.set(key, value, ttl)
        
        if self._flask_cache:
            self._flask_cache.set(key, value, timeout=ttl)
        
        self._file.set(key, value, ttl)
        
        logger.debug(f"Cache set: {key}")
    
    def delete(self, key: str) -> None:
        self._memory.delete(key)
        if self._flask_cache:
            self._flask_cache.delete(key)
        self._file.delete(key)
        logger.debug(f"Cache deleted: {key}")
    
    def clear(self) -> None:
        self._memory.clear()
        if self._flask_cache:
            self._flask_cache.clear()
        self._file.clear()
        logger.info("All caches cleared")
    
    def get_cache_time(self, key: str) -> str | None:
        cache_path = self._file._get_cache_path(key)
        if not cache_path.exists():
            return None
        
        from datetime import datetime
        try:
            mtime = cache_path.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            return None
