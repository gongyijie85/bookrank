"""
API缓存服务 - 为外部API调用提供数据库持久化缓存
"""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func

from ..models.database import db
from ..models.schemas import APICache
from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


class APICacheService:
    """API缓存服务类"""

    DEFAULT_TTL = {
        'nyt': 86400 * 7,
        'google_books': 86400,
        'open_library': 86400 * 3,
        'wikidata': 86400 * 7,
    }

    @staticmethod
    def _compute_hash(api_source: str, request_key: str) -> str:
        """计算请求的唯一哈希值"""
        combined = f'{api_source}:{request_key}'
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def get(self, api_source: str, request_key: str) -> dict | None:
        """
        从缓存获取API响应

        Args:
            api_source: API来源标识 (nyt, google_books, open_library, wikidata)
            request_key: 请求键 (如 category_id, isbn 等)

        Returns:
            缓存的响应数据或None
        """
        request_hash = self._compute_hash(api_source, request_key)

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
                return json.loads(cache.response_data)
            except json.JSONDecodeError:
                return {'error': cache.response_data}

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
        保存API响应到缓存

        Args:
            api_source: API来源标识
            request_key: 请求键
            response_data: 响应数据
            ttl_seconds: 缓存过期时间（秒）
            is_error: 是否是错误响应
            error_message: 错误消息

        Returns:
            APICache对象
        """
        if isinstance(response_data, dict):
            response_str = json.dumps(response_data, ensure_ascii=False)
        else:
            response_str = str(response_data)

        request_hash = self._compute_hash(api_source, request_key)
        ttl_seconds = ttl_seconds or self.DEFAULT_TTL.get(api_source, 86400)

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
            logger.info(f'API缓存已保存: {api_source} - {request_key}')
            return existing
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'保存API缓存失败: {e}')
            db.session.rollback()
            raise

    def delete(self, api_source: str | None = None, older_than_days: int | None = None) -> int:
        """
        删除缓存记录

        Args:
            api_source: API来源筛选
            older_than_days: 删除N天前的记录

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
            logger.info(f'已清理 {deleted} 条过期API缓存')
            return deleted
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'清理过期缓存失败: {e}')
            db.session.rollback()
            raise

    def get_stats(self, api_source: str | None = None) -> dict:
        """
        获取缓存统计信息

        Args:
            api_source: API来源筛选

        Returns:
            统计信息字典
        """
        query = APICache.query

        if api_source:
            query = query.filter_by(api_source=api_source)

        total_count = query.count()

        expired_count = query.filter(APICache.expires_at < datetime.now(UTC)).count()

        total_usage = db.session.query(func.sum(APICache.usage_count)).scalar() or 0

        stats = {
            'total_count': total_count,
            'expired_count': expired_count,
            'total_usage_count': total_usage,
        }

        if not api_source:
            for source in self.DEFAULT_TTL:
                source_count = APICache.query.filter_by(api_source=source).count()
                stats[f'{source}_count'] = source_count

        return stats

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
