"""Server-side book content language-pack hydration."""

import json
import logging
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from ..models.database import db
from ..models.schemas import BookMetadata, TranslationCache
from ..utils.api_helpers import clean_translation_text
from ..utils.error_handler import ErrorCategory, log_error
from .translation_cache_service import TranslationCacheService

logger = logging.getLogger(__name__)


class BookLanguagePack:
    """Apply pre-translated book fields without doing live translation."""

    _write_lock = threading.RLock()
    _FIELDS = (
        ('title', 'title_zh', 'title'),
        ('description', 'description_zh', 'description'),
        ('details', 'details_zh', 'details'),
    )
    _PLACEHOLDERS = {
        'No summary available.',
        'No detailed description available.',
        'Unknown',
        'N/A',
        '暂无简介',
        '暂无详细介绍',
    }

    def __init__(self, pack_path: str | Path | None = None):
        self._pack_path = Path(pack_path) if pack_path else None
        self._pack_mtime: float | None = None
        self._pack_books: dict[str, dict[str, str]] = {}
        self._table_columns_cache: dict[str, set[str]] = {}

    def hydrate_books(self, books: Iterable[Any]) -> None:
        """Fill missing zh fields from DB metadata, static pack, then translation cache."""
        books = list(books)
        if not books:
            return

        isbns = [isbn for isbn in (self._book_isbn(book) for book in books) if isbn]
        if isbns:
            self._apply_isbn_translations(books, self.get_book_metadata_translations(isbns))
            self._apply_isbn_translations(books, self._load_static_pack())

        self._apply_exact_text_cache(books)

    def translate_and_store_books(
        self,
        books: Iterable[Any],
        translator: Any | None = None,
        save_metadata: Callable[..., bool] | None = None,
    ) -> dict[str, int]:
        """Translate missing zh fields and persist them into the static language pack."""
        books = list(books)
        stats = {
            'books_seen': len(books),
            'books_missing': 0,
            'fields_from_pack': 0,
            'fields_stored': 0,
            'fields_translated': 0,
            'failures': 0,
            'pack_writes': 0,
        }
        if not books:
            return stats

        with self._write_lock:
            pack_doc = self._load_pack_document()
            pack_books = pack_doc.setdefault('books', {})
            if not isinstance(pack_books, dict):
                pack_books = {}
                pack_doc['books'] = pack_books

            pack_changed = False
            for book in books:
                isbn = self._book_isbn(book)
                if not isbn:
                    continue

                pack_entry = pack_books.setdefault(isbn, {})
                if not isinstance(pack_entry, dict):
                    pack_entry = {}
                    pack_books[isbn] = pack_entry

                translated_for_metadata: dict[str, str] = {}
                book_had_missing = False

                for source_attr, target_attr, field_type in self._FIELDS:
                    source_text = self._get_value(book, source_attr)
                    if not source_text or self._is_placeholder(source_text):
                        continue

                    object_value = self._get_value(book, target_attr)
                    pack_value = pack_entry.get(target_attr)

                    if object_value:
                        cleaned = clean_translation_text(object_value, field_type)
                        self._set_value(book, target_attr, cleaned)
                        if not pack_value:
                            pack_entry[target_attr] = cleaned
                            pack_changed = True
                            stats['fields_stored'] += 1
                        continue

                    if pack_value:
                        cleaned = clean_translation_text(pack_value, field_type)
                        self._set_value(book, target_attr, cleaned)
                        stats['fields_from_pack'] += 1
                        continue

                    book_had_missing = True
                    if not translator:
                        continue
                    translated = self._translate_field(translator, source_text, field_type)
                    if not translated:
                        stats['failures'] += 1
                        continue

                    cleaned = clean_translation_text(translated, field_type)
                    self._set_value(book, target_attr, cleaned)
                    pack_entry[target_attr] = cleaned
                    translated_for_metadata[target_attr] = cleaned
                    pack_changed = True
                    stats['fields_translated'] += 1

                if book_had_missing:
                    stats['books_missing'] += 1

                if translated_for_metadata and save_metadata:
                    self._save_metadata_translation(isbn, translated_for_metadata, save_metadata)

            if pack_changed and self._pack_path:
                self._write_pack_document(pack_doc)
                stats['pack_writes'] = 1

        return stats

    def store_books(self, books: Iterable[Any]) -> dict[str, int]:
        """Persist existing zh fields from book objects into the language pack."""
        return self.translate_and_store_books(books, translator=None, save_metadata=None)

    def get_book_metadata_translations(self, isbns: list[str]) -> dict[str, dict[str, str | None]]:
        """Read BookMetadata translations while tolerating older schemas."""
        unique_isbns = sorted({isbn for isbn in isbns if isbn})
        if not unique_isbns:
            return {}

        try:
            columns = self._table_columns('book_metadata')
            query_fields: list[Any] = [BookMetadata.isbn]
            for column_name in ('title_zh', 'description_zh', 'details_zh'):
                if column_name in columns:
                    query_fields.append(getattr(BookMetadata, column_name))

            if len(query_fields) == 1:
                return {}

            rows = db.session.query(*query_fields).filter(BookMetadata.isbn.in_(unique_isbns)).all()
            translations: dict[str, dict[str, str | None]] = {}
            for row in rows:
                mapping = row._mapping
                isbn = mapping.get('isbn')
                if not isbn:
                    continue
                translations[isbn] = {
                    'title_zh': mapping.get('title_zh'),
                    'description_zh': mapping.get('description_zh'),
                    'details_zh': mapping.get('details_zh'),
                }
            return translations
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'BookMetadata language-pack lookup skipped: {e}', level='warning')
            try:
                db.session.rollback()
            except Exception as e:
                log_error(ErrorCategory.TRANSLATION, f'BookMetadata rollback 失败: {e}', level='warning')
            return {}

    def _apply_isbn_translations(self, books: list[Any], translations: dict[str, dict[str, str | None]]) -> None:
        if not translations:
            return

        for book in books:
            isbn = self._book_isbn(book)
            data = translations.get(isbn)
            if not data:
                continue
            self._fill_missing(book, data)

    def _apply_exact_text_cache(self, books: list[Any]) -> None:
        source_texts: set[str] = set()
        for book in books:
            for source_attr, target_attr, _field_type in self._FIELDS:
                if self._get_value(book, target_attr):
                    continue
                source_text = self._get_value(book, source_attr)
                if source_text and not self._is_placeholder(source_text):
                    source_texts.add(source_text)

        cached = self._get_cached_translations(source_texts)
        if not cached:
            return

        for book in books:
            for source_attr, target_attr, field_type in self._FIELDS:
                if self._get_value(book, target_attr):
                    continue
                source_text = self._get_value(book, source_attr)
                translated = cached.get(source_text or '')
                if translated:
                    self._set_value(book, target_attr, clean_translation_text(translated, field_type))

    def _get_cached_translations(self, source_texts: set[str]) -> dict[str, str]:
        texts = {text for text in source_texts if text and text.strip()}
        if not texts:
            return {}

        try:
            hash_to_texts: dict[str, set[str]] = {}
            for text in texts:
                source_hash = TranslationCacheService._compute_source_hash(text)
                hash_to_texts.setdefault(source_hash, set()).add(text)

            rows = TranslationCache.query.filter(
                TranslationCache.source_hash.in_(list(hash_to_texts.keys())),
                TranslationCache.source_lang == 'en',
                TranslationCache.target_lang == 'zh',
            ).all()

            translations: dict[str, str] = {}
            for row in rows:
                matching_texts = hash_to_texts.get(row.source_hash, set())
                if row.source_text in matching_texts and row.translated_text:
                    translations[row.source_text] = row.translated_text
            return translations
        except SQLAlchemyError as e:
            log_error(ErrorCategory.TRANSLATION, f'TranslationCache language-pack lookup skipped: {e}', level='warning')
            try:
                db.session.rollback()
            except Exception as e:
                log_error(ErrorCategory.TRANSLATION, f'BookMetadata rollback 失败: {e}', level='warning')
            return {}
        except Exception as e:
            log_error(
                ErrorCategory.TRANSLATION, f'TranslationCache language-pack lookup unavailable: {e}', level='warning'
            )
            return {}

    def _load_static_pack(self) -> dict[str, dict[str, str]]:
        if not self._pack_path or not self._pack_path.exists():
            return {}

        try:
            mtime = self._pack_path.stat().st_mtime
            if self._pack_mtime == mtime:
                return self._pack_books

            raw = json.loads(self._pack_path.read_text(encoding='utf-8'))
            books = raw.get('books', raw) if isinstance(raw, dict) else {}
            if not isinstance(books, dict):
                books = {}

            normalized: dict[str, dict[str, str]] = {}
            for isbn, values in books.items():
                if isinstance(values, dict):
                    normalized[str(isbn)] = {
                        key: str(value)
                        for key, value in values.items()
                        if key in {'title_zh', 'description_zh', 'details_zh'} and value
                    }

            self._pack_mtime = mtime
            self._pack_books = normalized
            return self._pack_books
        except Exception as e:
            log_error(
                ErrorCategory.TRANSLATION, f'Failed to load book language pack {self._pack_path}: {e}', level='warning'
            )
            self._pack_mtime = None
            self._pack_books = {}
            return {}

    def _load_pack_document(self) -> dict[str, Any]:
        default_doc = {
            'version': 1,
            'locale': 'zh',
            'updated_at': datetime.now(UTC).isoformat(),
            'description': (
                'Chinese book-content language pack. Server code hydrates these fields before rendering '
                'so language switching does not require live translation.'
            ),
            'books': {},
        }

        if not self._pack_path or not self._pack_path.exists():
            return default_doc

        try:
            raw = json.loads(self._pack_path.read_text(encoding='utf-8'))
        except Exception as e:
            log_error(
                ErrorCategory.TRANSLATION,
                f'Failed to load writable book language pack {self._pack_path}: {e}',
                level='warning',
            )
            return default_doc

        if not isinstance(raw, dict):
            return default_doc

        raw.setdefault('version', 1)
        raw.setdefault('locale', 'zh')
        raw.setdefault('description', default_doc['description'])
        if not isinstance(raw.get('books'), dict):
            raw['books'] = {}
        return raw

    def _write_pack_document(self, pack_doc: dict[str, Any]) -> None:
        if not self._pack_path:
            return

        self._pack_path.parent.mkdir(parents=True, exist_ok=True)
        pack_doc['updated_at'] = datetime.now(UTC).isoformat()

        tmp_path = self._pack_path.with_name(f'{self._pack_path.name}.tmp')
        tmp_path.write_text(json.dumps(pack_doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        tmp_path.replace(self._pack_path)

        self._pack_mtime = None
        self._pack_books = {}

    def _fill_missing(self, book: Any, data: dict[str, str | None]) -> None:
        for _source_attr, target_attr, field_type in self._FIELDS:
            if self._get_value(book, target_attr):
                continue
            value = data.get(target_attr)
            if value:
                self._set_value(book, target_attr, clean_translation_text(value, field_type))

    @staticmethod
    def _book_isbn(book: Any) -> str:
        if isinstance(book, dict):
            return str(book.get('isbn13') or book.get('isbn10') or book.get('id') or '')
        return str(getattr(book, 'isbn13', None) or getattr(book, 'isbn10', None) or getattr(book, 'id', '') or '')

    @classmethod
    def _is_placeholder(cls, text: str) -> bool:
        return text.strip() in cls._PLACEHOLDERS

    def _table_columns(self, table_name: str) -> set[str]:
        if table_name in self._table_columns_cache:
            return self._table_columns_cache[table_name]
        inspector = inspect(db.engine)
        columns = {column['name'] for column in inspector.get_columns(table_name)}
        self._table_columns_cache[table_name] = columns
        return columns

    @staticmethod
    def _get_value(book: Any, attr: str) -> str:
        value = book.get(attr) if isinstance(book, dict) else getattr(book, attr, None)
        if value is None:
            return ''
        return str(value).strip()

    @staticmethod
    def _set_value(book: Any, attr: str, value: str) -> None:
        if isinstance(book, dict):
            book[attr] = value
        elif hasattr(book, attr):
            setattr(book, attr, value)

    @staticmethod
    def _translate_field(translator: Any | None, text: str, field_type: str) -> str | None:
        if not translator or not hasattr(translator, 'translate'):
            return None
        try:
            return translator.translate(text, 'en', 'zh', field_type=field_type)
        except TypeError:
            return translator.translate(text, source_lang='en', target_lang='zh', field_type=field_type)
        except Exception as e:
            log_error(
                ErrorCategory.TRANSLATION, f'Language-pack translation failed for {field_type}: {e}', level='warning'
            )
            return None

    @staticmethod
    def _save_metadata_translation(
        isbn: str,
        translations: dict[str, str],
        save_metadata: Callable[..., bool],
    ) -> None:
        try:
            save_metadata(
                isbn=isbn,
                title_zh=translations.get('title_zh'),
                description_zh=translations.get('description_zh'),
                details_zh=translations.get('details_zh'),
            )
        except TypeError:
            save_metadata(
                isbn,
                translations.get('title_zh'),
                translations.get('description_zh'),
                translations.get('details_zh'),
            )
        except Exception as e:
            log_error(
                ErrorCategory.TRANSLATION, f'Saving language-pack metadata failed for {isbn}: {e}', level='warning'
            )
