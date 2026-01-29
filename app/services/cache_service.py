import json
import time
import logging
import hashlib
from pathlib import Path
from typing import Optional, Any, Dict
from abc import ABC, abstractmethod

from flask_caching import Cache

logger = logging.getLogger(__name__)


class CacheStrategy(ABC):
    """缓存策略抽象基类"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """设置缓存值"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        """删除缓存值"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空缓存"""
        pass


class MemoryCache(CacheStrategy):
    """内存缓存实现"""
    
    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, tuple] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        
        expiry_time, value = self._cache[key]
        if time.time() > expiry_time:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any, ttl: int = None) -> None:
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
        """获取缓存文件路径"""
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{safe_key}.json"
    
    def get(self, key: str) -> Optional[Any]:
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
    
    def __init__(self, memory_cache: MemoryCache, file_cache: FileCache, flask_cache: Cache = None):
        self._memory = memory_cache
        self._file = file_cache
        self._flask_cache = flask_cache
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值（按优先级：内存 -> Flask缓存 -> 文件）
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或None
        """
        # 1. 尝试从内存缓存获取
        value = self._memory.get(key)
        if value is not None:
            logger.debug(f"Memory cache hit: {key}")
            return value
        
        # 2. 尝试从Flask缓存获取
        if self._flask_cache:
            value = self._flask_cache.get(key)
            if value is not None:
                logger.debug(f"Flask cache hit: {key}")
                # 回填内存缓存
                self._memory.set(key, value)
                return value
        
        # 3. 尝试从文件缓存获取
        value = self._file.get(key)
        if value is not None:
            logger.debug(f"File cache hit: {key}")
            # 回填内存缓存
            self._memory.set(key, value)
            return value
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """
        设置缓存值（写入所有缓存层）
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
        """
        # 写入内存缓存
        self._memory.set(key, value, ttl)
        
        # 写入Flask缓存
        if self._flask_cache:
            self._flask_cache.set(key, value, timeout=ttl)
        
        # 写入文件缓存
        self._file.set(key, value, ttl)
        
        logger.debug(f"Cache set: {key}")
    
    def delete(self, key: str) -> None:
        """删除缓存值"""
        self._memory.delete(key)
        if self._flask_cache:
            self._flask_cache.delete(key)
        self._file.delete(key)
        logger.debug(f"Cache deleted: {key}")
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._memory.clear()
        if self._flask_cache:
            self._flask_cache.clear()
        self._file.clear()
        logger.info("All caches cleared")
    
    def get_cache_time(self, key: str) -> Optional[str]:
        """获取缓存文件修改时间"""
        cache_path = self._file._get_cache_path(key)
        if not cache_path.exists():
            return None
        
        from datetime import datetime
        try:
            mtime = cache_path.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            return None
