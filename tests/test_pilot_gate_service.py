"""Pilot gate service tests (#140/#123; was 0% coverage)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.new_book import Publisher
from app.services import pilot_gate_service as pgs
from app.services import source_control_service as scs


@pytest.fixture
def publisher(app, db):
    with app.app_context():
        pub = Publisher(
            name='哈珀柯林斯',
            name_en='HarperCollins',
            crawler_class='Dummy',
            is_active=True,
            source_status='healthy',
        )
        db.session.add(pub)
        db.session.commit()
        yield pub
        db.session.remove()


def test_compliance_go_roundtrip(app, db):
    assert pgs.get_compliance_go('harpercollins') is False
    pgs.set_compliance_go('harpercollins', True, actor='tester')
    assert pgs.get_compliance_go('harpercollins') is True


def test_can_enable_requires_compliance_and_gates(app, db, publisher):
    # 未合规 -> False
    ok, reason = pgs.can_enable_display_primary('harpercollins')
    assert ok is False
    assert '合规' in reason


def test_evaluate_gates_insufficient_runs(app, db):
    # 只有 1 次运行记录
    pgs.record_evidence_run('harpercollins', success=True, batch_id='b1')
    report = pgs.evaluate_gates('harpercollins')
    assert report['passed'] is False
    assert report['metrics']['planned_runs'] == 1


def test_evaluate_gates_sufficient(app, db):
    now = datetime.now(UTC)
    for i in range(12):
        at = now - timedelta(days=i)
        pgs.record_evidence_run('harpercollins', success=True, batch_id=f'b{i}', at=at)
    report = pgs.evaluate_gates('harpercollins')
    assert report['metrics']['planned_runs'] == 12
    assert report['metrics']['success_rate'] == 1.0
    # 时间窗不足（只有 12 天 < 14 天）—— 但按线 101 的检查仅在
    # planned >= MIN_PLANNED_RUNS 且窗口不足时才失败
    # 12 次运行窗口 11 天 -> 失败
    assert report['passed'] is False


def test_rollback_drill_flow(app, db, publisher):
    # 打开 import 以便 drill 有开关操作
    scs.set_flags('harpercollins', actor='tester', site_import_enabled=True)
    result = pgs.run_rollback_drill('harpercollins', actor='tester')
    assert result['passed'] is True
    steps = {s['step']: s['ok'] for s in result['steps']}
    assert steps['disable_import'] is True
    assert steps['disable_display_primary'] is True
    assert steps['fallback_google'] is True
    assert steps['restore_import'] is True
    # 演练后仍以 import 开启、display_primary 关闭状态结束
    flags = scs.get_flags('harpercollins')
    assert flags['site_import_enabled'] is True


def test_get_last_drill_none(app, db):
    assert pgs.get_last_drill('harpercollins') is None
