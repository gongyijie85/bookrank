"""Helpers for GHA observe phase (#138): fixture batch drafts without import secrets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .publisher_observer.batch_draft import observe_fixture_manifest_as_batch_draft

# Path is used at runtime for Path(manifest_path)

_SECRET_ENV_KEYS = frozenset(
    {
        'BATCH_IMPORT_SECRET',
        'CRON_SECRET',
        'ADMIN_SECRET',
        'SECRET_KEY',
        'ZHIPU_API_KEY',
        'NYT_API_KEY',
        'GOOGLE_API_KEY',
        'PRH_API_KEY',
        'DATABASE_URL',
    }
)


def redact_secrets_from_env(env: dict[str, str]) -> dict[str, str]:
    """Return env without import/production secrets (for observe-phase jobs)."""
    return {key: value for key, value in env.items() if key not in _SECRET_ENV_KEYS}


def build_fixture_batch_draft(
    manifest_path: str | Path,
    *,
    run_date: str,
    producer: str,
    produced_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a no-write batch draft from HarperCollins fixtures for pipeline demos."""
    when = produced_at or datetime.now(UTC)
    path = Path(manifest_path)
    draft = observe_fixture_manifest_as_batch_draft(
        path,
        produced_at=when,
        run_date=run_date,
        producer=producer,
    )
    if draft.get('write_enabled') is not False:
        raise ValueError('pipeline draft must keep write_enabled=false')
    return draft
