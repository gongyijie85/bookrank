"""Per-source health counters for site-crawl plans (issue #136 / #121)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..models.database import db
from ..models.new_book import Publisher

FAILURE_THRESHOLD = 3
RECOVERY_THRESHOLD = 2

# Keep in sync with batch_import_service.SOURCE_TO_PUBLISHER_NAME_EN
SOURCE_TO_PUBLISHER_NAME_EN: dict[str, str] = {
    'harpercollins': 'HarperCollins',
}

_SOURCE_BY_NAME_EN = {v: k for k, v in SOURCE_TO_PUBLISHER_NAME_EN.items()}


def publisher_for_source(source_id: str) -> Publisher | None:
    name_en = SOURCE_TO_PUBLISHER_NAME_EN.get(source_id.lower())
    if not name_en:
        return None
    return Publisher.query.filter_by(name_en=name_en).first()  # type: ignore[no-any-return]


def record_plan_failure(
    source_id: str,
    *,
    error_code: str,
    error_summary: str,
) -> None:
    """Count a planned crawl/import failure; degrade after consecutive failures."""
    publisher = publisher_for_source(source_id)
    if publisher is None:
        return
    if publisher.source_status == 'disabled':
        publisher.last_attempt_at = datetime.now(UTC)
        publisher.last_error_code = error_code[:64]
        publisher.last_error_summary = error_summary[:500]
        db.session.commit()
        return

    publisher.consecutive_failures = int(publisher.consecutive_failures or 0) + 1
    publisher.consecutive_successes = 0
    publisher.last_attempt_at = datetime.now(UTC)
    publisher.last_error_code = error_code[:64]
    publisher.last_error_summary = error_summary[:500]
    if publisher.consecutive_failures >= FAILURE_THRESHOLD:
        publisher.source_status = 'degraded'
    db.session.commit()


def record_plan_success(source_id: str, *, batch_id: str | None) -> None:
    """Count a planned success (applied envelope, including empty legal zero)."""
    publisher = publisher_for_source(source_id)
    if publisher is None:
        return

    publisher.last_attempt_at = datetime.now(UTC)
    publisher.last_error_code = None
    publisher.last_error_summary = None
    if batch_id:
        publisher.last_success_batch_id = batch_id

    if publisher.source_status == 'disabled':
        # success while disabled does not auto-enable
        db.session.commit()
        return

    publisher.consecutive_failures = 0
    publisher.consecutive_successes = int(publisher.consecutive_successes or 0) + 1

    if publisher.source_status == 'degraded':
        if publisher.consecutive_successes >= RECOVERY_THRESHOLD:
            publisher.source_status = 'healthy'
        else:
            publisher.source_status = 'recovering'
    elif publisher.source_status == 'recovering':
        if publisher.consecutive_successes >= RECOVERY_THRESHOLD:
            publisher.source_status = 'healthy'
    else:
        publisher.source_status = 'healthy'

    db.session.commit()


def list_source_health() -> list[dict[str, Any]]:
    """Return health snapshots for publishers that participate in site crawl map."""
    rows: list[dict[str, Any]] = []
    for source_id, name_en in SOURCE_TO_PUBLISHER_NAME_EN.items():
        pub = Publisher.query.filter_by(name_en=name_en).first()
        if pub is None:
            rows.append(
                {
                    'source_id': source_id,
                    'name_en': name_en,
                    'registered': False,
                }
            )
            continue
        rows.append(
            {
                'source_id': source_id,
                'name_en': pub.name_en,
                'registered': True,
                'source_status': pub.source_status,
                'consecutive_failures': pub.consecutive_failures,
                'consecutive_successes': pub.consecutive_successes,
                'last_success_batch_id': pub.last_success_batch_id,
                'last_attempt_at': pub.last_attempt_at.isoformat() if pub.last_attempt_at else None,
                'last_error_code': getattr(pub, 'last_error_code', None),
                'last_error_summary': getattr(pub, 'last_error_summary', None),
                'site_crawl_enabled': pub.site_crawl_enabled,
                'site_import_enabled': pub.site_import_enabled,
                'site_display_primary': pub.site_display_primary,
                'fallback_google_enabled': pub.fallback_google_enabled,
            }
        )
    # Also include other publishers with non-default health fields for ops visibility
    for pub in Publisher.query.order_by(Publisher.name_en).all():
        if pub.name_en in SOURCE_TO_PUBLISHER_NAME_EN.values():
            continue
        rows.append(
            {
                'source_id': _SOURCE_BY_NAME_EN.get(pub.name_en),
                'name_en': pub.name_en,
                'registered': True,
                'source_status': pub.source_status,
                'consecutive_failures': pub.consecutive_failures,
                'consecutive_successes': pub.consecutive_successes,
                'last_success_batch_id': pub.last_success_batch_id,
                'last_attempt_at': pub.last_attempt_at.isoformat() if pub.last_attempt_at else None,
                'last_error_code': getattr(pub, 'last_error_code', None),
                'last_error_summary': getattr(pub, 'last_error_summary', None),
                'site_crawl_enabled': pub.site_crawl_enabled,
                'site_import_enabled': pub.site_import_enabled,
                'site_display_primary': pub.site_display_primary,
                'fallback_google_enabled': pub.fallback_google_enabled,
            }
        )
    return rows
