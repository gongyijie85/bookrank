import logging
from typing import Any

from ...models.database import db
from ...models.new_book import NewBook
from ...utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


class TranslationPipeline:
    def __init__(self, translator: Any, language_pack: Any) -> None:
        self._translator = translator
        self._language_pack = language_pack

    def _translate_book(self, book: NewBook) -> bool:
        if not self._translator:
            return False

        try:
            changed = False
            if book.title and not book.title_zh:
                translated = self._translator.translate(book.title, 'en', 'zh', field_type='title')
                if translated:
                    book.title_zh = translated
                    changed = True
                else:
                    logger.debug('title 翻译返回空: id=%s, len=%d', getattr(book, 'id', '?'), len(book.title))

            if book.description and not book.description_zh:
                desc = book.description if len(book.description) <= 1000 else book.description[:1000]
                translated = self._translator.translate(desc, 'en', 'zh', field_type='description')
                if translated:
                    book.description_zh = translated
                    changed = True
                else:
                    logger.debug('description 翻译返回空: id=%s, len=%d', getattr(book, 'id', '?'), len(desc))
            return changed

        except Exception as e:
            logger.warning(
                '翻译失败: %s (id=%s) - %s',
                (book.title[:30] if book.title else '<空>'),
                getattr(book, 'id', '?'),
                e,
            )
            return False

    def translate_book_background(self, book_id: int, translation_service: Any) -> None:
        try:
            book = db.session.get(NewBook, book_id)
            if not book:
                return

            if not book.title_zh and book.title:
                book.title_zh = translation_service.translate(book.title, 'en', 'zh', field_type='title')
            if book.description and not book.description_zh:
                book.description_zh = translation_service.translate(
                    book.description[:1000], 'en', 'zh', field_type='description'
                )
            db.session.commit()
            logger.info(f'Book {book_id} translated in background')
        except Exception as e:
            log_error(
                ErrorCategory.TRANSLATION, f'Background translation failed for book {book_id}: {e}', level='warning'
            )
            try:
                db.session.rollback()
            except Exception as e:
                log_error(
                    ErrorCategory.DB_QUERY,
                    f'Background translation rollback 失败 for book {book_id}: {e}',
                    level='warning',
                )

    def _hydrate_language_pack(self, books: list[NewBook]) -> None:
        try:
            self._language_pack.hydrate_books(books)
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'新书语言包补齐跳过: {e}', level='debug')

    def _translate_and_store_language_pack(self, books: list[NewBook], translate: bool = True) -> dict[str, int]:
        if not books:
            return {
                'books_seen': 0,
                'books_missing': 0,
                'fields_from_pack': 0,
                'fields_stored': 0,
                'fields_translated': 0,
                'failures': 0,
                'pack_writes': 0,
            }

        translator = self._translator if translate else None
        try:
            stats = self._language_pack.translate_and_store_books(books, translator=translator)
            logger.info(
                '新书语言包同步完成: 触达%s本, 新翻译字段%s个, 写入%s次',
                stats.get('books_seen', 0),
                stats.get('fields_translated', 0),
                stats.get('pack_writes', 0),
            )
            return stats
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'新书语言包同步失败: {e}', level='warning')
            return {
                'books_seen': len(books),
                'books_missing': 0,
                'fields_from_pack': 0,
                'fields_stored': 0,
                'fields_translated': 0,
                'failures': len(books),
                'pack_writes': 0,
            }
