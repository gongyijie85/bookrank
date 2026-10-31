import re

from flask import request

from ...models.database import db
from ...models.schemas import BookMetadata
from ...utils.admin_auth import admin_required
from ...utils.api_helpers import (
    PLACEHOLDER_TEXTS,
    APIResponse,
    clean_translation_text,
    csrf_protect,
    handle_api_errors,
    is_non_substantive_details,
    rate_limit,
    validate_isbn,
)
from ...utils.error_handler import ErrorCategory, log_error
from ...utils.service_helpers import get_service
from . import api_bp


def _valid_chinese(value: object, field: str) -> bool:
    return (
        isinstance(value, str)
        and bool(re.search(r'[\u3400-\u9fff]', value))
        and value.strip() not in PLACEHOLDER_TEXTS
        and not (field == 'details' and is_non_substantive_details(value))
    )


@api_bp.route('/translate', methods=['POST'])
@rate_limit()
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
@rate_limit()
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
@rate_limit()
@csrf_protect
@handle_api_errors
def translate_book(isbn: str):
    """翻译图书信息（同时支持 NYT 分类图书和 AwardBook 获奖书单）"""
    if not validate_isbn(isbn):
        return APIResponse.error('无效的ISBN格式', 400)

    from ...services.award_book_service import AwardBookService
    from ...services.zhipu_translation_service import get_translation_service

    book_service = get_service('book_service')
    book_data = book_service.get_book_by_isbn(isbn) if book_service else None
    is_main_book = bool(book_data)

    # Fallback: 查询 AwardBook 表（获奖书单数据不在主 books 缓存中）
    # 注意：用 display_title 替代原始 title，避免 v0.9.57 修复前的 ISBN 脏数据
    # 被当作"书名"送进翻译 API，模型返回 ISBN 字面量后被前端写回页面
    award_book_service = AwardBookService()
    award_book = award_book_service.get_award_book_by_isbn(isbn)
    if award_book and not book_data:
        book_data = {
            'title': award_book.display_title or '',
            'description': award_book.description or '',
            'details': award_book.details or '',
            'isbn13': award_book.isbn13 or isbn,
            'title_zh': award_book.title_zh or '',
            'description_zh': award_book.description_zh or '',
        }

    if not book_data:
        return APIResponse.error('图书不存在', 404)

    translated_data = dict(book_data)
    fields = ('title', 'description', 'details')
    if is_main_book and any(
        book_data.get(field) and not _valid_chinese(translated_data.get(f'{field}_zh'), field) for field in fields
    ):
        # Cached ranking snapshots can predate a saved on-demand translation.
        # A failed metadata read must propagate, rather than retranslate over it.
        try:
            metadata = db.session.get(BookMetadata, isbn)
        except Exception as e:
            log_error(ErrorCategory.DB_QUERY, f'读取已有翻译失败 {isbn}: {e}', level='warning')
            return APIResponse.error('已有译文暂时无法读取，请稍后重试', 503, errors={'retryable': True})
        if metadata:
            for field in fields:
                target = f'{field}_zh'
                value = getattr(metadata, target)
                if not _valid_chinese(translated_data.get(target), field) and _valid_chinese(value, field):
                    translated_data[target] = value

    unsupported_details = bool(not is_main_book and book_data.get('details'))
    pending = []
    for field in fields:
        source = str(book_data.get(field) or '').strip()
        if (
            source
            and source not in PLACEHOLDER_TEXTS
            and not (field == 'details' and (unsupported_details or is_non_substantive_details(source)))
            and not _valid_chinese(translated_data.get(f'{field}_zh'), field)
            and not re.search(r'[\u3400-\u9fff]', source)
        ):
            pending.append(field)

    new_values = {}
    if pending:
        input_data = dict(translated_data)
        for field in fields:
            if field not in pending:
                input_data[field] = ''
            else:
                input_data[f'{field}_zh'] = ''
        try:
            result = get_translation_service().translate_book_info(input_data) or {}
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'翻译暂不可用 {isbn}: {e}', level='warning')
            return APIResponse.error('翻译暂不可用，请稍后重试', 503, errors={'retryable': True})
        for field in pending:
            target = f'{field}_zh'
            value = result.get(target)
            if isinstance(value, str):
                value = clean_translation_text(value, field)
            if _valid_chinese(value, field):
                new_values[target] = value
        if not new_values:
            return APIResponse.error('翻译暂不可用，请稍后重试', 503, errors={'retryable': True})
        if book_service and is_main_book:
            try:
                saved = bool(book_service.save_book_translation(isbn=isbn, **new_values))
            except Exception as e:
                log_error(ErrorCategory.TRANSLATION, f'翻译结果写入语言包失败 {isbn}: {e}', level='warning')
                saved = False
            if not saved:
                return APIResponse.error('译文保存失败，请稍后重试', 503, errors={'retryable': True})
            translated_data.update(new_values)

    award_partial = False
    if award_book:
        # Reuse durable main-book translations for the same ISBN.  An earlier
        # main save can succeed while the award save fails, so this also runs
        # when no new translation was necessary on this request.
        available_values = translated_data if is_main_book else {**translated_data, **new_values}
        award_values = {
            f'{field}_zh': available_values[f'{field}_zh']
            for field in ('title', 'description')
            if _valid_chinese(available_values.get(f'{field}_zh'), field)
            and not _valid_chinese(getattr(award_book, f'{field}_zh'), field)
        }
        if award_values:
            try:
                award_saved = bool(award_book_service.save_award_book_translation(isbn=isbn, **award_values))
            except Exception as e:
                log_error(ErrorCategory.TRANSLATION, f'获奖书译文保存失败 {isbn}: {e}', level='warning')
                award_saved = False
            if not award_saved:
                if not is_main_book:
                    return APIResponse.error('译文保存失败，请稍后重试', 503, errors={'retryable': True})
                award_partial = True
            elif not is_main_book:
                translated_data.update(new_values)

    status = (
        'partial'
        if unsupported_details
        or award_partial
        or any(not _valid_chinese(translated_data.get(f'{field}_zh'), field) for field in pending)
        else 'complete'
    )
    return APIResponse.success(data={'book': translated_data, 'translation_status': status})


@api_bp.route('/translate/cache/stats')
@rate_limit()
@admin_required
@handle_api_errors
def get_translation_cache_stats():
    """获取翻译缓存统计信息"""
    from ...services.zhipu_translation_service import get_translation_service

    service = get_translation_service()
    svc = service.zhipu
    zhipu_available = svc.is_available()
    provider_name = 'SiliconFlow Hunyuan-MT-7B' if svc.provider == 'siliconflow' else 'ZhipuAI GLM'

    try:
        cache_stats = service.get_cache_stats()
    except Exception as e:
        if 'no such table' in str(e):
            return APIResponse.success(
                data={
                    'service': provider_name,
                    'status': 'offline',
                    'model': svc.model,
                    'description': f'翻译服务(provider={svc.provider}, model={svc.model})',
                    'message': 'Database not initialized',
                }
            )
        raise

    return APIResponse.success(
        data={
            'service': provider_name,
            'status': 'online' if zhipu_available else 'offline',
            'model': svc.model,
            'description': f'翻译服务(provider={svc.provider}, model={svc.model})',
            'cache': cache_stats,
        }
    )


@api_bp.route('/translate/cache/recent')
@rate_limit()
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
@rate_limit()
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
