"""Source control service tests (feature flags + audit; was 0% coverage)."""

import pytest

from app.models.new_book import Publisher
from app.services import source_control_service as scs


@pytest.fixture
def publisher(app, db):
    with app.app_context():
        pub = Publisher(
            name='塔奇拉出版社',
            name_en='HarperCollins',
            crawler_class='Dummy',
            is_active=True,
            site_import_enabled=False,
            site_display_primary=False,
            fallback_google_enabled=True,
        )
        db.session.add(pub)
        db.session.commit()
        yield pub
        db.session.remove()


def test_get_flags_unknown_source(app, publisher):
    with pytest.raises(ValueError):
        scs.get_flags('nonexistent')


def test_get_flags(app, publisher):
    flags = scs.get_flags('harpercollins')
    assert flags['source_id'] == 'harpercollins'
    assert flags['name_en'] == 'HarperCollins'
    assert flags['site_import_enabled'] is False
    assert flags['fallback_google_enabled'] is True


def test_set_flags_updates_and_audits(app, publisher):
    result = scs.set_flags(
        'harpercollins',
        actor='tester',
        site_import_enabled=True,
        fallback_google_enabled=False,
    )
    assert result['site_import_enabled'] is True
    assert result['fallback_google_enabled'] is False
    audit = scs.list_audit()
    assert len(audit) == 1
    assert audit[0]['actor'] == 'tester'
    assert audit[0]['changes']['site_import_enabled'] is True


def test_site_import_allowed_and_display(app, publisher, db):
    assert scs.site_import_allowed('harpercollins') is False
    assert scs.site_display_primary('harpercollins') is False
    scs.set_flags('harpercollins', actor='tester', site_import_enabled=True)
    assert scs.site_import_allowed('harpercollins') is True


def test_list_audit_no_data(app, db):
    db.session.remove()
    assert scs.list_audit() == []
