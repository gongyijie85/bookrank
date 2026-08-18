"""Export import-shaped batch drafts from no-write observation reports.

Never enables writes. Never imports Flask, SQLAlchemy, or production secrets.
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from .contracts import BookObservation, ObservationReport
from .harpercollins import observe_fixture_manifest


def export_batch_draft(
    report: ObservationReport,
    *,
    produced_at: datetime,
    run_date: str,
    producer: str,
) -> dict[str, Any]:
    """Map an observation report to a crawl-batch draft for a later import phase."""
    if not isinstance(report, ObservationReport):
        raise TypeError('export_batch_draft expects an ObservationReport')
    if not isinstance(produced_at, datetime):
        raise TypeError('produced_at must be a datetime')

    records = [_book_to_record(book) for book in report.records]
    body_for_digest = {
        'source_id': report.source,
        'schema_version': report.schema_version,
        'records': records,
        'candidate_urls': list(report.candidate_urls),
        'manifest_sha256': report.manifest_sha256,
    }
    content_sha256 = sha256(
        json.dumps(body_for_digest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    batch_id = f'{report.source}:{run_date}:{content_sha256[:16]}'

    return {
        'batch_id': batch_id,
        'schema_version': report.schema_version,
        'source_id': report.source,
        'produced_at': produced_at.isoformat(),
        'producer': producer,
        'content_sha256': content_sha256,
        'write_enabled': False,
        'records': records,
        'candidate_urls': list(report.candidate_urls),
        'ai_fallback_calls': report.ai_fallback_calls,
        'unverified_ai_candidates': [
            {
                'selector_kind': item.selector_kind,
                'selector': item.selector,
                'reason': item.reason,
                'verified': item.verified,
            }
            for item in report.unverified_ai_candidates
        ],
        'evidence_summary': {
            'count': len(report.evidence),
            'statuses': sorted({item.status.value for item in report.evidence}),
            'manifest_sha256': report.manifest_sha256,
        },
        'empty_result': report.empty_result,
    }


def observe_fixture_manifest_as_batch_draft(
    manifest_path: str | Path,
    *,
    produced_at: datetime,
    run_date: str,
    producer: str,
) -> dict[str, Any]:
    """Run fixture observation then export a no-write batch draft."""
    path = Path(manifest_path)
    report = observe_fixture_manifest(path)
    return export_batch_draft(
        report,
        produced_at=produced_at,
        run_date=run_date,
        producer=producer,
    )


def _book_to_record(book: BookObservation) -> dict[str, Any]:
    main_isbn = next((edition.isbn13 for edition in book.editions if edition.is_main), None)
    provenance: list[dict[str, Any]] = [
        {
            'field': 'title',
            'source_kind': '官网记录',
            'source_url': book.source_url,
            'observed_at': None,
            'method': 'product_json',
        }
    ]
    if book.author is not None:
        provenance.append(
            {
                'field': 'author',
                'source_kind': '官网记录',
                'source_url': book.source_url,
                'observed_at': None,
                'method': 'product_json',
            }
        )
    return {
        'title': book.title,
        'author': book.author,
        'isbn13': main_isbn,
        'source_url': book.source_url,
        'publication_date': book.publication_date,
        'missing_fields': list(book.missing_fields),
        'editions': [
            {
                'format': edition.format,
                'isbn13': edition.isbn13,
                'is_main': edition.is_main,
            }
            for edition in book.editions
        ],
        'field_provenance': provenance,
    }
