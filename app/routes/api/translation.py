import logging

from flask import request

from ...utils.admin_auth import admin_required
from ...utils.api_helpers import APIResponse, csrf_protect, handle_api_errors, validate_isbn
from ...utils.error_handler import ErrorCategory, log_error
from ...utils.service_helpers import get_book_service
from . import api_bp

logger = logging.getLogger(__name__)


@api_bp.route('/translate', methods=['POST'])
@csrf_protect
@handle_api_errors
def translate_text():
    """翻译文本"""
    if not request.is_json:
        return APIResponse.error('Content-Type must be application/json', 400)

    data = request.get_json() or {}
    text = data.get('text', '').strip()
    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'zh')
    field_type = data.get('field_type', 'text')

    if not text:
        return APIResponse.error('缺少要翻译的文本', 400)
    if len(text) > 10000:
        return APIResponse.error('文本长度超过限制（最大10000字符）', 400)

    from ...services.zhipu_translation_service import get_translation_service

    service = get_translation_service()
    result = service.translate(text, source_lang, target_lang, field_type=field_type)

    if result:
        return APIResponse.success(
            data={'original': text, 'translated': result, 'source_lang': source_lang, 'target_lang': target_lang}
        )
    return APIResponse.error('翻译服务暂时不可用', 503)


@api_bp.route('/translate/book-fields', methods=['POST'])
@csrf_protect
@handle_api_errors
def translate_book_fields():
    """合并翻译一本书的多个字段（单次API调用，减少请求量）"""
    if not request.is_json:
        return APIResponse.error('Content-Type must be application/json', 400)

    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    details = data.get('details', '').strip()
    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'zh')

    if not title and not description and not details:
        return APIResponse.error('至少提供一个待翻译字段', 400)

    total_len = len(title) + len(description) + len(details)
    if total_len > 15000:
        return APIResponse.error('文本总长度超过限制（最大15000字符）', 400)

    from ...services.zhipu_translation_service import get_translation_service

    service = get_translation_service()
    result = service.translate_book_fields(
        title=title, description=description, details=details, source_lang=source_lang, target_lang=target_lang
    )

    return APIResponse.success(data=result)


@api_bp.route('/translate/book/<isbn>', methods=['POST'])
@csrf_protect
@handle_api_errors
def translate_book(isbn: str):
    """翻译图书信息"""
    if not validate_isbn(isbn):
        return APIResponse.error('无效的ISBN格式', 400)

    from ...services.zhipu_translation_service import get_translation_service

    book_service = get_book_service()
    if not book_service:
        return APIResponse.error('图书服务不可用', 503)

    book_data = book_service.get_book_by_isbn(isbn)
    if not book_data:
        return APIResponse.error('图书不存在', 404)

    service = get_translation_service()
    translated_data = service.translate_book_info(book_data)
    if translated_data:
        try:
            book_service.save_book_translation(
                isbn=isbn,
                title_zh=translated_data.get('title_zh'),
                description_zh=translated_data.get('description_zh'),
                details_zh=translated_data.get('details_zh'),
            )
            language_pack = getattr(book_service, '_language_pack', None)
            if language_pack:
                language_pack.store_books([translated_data])
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'翻译结果写入语言包失败 {isbn}: {e}', level='warning')

    return APIResponse.success(data={'book': translated_data})


@api_bp.route('/translate/cache/stats')
@admin_required
@handle_api_errors
def get_translation_cache_stats():
    """获取翻译缓存统计信息"""
    from ...services.zhipu_translation_service import get_translation_service

    service = get_translation_service()
    zhipu_available = service.zhipu.is_available()

    try:
        cache_stats = service.get_cache_stats()
    except Exception as e:
        if 'no such table' in str(e):
            return APIResponse.success(
                data={
                    'service': 'ZhipuAI GLM-4.7-Flash',
                    'status': 'offline',
                    'model': 'glm-4.7-flash',
                    'description': '使用智谱AI免费模型进行高质量翻译',
                    'message': 'Database not initialized',
                }
            )
        raise

    return APIResponse.success(
        data={
            'service': 'ZhipuAI GLM-4.7-Flash',
            'status': 'online' if zhipu_available else 'offline',
            'model': 'glm-4.7-flash',
            'description': '使用智谱AI免费模型进行高质量翻译',
            'cache': cache_stats,
        }
    )


@api_bp.route('/translate/cache/recent')
@admin_required
@handle_api_errors
def get_translation_cache_recent():
    """获取最近的翻译缓存记录"""
    from ...services.translation_cache_service import get_translation_cache_service

    limit = min(max(1, request.args.get('limit', 20, type=int)), 100)
    source_lang = request.args.get('source_lang')
    target_lang = request.args.get('target_lang')

    cache_service = get_translation_cache_service()
    recent = cache_service.get_recent(limit, source_lang, target_lang)

    return APIResponse.success(
        data={
            'records': [
                {
                    'id': r.id,
                    'source_text': r.source_text[:100] + '...' if len(r.source_text) > 100 else r.source_text,
                    'translated_text': r.translated_text[:100] + '...'
                    if len(r.translated_text) > 100
                    else r.translated_text,
                    'source_lang': r.source_lang,
                    'target_lang': r.target_lang,
                    'usage_count': r.usage_count,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'last_used_at': r.last_used_at.isoformat() if r.last_used_at else None,
                }
                for r in recent
            ],
            'count': len(recent),
        }
    )


@api_bp.route('/translate/cache/clear', methods=['POST'])
@csrf_protect
@admin_required
@handle_api_errors
def clear_translation_cache():
    """清理翻译缓存"""
    from ...services.translation_cache_service import get_translation_cache_service

    data = request.get_json() or {}
    cache_id = data.get('cache_id')
    older_than_days = data.get('older_than_days')
    min_usage = data.get('min_usage')

    cache_service = get_translation_cache_service()

    if older_than_days or min_usage is not None:
        deleted = cache_service.delete(older_than_days=older_than_days, min_usage=min_usage)
        message = f'已清理 {deleted} 条翻译缓存'
    elif cache_id:
        deleted = cache_service.delete(cache_id=cache_id)
        message = f'已删除缓存记录 #{cache_id}'
    else:
        deleted = cache_service.clear_all()
        message = f'已清空所有翻译缓存（{deleted}条）'

    return APIResponse.success(message=message)
