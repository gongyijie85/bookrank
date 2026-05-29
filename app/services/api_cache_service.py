"""
API缓存服务 - 为外部API调用提供数据库持久化缓存
"""

import hashlib
import json
import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from sqlalchemy import func

from ..models.database import db
from ..models.schemas import APICache
from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)

# 内存 LRU 缓存最大条目数
_MEMORY_CACHE_MAX = 256


class APICacheService:
    """API缓存服务类（含内存 LRU 写通缓存层）"""

    DEFAULT_TTL = {
        'nyt': 86400 * 7,
        'google_books': 86400,
        'open_library': 86400 * 3,
        'wikidata': 86400 * 7,
    }

    def __init__(self) -> None:
        self._mem_cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._mem_lock = Lock()

    def _mem_get(self, cache_key: str) -> Any | None:
        """从内存 LRU 读取（命中则移到末尾）"""
        with self._mem_lock:
            entry = self._mem_cache.get(cache_key)
            if entry is None:
                return None
            data, expires_at = entry
            if datetime.now(UTC).timestamp() > expires_at:
                self._mem_cache.pop(cache_key, None)
                return None
            self._mem_cache.move_to_end(cache_key)
            return data

    def _mem_set(self, cache_key: str, data: Any, ttl_seconds: int) -> None:
        """写入内存 LRU（超出上限时淘汰最旧条目）"""
        with self._mem_lock:
            expires_at = datetime.now(UTC).timestamp() + ttl_seconds
            self._mem_cache[cache_key] = (data, expires_at)
            self._mem_cache.move_to_end(cache_key)
            while len(self._mem_cache) > _MEMORY_CACHE_MAX:
                self._mem_cache.popitem(last=False)

    @staticmethod
    def _compute_hash(api_source: str, request_key: str) -> str:
        """计算请求的唯一哈希值"""
        combined = f'{api_source}:{request_key}'
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def get(self, api_source: str, request_key: str) -> dict | None:
        """
        从缓存获取API响应（先查内存 LRU，再查数据库）

        Returns:
            缓存的响应数据或None
        """
        request_hash = self._compute_hash(api_source, request_key)
        cache_key = f'{api_source}:{request_hash}'

        # 1. 内存 LRU 快速路径
        mem_data = self._mem_get(cache_key)
        if mem_data is not None:
            return mem_data

        # 2. 数据库慢路径
        cache = APICache.query.filter_by(api_source=api_source, request_hash=request_hash).first()

        if cache:
            if cache.is_expired():
                logger.debug(f'缓存已过期: {api_source} - {request_key}')
                return None

            if cache.status_code and cache.status_code >= 400:
                logger.warning(f'忽略错误API缓存: {api_source} - {request_key} ({cache.status_code})')
                return None

            logger.info(f'API缓存命中: {api_source} - {request_key}')

            try:
                data = json.loads(cache.response_data)
            except json.JSONDecodeError:
                data = {'error': cache.response_data}

            # 回填内存缓存
            remaining = int((cache.expires_at.replace(tzinfo=UTC) - datetime.now(UTC)).total_seconds())
            if remaining > 0:
                self._mem_set(cache_key, data, remaining)

            return data

        logger.debug(f'API缓存未命中: {api_source} - {request_key}')
        return None

    def set(
        self,
        api_source: str,
        request_key: str,
        response_data: Any,
        ttl_seconds: int | None = None,
        is_error: bool = False,
        error_message: str | None = None,
    ) -> APICache:
        """
        保存API响应到缓存（同步写入内存 LRU 和数据库）

        Returns:
            APICache对象
        """
        if isinstance(response_data, dict):
            response_str = json.dumps(response_data, ensure_ascii=False)
        else:
            response_str = str(response_data)

        request_hash = self._compute_hash(api_source, request_key)
        ttl_seconds = ttl_seconds or self.DEFAULT_TTL.get(api_source, 86400)
        cache_key = f'{api_source}:{request_hash}'

        existing = APICache.query.filter_by(api_source=api_source, request_hash=request_hash).first()

        if existing:
            existing.response_data = response_str
            existing.status_code = 500 if is_error else 200
            existing.error_message = error_message
            existing.ttl_seconds = ttl_seconds
            existing.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
            existing.usage_count += 1
            existing.last_used_at = datetime.now(UTC)
        else:
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
            existing = APICache(
                api_source=api_source,
                request_key=request_key,
                request_hash=request_hash,
                response_data=response_str,
                status_code=500 if is_error else 200,
                error_message=error_message,
                ttl_seconds=ttl_seconds,
                expires_at=expires_at,
                usage_count=1,
                last_used_at=datetime.now(UTC),
            )
            db.session.add(existing)

        try:
            db.session.commit()

            # 写通到内存缓存（仅非错误响应）
            if not is_error and isinstance(response_data, dict):
                self._mem_set(cache_key, response_data, ttl_seconds)

            logger.info(f'API缓存已保存: {api_source} - {request_key}')
            return existing
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'保存API缓存失败: {e}')
            db.session.rollback()
            raise

    def delete(self, api_source: str | None = None, older_than_days: int | None = None) -> int:
        """
        删除缓存记录

        Returns:
            删除的记录数
        """
        query = APICache.query

        if api_source:
            query = query.filter_by(api_source=api_source)

        if older_than_days:
            cutoff_date = datetime.now(UTC) - timedelta(days=older_than_days)
            query = query.filter(APICache.created_at < cutoff_date)

        deleted_count = query.delete()
        try:
            db.session.commit()

            # 同步清理内存缓存
            with self._mem_lock:
                if api_source:
                    prefix = f'{api_source}:'
                    keys_to_remove = [k for k in self._mem_cache if k.startswith(prefix)]
                    for k in keys_to_remove:
                        del self._mem_cache[k]
                else:
                    self._mem_cache.clear()

            logger.info(f'已删除 {deleted_count} 条API缓存')
            return deleted_count
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'删除API缓存失败: {e}')
            db.session.rollback()
            raise

    def clear_expired(self) -> int:
        """清理过期缓存"""
        deleted = APICache.query.filter(APICache.expires_at < datetime.now(UTC)).delete()

        try:
            db.session.commit()

            # 同步清理内存中过期条目
            now_ts = datetime.now(UTC).timestamp()
            with self._mem_lock:
                expired_keys = [k for k, (_, exp) in self._mem_cache.items() if now_ts > exp]
                for k in expired_keys:
                    del self._mem_cache[k]

            logger.info(f'已清理 {deleted} 条过期API缓存')
            return deleted
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'清理过期缓存失败: {e}')
            db.session.rollback()
            raise

    def get_stats(self, api_source: str | None = None) -> dict:
        """
        获取缓存统计信息（使用单条 GROUP BY 查询）

        Returns:
            统计信息字典
        """
        if api_source:
            total_count = APICache.query.filter_by(api_source=api_source).count()
            expired_count = (
                APICache.query.filter_by(api_source=api_source)
                .filter(APICache.expires_at < datetime.now(UTC))
                .count()
            )
            total_usage = (
                db.session.query(func.sum(APICache.usage_count))
                .filter(APICache.api_source == api_source)
                .scalar()
                or 0
            )
            return {
                'total_count': total_count,
                'expired_count': expired_count,
                'total_usage_count': total_usage,
            }

        # 无 api_source 时，用单条 GROUP BY 查询替代 N+1
        rows = (
            db.session.query(
                APICache.api_source,
                func.count(APICache.id),
                func.sum(APICache.usage_count),
            )
            .group_by(APICache.api_source)
            .all()
        )

        total_count = 0
        total_usage = 0
        stats: dict[str, int] = {}
        for source, count, usage in rows:
            total_count += count
            total_usage += usage or 0
            stats[f'{source}_count'] = count

        expired_count = APICache.query.filter(APICache.expires_at < datetime.now(UTC)).count()

        return {
            'total_count': total_count,
            'expired_count': expired_count,
            'total_usage_count': total_usage,
            **stats,
        }

    def get_recent_records(self, limit: int = 20, api_source: str | None = None) -> list[APICache]:
        """获取最近的 API 缓存记录"""
        try:
            query = APICache.query
            if api_source:
                query = query.filter_by(api_source=api_source)
            return query.order_by(APICache.last_used_at.desc()).limit(limit).all()
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'获取最近缓存记录失败: {e}')
            return []


_api_cache_service: APICacheService | None = None


def get_api_cache_service() -> APICacheService:
    """获取API缓存服务单例"""
    global _api_cache_service
    if _api_cache_service is None:
        _api_cache_service = APICacheService()
    return _api_cache_service
