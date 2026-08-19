"""Import crawl batches into NewBook cards (#134 + #135 grading/merge + #136 health hooks)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..models.database import db
from ..models.new_book import BatchImportReceipt, NewBook, Publisher
from .publisher_observer.harpercollins import is_valid_isbn13

BATCH_MAX_AGE = timedelta(hours=48)
RECENCY_WINDOW_DAYS = 30

SOURCE_TO_PUBLISHER_NAME_EN: dict[str, str] = {
    'harpercollins': 'HarperCollins',
}

ALLOWED_SCHEMA_PREFIXES = ('hc-observer-',)

_SOURCE_KIND_RANK = {
    '官网记录': 3,
    '官方数据接口': 2,
    '补全来源': 1,
}

_PRINT_RANK = {
    'hardcover': 0,
    'hardback': 0,
    'trade paperback': 1,
    'paperback': 1,
    'softcover': 1,
    'large print': 2,
}

_NON_PRINT = frozenset(
    {
        'e-book',
        'ebook',
        'electronic',
        'kindle',
        'audiobook',
        'audio',
        'cd',
        'mp3',
    }
)


class BatchImportError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class _BatchLookup:
    """批级书籍索引：一次性预载出版社书籍，避免每条 record 全表扫描。"""

    def __init__(self, publisher: Publisher) -> None:
        self._by_isbn: dict[str, NewBook] = {}
        self._by_url: dict[str, NewBook] = {}
        for book in NewBook.query.filter_by(publisher_id=publisher.id).all():
            self._index(book)

    def _index(self, book: NewBook) -> None:
        if book.isbn13:
            self._by_isbn.setdefault(book.isbn13, book)
        for url in (book.canonical_source_url, book.source_url):
            key = normalize_source_url(url)
            if key:
                self._by_url.setdefault(key, book)

    def find(self, *, isbn13: str | None, source_url: str | None) -> NewBook | None:
        if isbn13:
            found = self._by_isbn.get(isbn13)
            if found is not None:
                return found
        if source_url:
            return self._by_url.get(source_url)
        return None

    def register_written(self, book: NewBook) -> None:
        """新建/更新后的 book 重新入索引，供同批后续 record 命中。"""
        self._index(book)


@dataclass(frozen=True)
class BatchImportResult:
    status: str
    receipt: dict[str, Any]
    http_status: int = 200


def import_batch(payload: dict[str, Any]) -> BatchImportResult:
    """Validate and apply one publisher batch; update source health on outcome."""
    from . import source_health_service

    source_id_for_health: str | None = None
    try:
        batch_id = _require_str(payload, 'batch_id')
        source_id = _require_str(payload, 'source_id').lower()
        source_id_for_health = source_id
        schema_version = _require_str(payload, 'schema_version')
        produced_at_raw = _require_str(payload, 'produced_at')
        content_sha256 = _require_str(payload, 'content_sha256').lower()
        records = payload.get('records')
        if not isinstance(records, list):
            raise BatchImportError('SCHEMA_INVALID', 'records must be a list', 400)

        if not any(schema_version.startswith(prefix) for prefix in ALLOWED_SCHEMA_PREFIXES):
            raise BatchImportError('SCHEMA_INVALID', f'unsupported schema_version: {schema_version}', 400)

        if source_id not in SOURCE_TO_PUBLISHER_NAME_EN:
            raise BatchImportError('SOURCE_MISMATCH', f'unsupported source_id: {source_id}', 400)

        if not batch_id.startswith(f'{source_id}:'):
            raise BatchImportError('SCHEMA_INVALID', 'batch_id must start with source_id', 400)

        produced_at = _parse_produced_at(produced_at_raw)
        now = datetime.now(UTC)
        if produced_at > now + timedelta(minutes=5):
            raise BatchImportError('SCHEMA_INVALID', 'produced_at is in the future', 400)
        if now - produced_at > BATCH_MAX_AGE:
            raise BatchImportError('EXPIRED', 'batch produced_at is older than 48 hours', 400)

        expected_digest = compute_content_sha256(source_id, schema_version, records)
        if content_sha256 != expected_digest:
            raise BatchImportError('DIGEST_MISMATCH', 'content_sha256 does not match payload', 409)

        existing = db.session.get(BatchImportReceipt, batch_id)
        if existing is not None:
            if existing.content_sha256 != content_sha256:
                raise BatchImportError(
                    'DIGEST_MISMATCH',
                    'batch_id already applied with different content',
                    409,
                )
            receipt = existing.to_dict()
            receipt['status'] = 'duplicate'
            # duplicate is not a plan failure (#121 / #136)
            return BatchImportResult(status='duplicate', receipt=receipt, http_status=200)

        publisher = Publisher.query.filter_by(name_en=SOURCE_TO_PUBLISHER_NAME_EN[source_id]).first()
        if publisher is None:
            raise BatchImportError('SOURCE_MISMATCH', f'publisher not registered for {source_id}', 400)

        if not bool(publisher.site_import_enabled):
            raise BatchImportError(
                'IMPORT_DISABLED',
                f'site_import_enabled is false for {source_id}',
                403,
            )

        record_results: list[dict[str, Any]] = []
        accepted = 0
        pending_review = 0
        rejected = 0
        lookup = _BatchLookup(publisher)
        for index, raw in enumerate(records):
            if not isinstance(raw, dict):
                rejected += 1
                record_results.append({'index': index, 'outcome': 'rejected', 'reason': 'not_an_object'})
                continue
            if raw.get('ai_unverified') is True or raw.get('from_ai_candidate') is True:
                rejected += 1
                record_results.append({'index': index, 'outcome': 'rejected', 'reason': 'ai_candidate_not_allowed'})
                continue
            outcome = _apply_record(publisher, raw, batch_id, lookup)
            record_results.append({'index': index, **outcome})
            if outcome['outcome'] == 'accepted':
                accepted += 1
            elif outcome['outcome'] == 'pending_review':
                pending_review += 1
            else:
                rejected += 1

        receipt = {
            'batch_id': batch_id,
            'status': 'applied',
            'source_id': source_id,
            'schema_version': schema_version,
            'content_sha256': content_sha256,
            'counts': {
                'records': len(records),
                'accepted': accepted,
                'rejected': rejected,
                'pending_review': pending_review,
            },
            'record_results': record_results,
        }
        row = BatchImportReceipt(
            batch_id=batch_id,
            content_sha256=content_sha256,
            source_id=source_id,
            status='applied',
            receipt_json=json.dumps(receipt, ensure_ascii=False),
        )
        db.session.add(row)
        db.session.commit()
        source_health_service.record_plan_success(source_id, batch_id=batch_id)
        from . import pilot_gate_service

        pilot_gate_service.record_evidence_run(source_id, success=True, batch_id=batch_id)
        return BatchImportResult(status='applied', receipt=receipt, http_status=200)
    except BatchImportError as exc:
        if source_id_for_health:
            source_health_service.record_plan_failure(
                source_id_for_health,
                error_code=exc.code,
                error_summary=exc.message,
            )
            from . import pilot_gate_service

            pilot_gate_service.record_evidence_run(
                source_id_for_health,
                success=False,
                error_code=exc.code,
            )
        raise


def compute_content_sha256(source_id: str, schema_version: str, records: list[Any]) -> str:
    body = {
        'source_id': source_id,
        'schema_version': schema_version,
        'records': records,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()


def normalize_source_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip() or None
    path = parts.path.rstrip('/') or '/'
    host = parts.netloc.lower()
    return urlunsplit((parts.scheme.lower(), host, path, '', ''))


def choose_main_edition(editions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick print main edition: Hardcover > Paperback > Large Print; never e/audio."""
    print_editions: list[tuple[int, dict[str, Any]]] = []
    for edition in editions:
        fmt = str(edition.get('format') or '').strip().lower()
        if fmt in _NON_PRINT:
            continue
        rank = _PRINT_RANK.get(fmt, 50)
        isbn = str(edition.get('isbn13') or '')
        if isbn and not is_valid_isbn13(isbn):
            continue
        print_editions.append((rank, edition))
    if not print_editions:
        return None
    print_editions.sort(key=lambda item: (item[0], str(item[1].get('isbn13') or '')))
    return print_editions[0][1]


