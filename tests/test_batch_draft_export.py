"""Issue #133: 无写库观察导出可导入采集批次草稿。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.publisher_observer import (
    observe_fixture_manifest,
)
from app.services.publisher_observer.batch_draft import (
    export_batch_draft,
    observe_fixture_manifest_as_batch_draft,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'publisher_observer' / 'harpercollins'


def test_export_batch_draft_from_observation_report_is_import_shaped_and_no_write():
    report = observe_fixture_manifest(FIXTURES / 'manifest.json')
    produced_at = datetime(2026, 8, 12, 8, 0, 0, tzinfo=UTC)

    draft = export_batch_draft(
        report,
        produced_at=produced_at,
        run_date='2026-08-12',
        producer='gha_run_test',
    )

    assert draft['write_enabled'] is False
    assert draft['source_id'] == 'harpercollins'
    assert draft['schema_version']
    assert draft['produced_at'] == produced_at.isoformat()
    assert draft['producer'] == 'gha_run_test'
    assert isinstance(draft['content_sha256'], str) and len(draft['content_sha256']) == 64
    assert draft['batch_id'].startswith('harpercollins:2026-08-12:')
    assert draft['batch_id'].endswith(draft['content_sha256'][:16])
    assert isinstance(draft['records'], list)
    assert draft['ai_fallback_calls'] == report.ai_fallback_calls
    # Unverified AI candidates must never appear as book records.
    for record in draft['records']:
        assert 'title' in record
        assert 'source_url' in record
        assert 'editions' in record
        assert 'missing_fields' in record
        assert 'field_provenance' in record


def test_observe_as_batch_draft_rejects_non_harper_before_export(tmp_path: Path):
    bad = tmp_path / 'manifest.json'
    bad.write_text(
        '{"source": "hachette", "fixtures": []}',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='harpercollins'):
        observe_fixture_manifest_as_batch_draft(
            bad,
            produced_at=datetime(2026, 8, 12, tzinfo=UTC),
            run_date='2026-08-12',
            producer='test',
        )


def test_export_batch_draft_is_deterministic_for_same_report():
    report = observe_fixture_manifest(FIXTURES / 'manifest.json')
    produced_at = datetime(2026, 8, 12, 8, 0, 0, tzinfo=UTC)
    a = export_batch_draft(report, produced_at=produced_at, run_date='2026-08-12', producer='p')
    b = export_batch_draft(report, produced_at=produced_at, run_date='2026-08-12', producer='p')
    assert a == b
    assert a['write_enabled'] is False


def test_export_requires_observation_report_type():
    with pytest.raises(TypeError):
        export_batch_draft(  # type: ignore[arg-type]
            {'source': 'harpercollins'},
            produced_at=datetime(2026, 8, 12, tzinfo=UTC),
            run_date='2026-08-12',
            producer='p',
        )
