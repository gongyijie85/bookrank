import logging

from flask import current_app

from ..utils import clean_translation_text
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.service_helpers import (
    get_book_service,
    get_google_books_client,
    get_translation_service,
    submit_background_task,
)

logger = logging.getLogger(__name__)



def is_valid_isbn(value: str | None) -> bool:
    """验证ISBN格式（委托给 api_helpers.validate_isbn）"""
    from ..utils.api_helpers import validate_isbn
    return validate_isbn(value)


def fetch_google_books_details(book: dict, isbn: str) -> None:
    cache_key = f'google_books_detail:{isbn}'
    cache_service = None

    try:
        book_service = get_book_service()
        if book_service:
            cache_service = book_service.cache
    except Exception as e:
        log_error(ErrorCategory.CACHE, f'获取 book_service 缓存失败: {e}', level='warning')

    if cache_service:
        try:
            cached = cache_service.get(cache_key)
            if cached and isinstance(cached, dict):
                update_book_from_google_books(book, cached)
                return
        except Exception as e:
            log_error(ErrorCategory.CACHE, f'读取 Google Books 缓存失败 ISBN {isbn}: {e}', level='warning')

    google_client = get_google_books_client()
    if not google_client:
        return

    try:
        details = google_client.fetch_book_details(isbn)
        if not details or not isinstance(details, dict):
            return

        update_book_from_google_books(book, details)

        if cache_service:
            try:
                cache_service.set(cache_key, details, ttl=604800)
            except Exception as e:
                log_error(ErrorCategory.CACHE, f'写入 Google Books 缓存失败 ISBN {isbn}: {e}', level='warning')

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'Google Books API 调用失败 ISBN {isbn}: {e}', level='warning')


def translate_field_async(book: dict, source_field: str, target_field: str) -> None:
    app = current_app._get_current_object()
    translation_service = get_translation_service()

    def _do_translate():
        try:
            if translation_service:
                with app.app_context():
                    text = book.get(source_field, '')
                    if text and not book.get(target_field):
                        ft = (
                            'title'
                            if target_field == 'title_zh'
                            else 'description'
                            if target_field == 'description_zh'
                            else 'details'
                            if target_field == 'details_zh'
                            else 'text'
                        )
                        translated = translation_service.translate(text, 'en', 'zh', field_type=ft)
                        if translated:
                            book[target_field] = translated
                            logger.info(f'已翻译 {source_field} -> {target_field}')
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'异步翻译失败 {source_field}: {e}', level='warning')

    submit_background_task(_do_translate)


def update_book_from_google_books(book: dict, details: dict) -> None:
    if details.get('details') and details['details'] != 'No detailed description available.':
        book['details'] = details['details']
        translate_field_async(book, 'details', 'details_zh')

    if details.get('page_count') and details['page_count'] != 'Unknown':
        book['page_count'] = str(details['page_count'])

    if details.get('publication_dt') and details['publication_dt'] != 'Unknown':
        book['publication_dt'] = details['publication_dt']

    if details.get('language') and details['language'] != 'Unknown':
        book['language'] = details['language']

    if details.get('publisher') and details['publisher'] not in ('Unknown', 'Unknown Publisher'):
        current_publisher = book.get('publisher', '')
        if not current_publisher or current_publisher in ('Unknown', 'Unknown Publisher'):
            book['publisher'] = details['publisher']

    if details.get('cover_url') and not book.get('cover'):
        book['cover'] = details['cover_url']

    if details.get('isbn_13') and is_valid_isbn(details['isbn_13']) and not book.get('isbn13'):
        book['isbn13'] = details['isbn_13']
    if details.get('isbn_10') and is_valid_isbn(details['isbn_10']) and not book.get('isbn10'):
        book['isbn10'] = details['isbn_10']

    if book.get('description') and not book.get('description_zh'):
        translate_field_async(book, 'description', 'description_zh')


def merge_or_translate_book(book: dict, isbn: str) -> None:
    try:
        from .user_service import UserService

        user_service = UserService()
        meta = user_service.get_book_metadata(isbn)
        if meta:
            if meta.description_zh and not book.get('description_zh'):
                book['description_zh'] = clean_translation_text(meta.description_zh, 'description')
            if meta.details_zh and not book.get('details_zh'):
                book['details_zh'] = clean_translation_text(meta.details_zh, 'details')
            if meta.title_zh and not book.get('title_zh'):
                book['title_zh'] = clean_translation_text(meta.title_zh, 'title')

            if meta.title_zh and meta.description_zh and meta.details_zh:
                return

        needs_title = bool(book.get('title') and not book.get('title_zh'))
        needs_desc = bool(
            book.get('description')
            and book.get('description') != 'No summary available.'
            and not book.get('description_zh')
        )
        needs_details = bool(
            book.get('details')
            and book.get('details') != 'No detailed description available.'
            and not book.get('details_zh')
        )

        if not needs_title and not needs_desc and not needs_details:
            return

        translation_service = get_translation_service()
        if not translation_service:
            return
        app = current_app._get_current_object()

        def _translate_async():
            with app.app_context():
                try:
                    from .user_service import UserService

                    user_svc = UserService()
                    title_zh = None
                    desc_zh = None
                    details_zh = None

                    if needs_title:
                        try:
                            title_zh = translation_service.translate(
                                book.get('title', ''), 'en', 'zh', field_type='title'
                            )
                        except Exception as e:
                            log_error(ErrorCategory.TRANSLATION, f'异步书名翻译失败: {e}', level='warning')

                    if needs_desc:
                        try:
                            desc_zh = translation_service.translate(
                                book.get('description', ''), 'en', 'zh', field_type='description'
                            )
                        except Exception as e:
                            log_error(ErrorCategory.TRANSLATION, f'异步简介翻译失败: {e}', level='warning')

                    if needs_details:
                        try:
                            details_zh = translation_service.translate(
                                book.get('details', ''), 'en', 'zh', field_type='details'
                            )
                        except Exception as e:
                            log_error(ErrorCategory.TRANSLATION, f'异步详情翻译失败: {e}', level='warning')

                    user_svc.save_book_translation(
                        isbn, title_zh=title_zh, description_zh=desc_zh, details_zh=details_zh
                    )
                    logger.info(f'异步翻译完成: {isbn}')
                except Exception as e:
                    log_error(ErrorCategory.TRANSLATION, f'异步翻译失败 {isbn}: {e}', level='warning')

        submit_background_task(_translate_async)

    except Exception as e:
        log_error(ErrorCategory.TRANSLATION, f'合并图书翻译失败 {isbn}: {e}', level='warning')
