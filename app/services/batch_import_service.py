"""Import crawl batches into NewBook cards (issue #134).

Auth and HTTP live in the route layer. This module validates envelopes,
enforces batch_id idempotency, and writes minimal accepted records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from ..models.database import db
from ..models.new_book import BatchImportReceipt, NewBook, Publisher
from .publisher_observer.harpercollins import is_valid_isbn13

BATCH_MAX_AGE = timedelta(hours=48)

# source_id (crawl) -> publishers.name_en
SOURCE_TO_PUBLISHER_NAME_EN: dict[str, str] = {
    'harpercollins': 'HarperCollins',
}

ALLOWED_SCHEMA_PREFIXES = ('hc-observer-',)


class BatchImportError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class BatchImportResult:
    status: str
    receipt: dict[str, Any]
    http_status: int = 200


def import_batch(payload: dict[str, Any]) -> BatchImportResult:
    """Validate and apply one publisher batch. Never partially commits on envelope failure."""
    batch_id = _require_str(payload, 'batch_id')
    source_id = _require_str(payload, 'source_id').lower()
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
        return BatchImportResult(status='duplicate', receipt=receipt, http_status=200)

    publisher = Publisher.query.filter_by(name_en=SOURCE_TO_PUBLISHER_NAME_EN[source_id]).first()
    if publisher is None:
        raise BatchImportError('SOURCE_MISMATCH', f'publisher not registered for {source_id}', 400)

    record_results: list[dict[str, Any]] = []
    accepted = 0
    rejected = 0
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            rejected += 1
            record_results.append({'index': index, 'outcome': 'rejected', 'reason': 'not_an_object'})
            continue
        outcome = _upsert_record(publisher, raw, batch_id)
        record_results.append({'index': index, 'outcome': outcome['outcome'], **outcome})
        if outcome['outcome'] == 'accepted':
            accepted += 1
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
            'pending_review': 0,
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
    return BatchImportResult(status='applied', receipt=receipt, http_status=200)


def compute_content_sha256(source_id: str, schema_version: str, records: list[Any]) -> str:
    body = {
        'source_id': source_id,
        'schema_version': schema_version,
        'records': records,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()


def _upsert_record(publisher: Publisher, raw: dict[str, Any], batch_id: str) -> dict[str, Any]:
    title = (raw.get('title') or '').strip()
    author = (raw.get('author') or '').strip()
    isbn13 = (raw.get('isbn13') or '').strip() or None
    source_url = (raw.get('source_url') or '').strip() or None
    if not title or not author:
        return {'outcome': 'rejected', 'reason': 'missing_title_or_author'}
    if isbn13 and not is_valid_isbn13(isbn13):
        return {'outcome': 'rejected', 'reason': 'invalid_isbn13'}
    if not isbn13 and not source_url:
        return {'outcome': 'rejected', 'reason': 'missing_identity'}

    book: NewBook | None = None
    if isbn13:
        book = NewBook.query.filter_by(publisher_id=publisher.id, isbn13=isbn13).first()
    if book is None and source_url:
        book = NewBook.query.filter_by(publisher_id=publisher.id, source_url=source_url).first()

    publication_date = _parse_date(raw.get('publication_date'))
    editions_raw = raw.get('editions')
    provenance_raw = raw.get('field_provenance')
    editions: list[dict[str, Any]] = (
        [item for item in editions_raw if isinstance(item, dict)] if isinstance(editions_raw, list) else []
    )
    provenance: list[dict[str, Any]] = (
        [item for item in provenance_raw if isinstance(item, dict)] if isinstance(provenance_raw, list) else []
    )

    if book is None:
        book = NewBook(
            publisher_id=publisher.id,
            title=title,
            author=author,
            isbn13=isbn13,
            source_url=source_url,
            publication_date=publication_date,
            is_displayable=True,
            is_verified=False,
        )
        db.session.add(book)
    else:
        book.title = title
        book.author = author
        if isbn13:
            book.isbn13 = isbn13
        if source_url:
            book.source_url = source_url
        if publication_date is not None:
            book.publication_date = publication_date

    book.canonical_source_url = source_url
    book.last_import_batch_id = batch_id
    book.set_editions(editions)
    book.set_field_provenance(provenance)
    return {'outcome': 'accepted', 'isbn13': isbn13, 'source_url': source_url}


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


def _parse_date(raw: Any) -> Any:
    if raw is None or raw == '':
        return None
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError:
        return None