def _apply_record(
    publisher: Publisher,
    raw: dict[str, Any],
    batch_id: str,
    lookup: _BatchLookup,
) -> dict[str, Any]:
    title = (raw.get('title') or '').strip()
    author_raw = raw.get('author')
    author = (author_raw or '').strip() if author_raw is not None else ''
    source_url = normalize_source_url((raw.get('source_url') or '').strip() or None)
    editions = _normalize_editions(raw.get('editions'))
    main = choose_main_edition(editions)
    isbn13 = (raw.get('isbn13') or '').strip() or None
    if main and main.get('isbn13'):
        isbn13 = str(main['isbn13'])
    if isbn13 and not is_valid_isbn13(isbn13):
        return {'outcome': 'rejected', 'reason': 'invalid_isbn13'}

    if not title:
        return {'outcome': 'rejected', 'reason': 'missing_title'}
    if not isbn13 and not source_url:
        return {'outcome': 'rejected', 'reason': 'missing_identity'}

    publication_date = _parse_date(raw.get('publication_date'))
    missing = list(raw.get('missing_fields') or [])
    if not author and 'author' not in missing:
        missing.append('author')
    if publication_date is None and 'publication_date' not in missing:
        missing.append('publication_date')

    grade = _grade_record(
        title=title,
        author=author,
        isbn13=isbn13,
        source_url=source_url,
        publication_date=publication_date,
        main=main,
    )
    if grade == 'rejected':
        return {'outcome': 'rejected', 'reason': 'failed_display_gate', 'missing_fields': missing}

    # Mark main flags on editions list
    if main is not None:
        main_isbn = str(main.get('isbn13') or '')
        for edition in editions:
            edition['is_main'] = str(edition.get('isbn13') or '') == main_isbn and _is_print_format(
                str(edition.get('format') or '')
            )
    elif editions:
        for edition in editions:
            edition['is_main'] = False

    provenance = _normalize_provenance(raw.get('field_provenance'))
    book = _find_existing(lookup, isbn13=isbn13, source_url=source_url)

    if grade == 'pending_review':
        return _write_pending(
            publisher,
            book,
            title=title,
            author=author,
            isbn13=isbn13,
            source_url=source_url,
            publication_date=publication_date,
            editions=editions,
            provenance=provenance,
            missing=missing,
            batch_id=batch_id,
            lookup=lookup,
        )

    return _write_accepted(
        publisher,
        book,
        title=title,
        author=author,
        isbn13=isbn13,
        source_url=source_url,
        publication_date=publication_date,
        editions=editions,
        provenance=provenance,
        batch_id=batch_id,
        lookup=lookup,
    )


