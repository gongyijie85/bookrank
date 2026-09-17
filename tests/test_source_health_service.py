"""Source health service tests (failure/recovery state machine; was 0%)."""

from unittest.mock import patch

import pytest

from app.models.new_book import Publisher
from app.services import source_health_service as shs


@pytest.fixture
def publisher(app, db):
    with app.app_context():
        pub = Publisher(
            name='哈珀柯林斯',
            name_en='HarperCollins',
            crawler_class='Dummy',
            is_active=True,
            source_status='healthy',
            consecutive_failures=0,
            consecutive_successes=0,
        )
        db.session.add(pub)
        db.session.commit()
        yield pub
        db.session.remove()


def test_publisher_for_source_unknown(app, db):
    assert shs.publisher_for_source('nonexistent') is None


def test_record_plan_failure_degrades_after_three(app, db, publisher):
    for i in range(2):
        shs.record_plan_failure('harpercollins', error_code=f'E{i}', error_summary=f'err{i}')
    # 前两次不降级
    assert publisher.source_status == 'healthy'
    shs.record_plan_failure('harpercollins', error_code='E3', error_summary='err3')
    assert publisher.source_status == 'degraded'
    assert publisher.consecutive_failures == 3


def test_record_plan_success_recovers(app, db, publisher):
    publisher.source_status = 'degraded'
    db.session.commit()

    shs.record_plan_success('harpercollins', batch_id='b1')
    assert publisher.source_status == 'recovering'
    shs.record_plan_success('harpercollins', batch_id='b2')
    assert publisher.source_status == 'healthy'


def test_disabled_source_records_but_no_degrade(app, db, publisher):
    publisher.source_status = 'disabled'
    db.session.commit()
    shs.record_plan_failure('harpercollins', error_code='E', error_summary='err')
    assert publisher.source_status == 'disabled'
    assert publisher.last_error_code == 'E'


def test_success_in_disabled_does_not_enable(app, db, publisher):
    publisher.source_status = 'disabled'
    db.session.commit()
    shs.record_plan_success('harpercollins', batch_id='b1')
    assert publisher.source_status == 'disabled'


def test_list_source_health_snapshot(app, db, publisher):
    rows = shs.list_source_health()
    hc = next(r for r in rows if r['name_en'] == 'HarperCollins')
    assert hc['registered'] is True
    assert hc['source_status'] == 'healthy'
    assert 'consecutive_failures' in hc


@patch('app.services.source_health_service._dispatch_alert_async')
def test_failure_dispatches_degraded_alert(mock_dispatch, app, db, publisher):
    for _ in range(3):
        shs.record_plan_failure('harpercollins', error_code='E', error_summary='err')
    assert mock_dispatch.called
    assert mock_dispatch.call_args.args[1] == 'degraded'


@patch('app.services.source_health_service._dispatch_alert_async')
def test_recovery_dispatches_closed_alert(mock_dispatch, app, db, publisher):
    publisher.source_status = 'degraded'
    db.session.commit()
    shs.record_plan_success('harpercollins', batch_id='b1')
    shs.record_plan_success('harpercollins', batch_id='b2')
    assert mock_dispatch.called
    assert mock_dispatch.call_args.args[1] == 'recovered'
