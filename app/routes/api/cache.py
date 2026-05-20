import logging

from flask import request

from ...services.api_cache_service import get_api_cache_service
from ...utils.admin_auth import admin_required
from ...utils.api_helpers import APIResponse, csrf_protect
from . import api_bp

logger = logging.getLogger(__name__)


@api_bp.route('/cache/stats')
@admin_required
def get_api_cache_stats():
    """获取API缓存统计信息（通过 Service 层）"""
    try:
        cache_service = get_api_cache_service()
        stats = cache_service.get_stats()

        return APIResponse.success(data=stats)

    except Exception as e:
        logger.error(f'获取API缓存统计错误: {e}', exc_info=True)
        return APIResponse.error('获取统计失败', 500)


@api_bp.route('/cache/recent')
@admin_required
def get_api_cache_recent():
    """获取最近的API缓存记录（通过 Service 层）"""
    try:
        limit = min(max(1, request.args.get('limit', 20, type=int)), 100)
        api_source = request.args.get('api_source')

        cache_service = get_api_cache_service()
        records = cache_service.get_recent_records(limit=limit, api_source=api_source)

        return APIResponse.success(
            data={
                'records': [
                    {
                        'id': r.id,
                        'api_source': r.api_source,
                        'request_key': r.request_key,
                        'status_code': r.status_code,
                        'usage_count': r.usage_count,
                        'created_at': r.created_at.isoformat() if r.created_at else None,
                        'expires_at': r.expires_at.isoformat() if r.expires_at else None,
                    }
                    for r in records
                ],
                'count': len(records),
            }
        )

    except Exception as e:
        logger.error(f'获取API缓存记录错误: {e}', exc_info=True)
        return APIResponse.error('获取缓存记录失败', 500)


@api_bp.route('/cache/clear', methods=['POST'])
@csrf_protect
@admin_required
def clear_api_cache():
    """清理API缓存（通过 Service 层）"""
    try:
        data = request.get_json() or {}
        older_than_days = data.get('older_than_days')

        cache_service = get_api_cache_service()
        deleted = cache_service.delete(older_than_days=older_than_days)

        return APIResponse.success(message=f'已清理 {deleted} 条API缓存')

    except Exception as e:
        logger.error(f'清理API缓存错误: {e}', exc_info=True)
        return APIResponse.error('清理缓存失败', 500)


@api_bp.route('/cache/clear-expired', methods=['POST'])
@csrf_protect
@admin_required
def clear_expired_api_cache():
    """清理过期API缓存（通过 Service 层）"""
    try:
        cache_service = get_api_cache_service()
        deleted = cache_service.clear_expired()

        return APIResponse.success(message=f'已清理 {deleted} 条过期缓存')

    except Exception as e:
        logger.error(f'清理过期缓存错误: {e}', exc_info=True)
        return APIResponse.error('清理缓存失败', 500)