def _grade_record(
    *,
    title: str,
    author: str,
    isbn13: str | None,
    source_url: str | None,
    publication_date: date | None,
    main: dict[str, Any] | None,
) -> str:
    if not title:
        return 'rejected'
    has_identity = bool(isbn13) or bool(source_url)
    if not has_identity:
        return 'rejected'
    if not author or publication_date is None or not isbn13 or not source_url or main is None:
        if has_identity and title:
            return 'pending_review'
        return 'rejected'
    if not _is_within_recency(publication_date):
        return 'pending_review'
    return 'accepted'


def _write_accepted(
    publisher: Publisher,
    book: NewBook | None,
    *,
    title: str,
    author: str,
    isbn13: str | None,
    source_url: str | None,
    publication_date: date | None,
    editions: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
    batch_id: str,
    lookup: _BatchLookup,
) -> dict[str, Any]:
    displayable = bool(publisher.site_display_primary)
    if book is None:
        book = NewBook(
            publisher_id=publisher.id,
            title=title,
            author=author,
            isbn13=isbn13,
            source_url=source_url,
            publication_date=publication_date,
            is_displayable=displayable,
            is_verified=False,
        )
        db.session.add(book)
    else:
        _merge_fields(book, title=title, author=author, publication_date=publication_date, provenance=provenance)
        if isbn13:
            book.isbn13 = isbn13
        if source_url:
            book.source_url = source_url
        book.is_displayable = displayable

    book.canonical_source_url = source_url
    book.last_import_batch_id = batch_id
    book.set_editions(_merge_edition_lists(book.get_editions(), editions))
    book.set_field_provenance(_merge_provenance(book.get_field_provenance(), provenance))
    lookup.register_written(book)
    return {'outcome': 'accepted', 'isbn13': isbn13, 'source_url': source_url}


