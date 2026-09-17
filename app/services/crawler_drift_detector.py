"""Crawler selector drift detection (ROADMAP v1.0 #2).

Detects publishers whose sync results repeatedly indicate data-source
instability (empty / partial_failure / timeout / request_failed), likely
caused by selector drift or upstream API changes.

Evidence source: `last_auto_sync_result` SystemConfig (persisted by
`run_auto_sync`). Read-only: this module never mutates sync state.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..models.schemas import SystemConfig

# Drift-indicating sync statuses (sync_engine result contract).
_DRIFT_STATUSES = ('empty', 'partial_failure', 'timeout', 'request_failed')

# A publisher is a drift suspect when >= 2 of its last N observed results
# show a drift-indicating status, or when it was 'empty' once after having
# published books before.
_DRIFT_RATIO_THRESHOLD = 2
_LOOKBACK = 5


class DriftCandidate:
    """One publisher flagged as a possible selector-drift victim."""

    def __init__(self, publisher: str, observations: list[dict[str, Any]], reasons: list[str]) -> None:
        self.publisher = publisher
        self.observations = observations
        self.reasons = reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            'publisher': self.publisher,
            'reasons': self.reasons,
            'observations': self.observations[-_LOOKBACK:],
        }


def _load_last_result() -> dict[str, Any] | None:
    raw = SystemConfig.get_value('last_auto_sync_result')
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def detect_drift(recent_results: list[dict[str, Any]] | None = None) -> list[DriftCandidate]:
    """Scan recent sync results for recurring drift symptoms.

    Args:
        recent_results: list of per-publisher summary dicts (each with
            'publisher' and 'status'). Defaults to the latest
            `last_auto_sync_result` snapshot from SystemConfig.

    Returns:
        List of DriftCandidate (one per suspicious publisher).
    """
    if recent_results is None:
        result = _load_last_result()
        if result is None:
            return []
        recent_results = result.get('publishers', [])

    by_publisher: dict[str, list[dict[str, Any]]] = {}
    for entry in recent_results:
        name = entry.get('publisher')
        if not name:
            continue
        by_publisher.setdefault(name, []).append(entry)

    candidates: list[DriftCandidate] = []
    for name, obs in by_publisher.items():
        reasons: list[str] = []
        drift_count = sum(1 for o in obs if o.get('status') in _DRIFT_STATUSES)
        total = len(obs)
        if drift_count >= _DRIFT_RATIO_THRESHOLD:
            reasons.append(f'{drift_count}/{total} 次同步异常')
        elif total > 0 and drift_count == 1 and obs[-1].get('status') == 'empty':
            reasons.append('最近一次同步为空结果（可能数据源失效或选择器漂移）')
        if reasons:
            candidates.append(DriftCandidate(name, obs, reasons))

    return candidates


def drift_report() -> dict[str, Any]:
    """Full report for the admin endpoint & alert job.

    Returns:
        {drifted: [...], total_publishers: N, observed_at: iso}
    """
    result = _load_last_result()
    if result is None:
        return {'drifted': [], 'total_publishers': 0, 'observed_at': None}
    candidates = detect_drift(result.get('publishers'))
    finished_at = result.get('finished_at')
    parsed = None
    if finished_at:
        try:
            parsed = datetime.fromisoformat(finished_at).isoformat()
        except ValueError:
            parsed = finished_at
    return {
        'drifted': [c.to_dict() for c in candidates],
        'total_publishers': len(result.get('publishers', [])),
        'observed_at': parsed,
    }
