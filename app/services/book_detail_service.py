import logging
from typing import Any, cast

from flask import current_app

from ..utils import clean_translation_text
from ..utils.api_helpers import is_placeholder_text, strip_placeholder, validate_isbn
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.service_helpers import (
    get_google_books_client,
    get_or_create_open_library_client,
    get_service,
    submit_background_task,
)
from ..utils.translation_overrides import TRANSLATION_OVERRIDES

logger = logging.getLogger(__name__)


def fetch_google_books_details(book: dict, isbn: str) -> None:
    cache_key = f'google_books_detail:{isbn}'
    cache_service = None

    try:
        book_service = get_service('book_service')
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


def enrich_book_details(book: dict, isbn: str) -> None:
    """详情页的详情富化入口：Google Books 优先，取不到实质详情时回退 Open Library。

    只用 Google Books 会让一部分书**永远**没有详情：独立出版与新书在该库常常没有
    条目（实测 9798890920461《Stitched》在 Google Books 无记录，Open Library 的
    work 级记录却有 582 字符完整简介）。此时 `details` 只剩抓取侧写下的占位串，
    模板把它归一化成空，详情页的「详细信息」标签就整块消失。

    先就地清洗历史占位串，再补第二数据源，让详情页有内容可渲染。本函数只负责把
    正文写进 `book['details']`：翻译与持久化统一交给紧随其后的 `merge_or_translate_book`
    （它已包含 details 的排队翻译与 save_book_translation），避免同一段正文被翻译两次。

    Args:
        book: 详情页的书籍字典，原地修改
        isbn: 已通过 validate_isbn 校验的 ISBN
    """
    # 入口即清洗：缓存里可能还躺着历史占位串，先归一化成空，
    # 下游（模板 / 详情 API / needs_details 判断）才看得到真实的「有 / 没有」。
    book['details'] = strip_placeholder(book.get('details'))

    fetch_google_books_details(book, isbn)
    if book.get('details'):
        return

    try:
        client = get_or_create_open_library_client()
        description = client.fetch_work_description_by_isbn(isbn) if client else ''
    except Exception as e:
        # 兜底源失败不能影响详情页渲染：没有详情仍然是一张可用的页面。
        log_error(ErrorCategory.API_CALL, f'Open Library 详情兜底失败 ISBN {isbn}: {e}', level='warning')
        return

    if not description or is_placeholder_text(description):
        return

    book['details'] = description
    logger.info('Open Library 兜底详情命中: ISBN %s (%d 字)', isbn, len(description))


def translate_field_async(book: dict, source_field: str, target_field: str) -> None:
    app = cast('Any', current_app)._get_current_object()
    translation_service = get_service('translation_service')

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
    # 抓取侧用占位串表示「没有详情」，它不是数据：放行会让 needs_details 永远为假，
    # 该书的详情补齐路径从此封死（见 api_helpers._PLACEHOLDER_TEXTS）。
    fetched_details = details.get('details')
    if fetched_details and not is_placeholder_text(fetched_details):
        book['details'] = fetched_details
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

    if details.get('isbn_13') and validate_isbn(details['isbn_13']) and not book.get('isbn13'):
        book['isbn13'] = details['isbn_13']
    if details.get('isbn_10') and validate_isbn(details['isbn_10']) and not book.get('isbn10'):
        book['isbn10'] = details['isbn_10']

    if book.get('description') and not book.get('description_zh'):
        translate_field_async(book, 'description', 'description_zh')

    # 书名同样需要补翻：此前只排了 description/details，导致中文简介有值而书名
    # 一直是英文（页面回退显示原文）。见 #210 的回填取证。
    if book.get('title') and not book.get('title_zh'):
        translate_field_async(book, 'title', 'title_zh')


def _apply_translation_overrides(book: dict, isbn: str) -> None:
    """应用翻译覆盖映射"""
    overrides = TRANSLATION_OVERRIDES.get(isbn)
    if overrides:
        for key, value in overrides.items():
            if value and (not book.get(key) or book.get(key) != value):
                book[key] = value
                logger.info(f'应用翻译覆盖: {isbn} {key} -> {value}')


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

            # 应用翻译覆盖
            _apply_translation_overrides(book, isbn)

            if meta.title_zh and meta.description_zh and meta.details_zh:
                return

        needs_title = bool(book.get('title') and not book.get('title_zh'))
        needs_desc = bool(
            book.get('description')
            and not is_placeholder_text(book.get('description'))
            and not book.get('description_zh')
        )
        needs_details = bool(
            book.get('details') and not is_placeholder_text(book.get('details')) and not book.get('details_zh')
        )

        if not needs_title and not needs_desc and not needs_details:
            # 即使不需要翻译，也检查是否需要应用覆盖
            _apply_translation_overrides(book, isbn)
            return

        translation_service = get_service('translation_service')
        if not translation_service:
            return
        app = cast('Any', current_app)._get_current_object()

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

                    # 应用翻译覆盖
                    if title_zh:
                        book['title_zh'] = title_zh
                    if desc_zh:
                        book['description_zh'] = desc_zh
                    if details_zh:
                        book['details_zh'] = details_zh

                    _apply_translation_overrides(book, isbn)

                    user_svc.save_book_translation(
                        isbn,
                        title_zh=book.get('title_zh'),
                        description_zh=book.get('description_zh'),
                        details_zh=book.get('details_zh'),
                    )
                    logger.info(f'异步翻译完成: {isbn}')
                except Exception as e:
                    log_error(ErrorCategory.TRANSLATION, f'异步翻译失败 {isbn}: {e}', level='warning')

        submit_background_task(_translate_async)

    except Exception as e:
        log_error(ErrorCategory.TRANSLATION, f'合并图书翻译失败 {isbn}: {e}', level='warning')
