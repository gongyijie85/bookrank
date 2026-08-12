"""Source-level feature flags for site crawl path (issue #137)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..models.database import db
from ..models.new_book import NewBook, Publisher
from ..models.schemas import SystemConfig
from .source_health_service import publisher_for_source

_AUDIT_KEY = 'source_control_audit'
_AUDIT_MAX = 100

_FLAG_KEYS = (
    'site_crawl_enabled',
    'site_import_enabled',
    'site_display_primary',
    'fallback_google_enabled',
)


def get_flags(source_id: str) -> dict[str, Any]:
    publisher = publisher_for_source(source_id)
    if publisher is None:
        raise ValueError(f'unknown or unregistered source: {source_id}')
    return {
        'source_id': source_id.lower(),
        'name_en': publisher.name_en,
        'site_crawl_enabled': bool(publisher.site_crawl_enabled),
        'site_import_enabled': bool(publisher.site_import_enabled),
        'site_display_primary': bool(publisher.site_display_primary),
        'fallback_google_enabled': bool(publisher.fallback_google_enabled),
        'source_status': publisher.source_status,
    }


def set_flags(
    source_id: str,
    *,
    actor: str,
    site_crawl_enabled: bool | None = None,
    site_import_enabled: bool | None = None,
    site_display_primary: bool | None = None,
    fallback_google_enabled: bool | None = None,
) -> dict[str, Any]:
    """Update flags without redeploy; audit who/when/what."""
    publisher = publisher_for_source(source_id)
    if publisher is None:
        raise ValueError(f'unknown or unregistered source: {source_id}')

    before = get_flags(source_id)
    changes: dict[str, Any] = {}

    if site_crawl_enabled is not None and site_crawl_enabled != publisher.site_crawl_enabled:
        publisher.site_crawl_enabled = site_crawl_enabled
        changes['site_crawl_enabled'] = site_crawl_enabled
    if site_import_enabled is not None and site_import_enabled != publisher.site_import_enabled:
        publisher.site_import_enabled = site_import_enabled
        changes['site_import_enabled'] = site_import_enabled
    if site_display_primary is not None and site_display_primary != publisher.site_display_primary:
        if site_display_primary:
            from flask import current_app

            from . import pilot_gate_service

            # Enforce pilot/compliance gates outside automated unit tests.
            if not current_app.config.get('TESTING', False):
                allowed, reason = pilot_gate_service.can_enable_display_primary(source_id)
                if not allowed:
                    raise ValueError(reason)
        publisher.site_display_primary = site_display_primary
        changes['site_display_primary'] = site_display_primary
        _apply_display_primary(publisher, site_display_primary)
    if fallback_google_enabled is not None and fallback_google_enabled != publisher.fallback_google_enabled:
        publisher.fallback_google_enabled = fallback_google_enabled
        changes['fallback_google_enabled'] = fallback_google_enabled

    if changes:
        _append_audit(
            {
                'at': datetime.now(UTC).isoformat(),
                'actor': actor,
                'source_id': source_id.lower(),
                'before': {k: before[k] for k in _FLAG_KEYS},
                'changes': changes,
            }
        )
    db.session.commit()
    return get_flags(source_id)


def list_audit(limit: int = 50) -> list[dict[str, Any]]:
    raw = SystemConfig.get_value(_AUDIT_KEY)
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return list(reversed(items[-limit:]))


def _apply_display_primary(publisher: Publisher, enabled: bool) -> None:
    """Site-imported cards follow display_primary; pending_review stays hidden."""
    books = NewBook.query.filter(
        NewBook.publisher_id == publisher.id,
        NewBook.last_import_batch_id.is_not(None),  # type: ignore[union-attr]
    ).all()
    for book in books:
        if not enabled:
            book.is_displayable = False
            continue
        # only re-show accepted-quality cards (have author + date)
        if book.author and book.publication_date is not None and book.isbn13:
            book.is_displayable = True


def _append_audit(entry: dict[str, Any]) -> None:
    raw = SystemConfig.get_value(_AUDIT_KEY)
    try:
        items = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list):
        items = []
    items.append(entry)
    items = items[-_AUDIT_MAX:]
    SystemConfig.set_value(_AUDIT_KEY, json.dumps(items, ensure_ascii=False))


def site_import_allowed(source_id: str) -> bool:
    publisher = publisher_for_source(source_id)
    return bool(publisher and publisher.site_import_enabled)


def site_display_primary(source_id: str) -> bool:
    publisher = publisher_for_source(source_id)
    return bool(publisher and publisher.site_display_primary)
