"""
缓存服务测试

测试缓存服务的核心功能，包括内存缓存、文件缓存和缓存服务组合
"""
import pytest
import tempfile
import time
from pathlib import Path
from app.services.cache_service import MemoryCache, FileCache, CacheService


class TestCacheService:
    """缓存服务测试类"""
    
    def test_memory_cache_set_get(self):
        """测试内存缓存的设置和获取"""
        # 创建内存缓存实例
        cache = MemoryCache(default_ttl=10, max_size=100)
        
        # 设置缓存
        cache.set('test_key', 'test_value')
        
        # 获取缓存
        value = cache.get('test_key')
        
        # 验证结果
        assert value == 'test_value'
    
    def test_memory_cache_expiry(self):
        """测试内存缓存过期"""
        # 创建内存缓存实例
        cache = MemoryCache(default_ttl=1, max_size=100)
        
        # 设置缓存
        cache.set('test_key', 'test_value')
        
        # 验证缓存存在
        assert cache.get('test_key') == 'test_value'
        
        # 等待过期
        time.sleep(1.1)
        
        # 验证缓存已过期
        assert cache.get('test_key') is None
    
    def test_memory_cache_max_size(self):
        """测试内存缓存最大容量"""
        # 创建内存缓存实例
        cache = MemoryCache(default_ttl=10, max_size=2)
        
        # 设置多个缓存
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        cache.set('key3', 'value3')  # 这应该淘汰最旧的key1
        
        # 验证结果
        assert cache.get('key1') is None  # 应该被淘汰
        assert cache.get('key2') == 'value2'
        assert cache.get('key3') == 'value3'
    
    def test_memory_cache_delete(self):
        """测试内存缓存删除"""
        # 创建内存缓存实例
        cache = MemoryCache(default_ttl=10, max_size=100)
        
        # 设置缓存
        cache.set('test_key', 'test_value')
        assert cache.get('test_key') == 'test_value'
        
        # 删除缓存
        cache.delete('test_key')
        
        # 验证缓存已删除
        assert cache.get('test_key') is None
    
    def test_memory_cache_clear(self):
        """测试内存缓存清空"""
        # 创建内存缓存实例
        cache = MemoryCache(default_ttl=10, max_size=100)
        
        # 设置多个缓存
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        assert cache.get('key1') == 'value1'
        assert cache.get('key2') == 'value2'
        
        # 清空缓存
        cache.clear()
        
        # 验证缓存已清空
        assert cache.get('key1') is None
        assert cache.get('key2') is None
    
    def test_memory_cache_stats(self):
        """测试内存缓存统计信息"""
        # 创建内存缓存实例
        cache = MemoryCache(default_ttl=10, max_size=100)
        
        # 设置缓存
        cache.set('test_key', 'test_value')
        
        # 获取缓存（命中）
        cache.get('test_key')
        
        # 获取不存在的缓存（未命中）
        cache.get('non_existent_key')
        
        # 获取统计信息
        stats = cache.get_stats()
        
        # 验证结果
        assert stats['size'] == 1
        assert stats['max_size'] == 100
        assert stats['hits'] >= 1
        assert stats['misses'] >= 1
        assert 'hit_rate' in stats
    
    def test_file_cache_set_get(self):
        """测试文件缓存的设置和获取"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建文件缓存实例
            cache_dir = Path(temp_dir)
            cache = FileCache(cache_dir=cache_dir, default_ttl=10)
            
            # 设置缓存
            cache.set('test_key', 'test_value')
            
            # 获取缓存
            value = cache.get('test_key')
            
            # 验证结果
            assert value == 'test_value'
    
    def test_file_cache_expiry(self):
        """测试文件缓存过期"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建文件缓存实例
            cache_dir = Path(temp_dir)
            cache = FileCache(cache_dir=cache_dir, default_ttl=1)
            
            # 设置缓存
            cache.set('test_key', 'test_value')
            
            # 验证缓存存在
            assert cache.get('test_key') == 'test_value'
            
            # 等待过期
            time.sleep(1.1)
            
            # 验证缓存已过期
            assert cache.get('test_key') is None
    
    def test_file_cache_delete(self):
        """测试文件缓存删除"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建文件缓存实例
            cache_dir = Path(temp_dir)
            cache = FileCache(cache_dir=cache_dir, default_ttl=10)
            
            # 设置缓存
            cache.set('test_key', 'test_value')
            assert cache.get('test_key') == 'test_value'
            
            # 删除缓存
            cache.delete('test_key')
            
            # 验证缓存已删除
            assert cache.get('test_key') is None
    
    def test_file_cache_clear(self):
        """测试文件缓存清空"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建文件缓存实例
            cache_dir = Path(temp_dir)
            cache = FileCache(cache_dir=cache_dir, default_ttl=10)
            
            # 设置多个缓存
            cache.set('key1', 'value1')
            cache.set('key2', 'value2')
            assert cache.get('key1') == 'value1'
            assert cache.get('key2') == 'value2'
            
            # 清空缓存
            cache.clear()
            
            # 验证缓存已清空
            assert cache.get('key1') is None
            assert cache.get('key2') is None
    
    def test_cache_service_set_get(self):
        """测试缓存服务的设置和获取"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建缓存服务实例
            memory_cache = MemoryCache(default_ttl=10, max_size=100)
            file_cache = FileCache(cache_dir=Path(temp_dir), default_ttl=10)
            cache_service = CacheService(memory_cache, file_cache)
            
            # 设置缓存
            cache_service.set('test_key', 'test_value')
            
            # 获取缓存
            value = cache_service.get('test_key')
            
            # 验证结果
            assert value == 'test_value'
    
    def test_cache_service_delete(self):
        """测试缓存服务删除"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建缓存服务实例
            memory_cache = MemoryCache(default_ttl=10, max_size=100)
            file_cache = FileCache(cache_dir=Path(temp_dir), default_ttl=10)
            cache_service = CacheService(memory_cache, file_cache)
            
            # 设置缓存
            cache_service.set('test_key', 'test_value')
            assert cache_service.get('test_key') == 'test_value'
            
            # 删除缓存
            cache_service.delete('test_key')
            
            # 验证缓存已删除
            assert cache_service.get('test_key') is None
    
    def test_cache_service_clear(self):
        """测试缓存服务清空"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建缓存服务实例
            memory_cache = MemoryCache(default_ttl=10, max_size=100)
            file_cache = FileCache(cache_dir=Path(temp_dir), default_ttl=10)
            cache_service = CacheService(memory_cache, file_cache)
            
            # 设置多个缓存
            cache_service.set('key1', 'value1')
            cache_service.set('key2', 'value2')
            assert cache_service.get('key1') == 'value1'
            assert cache_service.get('key2') == 'value2'
            
            # 清空缓存
            cache_service.clear()
            
            # 验证缓存已清空
            assert cache_service.get('key1') is None
            assert cache_service.get('key2') is None
    
    def test_cache_service_get_cache_time(self):
        """测试缓存服务获取缓存时间"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建缓存服务实例
            memory_cache = MemoryCache(default_ttl=10, max_size=100)
            file_cache = FileCache(cache_dir=Path(temp_dir), default_ttl=10)
            cache_service = CacheService(memory_cache, file_cache)
            
            # 设置缓存
            cache_service.set('test_key', 'test_value')
            
            # 获取缓存时间
            cache_time = cache_service.get_cache_time('test_key')
            
            # 验证结果
            assert cache_time is not None
            assert isinstance(cache_time, str)
    
    def test_cache_service_get_stats(self):
        """测试缓存服务获取统计信息"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建缓存服务实例
            memory_cache = MemoryCache(default_ttl=10, max_size=100)
            file_cache = FileCache(cache_dir=Path(temp_dir), default_ttl=10)
            cache_service = CacheService(memory_cache, file_cache)
            
            # 获取统计信息
            stats = cache_service.get_stats()
            
            # 验证结果
            assert isinstance(stats, dict)
            assert 'memory' in stats
            assert isinstance(stats['memory'], dict)