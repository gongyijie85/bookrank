"""Pilot evidence, quality gates, and no-redeploy rollback drill (#140 / #123)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from ..models.database import db
from ..models.schemas import SystemConfig
from . import source_control_service
from .source_health_service import publisher_for_source

_EVIDENCE_PREFIX = 'pilot_evidence:'
_COMPLIANCE_KEY = 'pilot_compliance_go'
_DRILL_PREFIX = 'pilot_last_drill:'

MIN_PLANNED_RUNS = 10
MIN_WINDOW_DAYS = 14
MIN_SUCCESS_RATE = 0.80
MAX_DEGRADED_EPISODES = 1


def record_evidence_run(
    source_id: str,
    *,
    success: bool,
    batch_id: str | None = None,
    error_code: str | None = None,
    at: datetime | None = None,
) -> None:
    when = at or datetime.now(UTC)
    items = _load_evidence(source_id)
    items.append(
        {
            'at': when.astimezone(UTC).isoformat(),
            'success': bool(success),
            'batch_id': batch_id,
            'error_code': error_code,
        }
    )
    # keep ~60 days
    cutoff = datetime.now(UTC) - timedelta(days=60)
    pruned: list[dict[str, Any]] = []
    for item in items:
        try:
            ts = datetime.fromisoformat(str(item['at']).replace('Z', '+00:00'))
        except (KeyError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts >= cutoff:
            pruned.append(item)
    SystemConfig.set_value(_evidence_key(source_id), json.dumps(pruned, ensure_ascii=False))
    db.session.commit()


def set_compliance_go(source_id: str, go: bool, *, actor: str) -> None:
    data = _load_compliance()
    data[source_id.lower()] = {
        'go': bool(go),
        'actor': actor,
        'at': datetime.now(UTC).isoformat(),
    }
    SystemConfig.set_value(_COMPLIANCE_KEY, json.dumps(data, ensure_ascii=False))
    db.session.commit()


def get_compliance_go(source_id: str) -> bool:
    data = _load_compliance()
    entry = data.get(source_id.lower()) or {}
    return bool(entry.get('go'))


def evaluate_gates(source_id: str) -> dict[str, Any]:
    items = _load_evidence(source_id)
    failures: list[str] = []
    now = datetime.now(UTC)
    times: list[datetime] = []
    success_count = 0
    for item in items:
        try:
            ts = datetime.fromisoformat(str(item['at']).replace('Z', '+00:00'))
        except (KeyError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        times.append(ts)
        if item.get('success'):
            success_count += 1

    planned = len(times)
    success_rate = (success_count / planned) if planned else 0.0
    window_days = 0.0
    if times:
        window_days = (max(times) - min(times)).total_seconds() / 86400.0

    if planned < MIN_PLANNED_RUNS:
        failures.append(f'计划运行次数 {planned} < {MIN_PLANNED_RUNS}')
    # Inclusive calendar span: runs on day0 and day13 count as 14 calendar days.
    if planned >= MIN_PLANNED_RUNS and window_days + 1 < MIN_WINDOW_DAYS:
        failures.append(f'观察窗约 {window_days + 1:.1f} 天 < {MIN_WINDOW_DAYS} 天')
    if planned and success_rate < MIN_SUCCESS_RATE:
        failures.append(f'成功率 {success_rate:.0%} < {MIN_SUCCESS_RATE:.0%}')

    publisher = publisher_for_source(source_id)
    degraded_episodes = _count_degraded_episodes(items)
    if degraded_episodes > MAX_DEGRADED_EPISODES:
        failures.append(f'降级段次数 {degraded_episodes} > {MAX_DEGRADED_EPISODES}')
    if publisher is not None and publisher.source_status == 'degraded':
        failures.append('评估日来源仍为 degraded')

    return {
        'source_id': source_id.lower(),
        'passed': len(failures) == 0 and planned >= MIN_PLANNED_RUNS,
        'failures': failures,
        'metrics': {
            'planned_runs': planned,
            'success_count': success_count,
            'success_rate': success_rate,
            'window_days': window_days,
            'degraded_episodes': degraded_episodes,
            'evaluated_at': now.isoformat(),
        },
    }


def can_enable_display_primary(source_id: str) -> tuple[bool, str]:
    if not get_compliance_go(source_id):
        return False, '合规未 GO（#124）；禁止打开生产 site_display_primary'
    report = evaluate_gates(source_id)
    if not report['passed']:
        return False, '试点质量闸门未通过: ' + '; '.join(report['failures'])
    drill = get_last_drill(source_id)
    if not drill or not drill.get('passed'):
        return False, '尚未完成通过的强制故障演练'
    return True, 'ok'


def run_rollback_drill(source_id: str, *, actor: str) -> dict[str, Any]:
    """Simulate failure → hide primary → keep fallback → restore import (no redeploy)."""
    before = source_control_service.get_flags(source_id)
    steps: list[dict[str, Any]] = []

    # 1) force import off (failure path)
    source_control_service.set_flags(source_id, actor=actor, site_import_enabled=False)
    steps.append({'step': 'disable_import', 'ok': True})

    # 2) hide site primary display
    source_control_service.set_flags(source_id, actor=actor, site_display_primary=False)
    steps.append({'step': 'disable_display_primary', 'ok': True})

    # 3) ensure google fallback on
    source_control_service.set_flags(source_id, actor=actor, fallback_google_enabled=True)
    flags_mid = source_control_service.get_flags(source_id)
    steps.append(
        {
            'step': 'fallback_google',
            'ok': flags_mid['fallback_google_enabled'] is True and flags_mid['site_display_primary'] is False,
        }
    )

    # 4) restore import for continued observation; leave display_primary off until gates
    source_control_service.set_flags(source_id, actor=actor, site_import_enabled=True)
    after = source_control_service.get_flags(source_id)
    steps.append({'step': 'restore_import', 'ok': after['site_import_enabled'] is True})

    passed = all(step['ok'] for step in steps)
    result = {
        'source_id': source_id.lower(),
        'passed': passed,
        'actor': actor,
        'at': datetime.now(UTC).isoformat(),
        'steps': steps,
        'before': before,
        'after': after,
        'note': '全程通过配置开关完成，无需重新部署',
    }
    SystemConfig.set_value(_DRILL_PREFIX + source_id.lower(), json.dumps(result, ensure_ascii=False))
    db.session.commit()
    return result


def get_last_drill(source_id: str) -> dict[str, Any] | None:
    raw = SystemConfig.get_value(_DRILL_PREFIX + source_id.lower())
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def get_evidence_bundle(source_id: str) -> dict[str, Any]:
    return {
        'source_id': source_id.lower(),
        'runs': _load_evidence(source_id),
        'compliance_go': get_compliance_go(source_id),
        'gates': evaluate_gates(source_id),
        'last_drill': get_last_drill(source_id),
        'flags': _safe_flags(source_id),
        'audit': source_control_service.list_audit(limit=20),
    }


def _safe_flags(source_id: str) -> dict[str, Any] | None:
    try:
        return source_control_service.get_flags(source_id)
    except ValueError:
        return None


def _evidence_key(source_id: str) -> str:
    return _EVIDENCE_PREFIX + source_id.lower()


def _load_evidence(source_id: str) -> list[dict[str, Any]]:
    raw = SystemConfig.get_value(_evidence_key(source_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _load_compliance() -> dict[str, Any]:
    raw = SystemConfig.get_value(_COMPLIANCE_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _count_degraded_episodes(items: list[dict[str, Any]]) -> int:
    """Count failure streaks as degraded episodes (approx for evidence-only history)."""
    episodes = 0
    in_fail = False
    for item in items:
        if not item.get('success'):
            if not in_fail:
                episodes += 1
                in_fail = True
        else:
            in_fail = False
    return episodes