def _write_pending(
    publisher: Publisher,
    book: NewBook | None,
    *,
    title: str,
    author: str,
    isbn13: str | None,
    source_url: str | None,
    publication_date: date | None,
    editions: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
    missing: list[str],
    batch_id: str,
    lookup: _BatchLookup,
) -> dict[str, Any]:
    # ORM requires non-null author: store empty string, never invent a name.
    store_author = author if author else ''
    if book is None:
        book = NewBook(
            publisher_id=publisher.id,
            title=title,
            author=store_author,
            isbn13=isbn13,
            source_url=source_url,
            publication_date=publication_date,
            is_displayable=False,
            is_verified=False,
        )
        db.session.add(book)
    else:
        # Do not clobber successful displayable fields with empty pending values
        if title:
            book.title = title
        if author:
            book.author = author
        if isbn13 and not book.isbn13:
            book.isbn13 = isbn13
        if source_url and not book.source_url:
            book.source_url = source_url
        if publication_date is not None and book.publication_date is None:
            book.publication_date = publication_date
        if book.is_displayable:
            # keep displayable if already accepted previously
            pass
        else:
            book.is_displayable = False

    book.canonical_source_url = book.canonical_source_url or source_url
    book.last_import_batch_id = batch_id
    book.set_editions(_merge_edition_lists(book.get_editions(), editions))
    book.set_field_provenance(_merge_provenance(book.get_field_provenance(), provenance))
    lookup.register_written(book)
    return {
        'outcome': 'pending_review',
        'isbn13': isbn13,
        'source_url': source_url,
        'missing_fields': missing,
    }


def _find_existing(
    lookup: _BatchLookup,
    *,
    isbn13: str | None,
    source_url: str | None,
) -> NewBook | None:
    return lookup.find(isbn13=isbn13, source_url=source_url)


def _merge_edition_lists(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_isbn: dict[str, dict[str, Any]] = {}
    for edition in existing + incoming:
        isbn = str(edition.get('isbn13') or '')
        if not isbn:
            continue
        by_isbn[isbn] = {
            'format': edition.get('format') or '',
            'isbn13': isbn,
            'is_main': bool(edition.get('is_main')),
        }
    merged = list(by_isbn.values())
    main = choose_main_edition(merged)
    main_isbn = str(main.get('isbn13') or '') if main else ''
    for edition in merged:
        edition['is_main'] = edition.get('isbn13') == main_isbn
    return merged


def _merge_fields(
    book: NewBook,
    *,
    title: str,
    author: str,
    publication_date: date | None,
    provenance: list[dict[str, Any]],
) -> None:
    prov_by_field = {str(item.get('field')): item for item in provenance}
    existing_prov = {str(item.get('field')): item for item in book.get_field_provenance()}

    def _can_overwrite(field: str) -> bool:
        new_item = prov_by_field.get(field)
        old_item = existing_prov.get(field)
        if new_item is None:
            return True
        if old_item is None:
            return True
        new_rank = _SOURCE_KIND_RANK.get(str(new_item.get('source_kind') or ''), 0)
        old_rank = _SOURCE_KIND_RANK.get(str(old_item.get('source_kind') or ''), 0)
        return new_rank >= old_rank

    if title and _can_overwrite('title'):
        book.title = title
    if author and _can_overwrite('author'):
        book.author = author
    if publication_date is not None and _can_overwrite('publication_date'):
        book.publication_date = publication_date


def _merge_provenance(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_field: dict[str, dict[str, Any]] = {}
    for item in existing + incoming:
        field = str(item.get('field') or '')
        if not field:
            continue
        prev = by_field.get(field)
        if prev is None:
            by_field[field] = item
            continue
        new_rank = _SOURCE_KIND_RANK.get(str(item.get('source_kind') or ''), 0)
        old_rank = _SOURCE_KIND_RANK.get(str(prev.get('source_kind') or ''), 0)
        if new_rank >= old_rank:
            by_field[field] = item
    return list(by_field.values())


def _normalize_editions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                'format': str(item.get('format') or ''),
                'isbn13': str(item.get('isbn13') or ''),
                'is_main': bool(item.get('is_main')),
            }
        )
    return result


def _normalize_provenance(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _is_print_format(fmt: str) -> bool:
    key = fmt.strip().lower()
    return key not in _NON_PRINT and (key in _PRINT_RANK or bool(key))


def _is_within_recency(value: date) -> bool:
    today = date.today()
    delta = (today - value).days
    return 0 <= delta <= RECENCY_WINDOW_DAYS


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BatchImportError('SCHEMA_INVALID', f'missing or invalid field: {key}', 400)
    return value.strip()


def _parse_produced_at(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError as exc:
        raise BatchImportError('SCHEMA_INVALID', 'produced_at must be ISO-8601', 400) from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_date(raw: Any) -> date | None:
    if raw is None or raw == '':
        return None
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError:
        return None
