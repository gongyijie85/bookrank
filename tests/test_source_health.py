"""Issue #136: source health counters and admin visibility."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.new_book import Publisher
from app.services import source_health_service
from app.services.batch_import_service import compute_content_sha256, import_batch


@pytest.fixture
def harper(app, db):
    pub = Publisher.query.filter_by(name_en='HarperCollins').first()
    if pub is None:
        pub = Publisher(
            name='哈珀柯林斯',
            name_en='HarperCollins',
            crawler_class='HarperCollinsGoogleCrawler',
            is_active=True,
        )
        db.session.add(pub)
        db.session.commit()
    pub.consecutive_failures = 0
    pub.consecutive_successes = 0
    pub.source_status = 'healthy'
    pub.last_success_batch_id = None
    pub.site_import_enabled = True
    pub.site_display_primary = True
    db.session.commit()
    return pub


def test_three_failures_degrade_without_clearing_last_success(app, db, harper):
    harper.last_success_batch_id = 'harpercollins:2026-08-01:deadbeefdeadbeef'
    db.session.commit()
    for _ in range(3):
        source_health_service.record_plan_failure(
            'harpercollins',
            error_code='EXPIRED',
            error_summary='batch too old',
        )
    db.session.refresh(harper)
    assert harper.consecutive_failures == 3
    assert harper.source_status == 'degraded'
    assert harper.last_success_batch_id == 'harpercollins:2026-08-01:deadbeefdeadbeef'


def test_two_successes_recover_from_degraded(app, db, harper):
    harper.source_status = 'degraded'
    harper.consecutive_failures = 3
    db.session.commit()
    source_health_service.record_plan_success('harpercollins', batch_id='b1')
    source_health_service.record_plan_success('harpercollins', batch_id='b2')
    db.session.refresh(harper)
    assert harper.source_status == 'healthy'
    assert harper.consecutive_successes == 2
    assert harper.consecutive_failures == 0
    assert harper.last_success_batch_id == 'b2'


def test_disabled_does_not_auto_recover(app, db, harper):
    harper.source_status = 'disabled'
    db.session.commit()
    source_health_service.record_plan_success('harpercollins', batch_id='b3')
    source_health_service.record_plan_success('harpercollins', batch_id='b4')
    db.session.refresh(harper)
    assert harper.source_status == 'disabled'


def test_duplicate_import_does_not_count_as_failure(app, db, harper, client):
    # empty applied batch is success; duplicate is not failure
    records: list = []
    schema = 'hc-observer-v1'
    digest = compute_content_sha256('harpercollins', schema, records)
    payload = {
        'batch_id': f'harpercollins:2026-08-12:{digest[:16]}',
        'schema_version': schema,
        'source_id': 'harpercollins',
        'produced_at': datetime.now(UTC).isoformat(),
        'producer': 'test',
        'content_sha256': digest,
        'records': records,
    }
    first = import_batch(payload)
    second = import_batch(payload)
    assert first.status == 'applied'
    assert second.status == 'duplicate'
    db.session.refresh(harper)
    assert harper.consecutive_failures == 0
    assert harper.source_status == 'healthy'


def test_admin_source_health_requires_admin(client, app, db, harper):
    response = client.get('/api/admin/new-books/source-health')
    # 401/403 unauth; 429 if suite already exhausted admin rate limit
    assert response.status_code in (401, 403, 302, 400, 429)


def test_admin_source_health_lists_publisher(client, app, db, harper):
    from app.utils import admin_auth

    # Clear suite-wide admin auth ban state (other tests may have tripped 429)
    admin_auth._auth_failures.clear()

    app.config['ADMIN_SECRET'] = 'admin-test-secret'
    response = client.get(
        '/api/admin/new-books/source-health',
        headers={'X-Admin-Secret': 'admin-test-secret'},
    )
    assert response.status_code == 200
    data = response.get_json()['data']
    assert 'sources' in data
    row = next(s for s in data['sources'] if s['source_id'] == 'harpercollins' or s['name_en'] == 'HarperCollins')
    assert 'source_status' in row
    assert 'consecutive_failures' in row
