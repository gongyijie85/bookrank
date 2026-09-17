"""Issues #137 source flags / #138 pipeline helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.models.new_book import NewBook, Publisher
from app.services import source_control_service
from app.services.batch_import_service import BatchImportError, compute_content_sha256, import_batch
from app.services.pipeline_draft import build_fixture_batch_draft, redact_secrets_from_env


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
    pub.site_crawl_enabled = False
    pub.site_import_enabled = False
    pub.site_display_primary = False
    pub.fallback_google_enabled = True
    db.session.commit()
    return pub


def _isbn(base12: str) -> str:
    checksum = sum(int(base12[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    return base12 + str((10 - checksum % 10) % 10)


ISBN = _isbn('978006341900')


def _accepted_batch(source_id: str = 'harpercollins'):
    recent = (date.today() - timedelta(days=2)).isoformat()
    records = [
        {
            'title': 'Flag Test Book',
            'author': 'Author F',
            'isbn13': ISBN,
            'source_url': 'https://www.harpercollins.com/products/flag-test',
            'publication_date': recent,
            'editions': [{'format': 'Hardcover', 'isbn13': ISBN, 'is_main': True}],
            'field_provenance': [],
            'missing_fields': [],
        }
    ]
    schema = 'hc-observer-v1'
    digest = compute_content_sha256(source_id, schema, records)
    return {
        'batch_id': f'{source_id}:2026-08-12:{digest[:16]}',
        'schema_version': schema,
        'source_id': source_id,
        'produced_at': datetime.now(UTC).isoformat(),
        'producer': 'test',
        'content_sha256': digest,
        'records': records,
    }


def test_defaults_are_safe(app, db, harper):
    flags = source_control_service.get_flags('harpercollins')
    assert flags['site_crawl_enabled'] is False
    assert flags['site_import_enabled'] is False
    assert flags['site_display_primary'] is False
    assert flags['fallback_google_enabled'] is True


def test_import_disabled_when_flag_off(app, db, harper):
    with pytest.raises(BatchImportError) as exc:
        import_batch(_accepted_batch())
    assert exc.value.code == 'IMPORT_DISABLED'
    assert NewBook.query.filter_by(isbn13=ISBN).count() == 0


def test_import_enabled_writes_non_display_when_primary_off(app, db, harper):
    source_control_service.set_flags(
        'harpercollins',
        site_import_enabled=True,
        site_display_primary=False,
        actor='test',
    )
    result = import_batch(_accepted_batch())
    assert result.status == 'applied'
    book = NewBook.query.filter_by(isbn13=ISBN).one()
    assert book.is_displayable is False
    assert book.last_import_batch_id


def test_display_primary_on_makes_site_books_visible(app, db, harper):
    source_control_service.set_flags(
        'harpercollins',
        site_import_enabled=True,
        site_display_primary=True,
        actor='test',
    )
    import_batch(_accepted_batch())
    book = NewBook.query.filter_by(isbn13=ISBN).one()
    assert book.is_displayable is True


def test_flag_change_is_audited(app, db, harper):
    source_control_service.set_flags('harpercollins', site_crawl_enabled=True, actor='ops')
    audit = source_control_service.list_audit(limit=5)
    assert any(item.get('actor') == 'ops' and item.get('source_id') == 'harpercollins' for item in audit)


def test_query_hides_site_books_when_display_primary_off(app, db, harper):
    from unittest.mock import MagicMock

    from app.services.new_book.query_service import NewBookQueryService

    source_control_service.set_flags(
        'harpercollins',
        site_import_enabled=True,
        site_display_primary=False,
        actor='test',
    )
    import_batch(_accepted_batch())
    # force displayable true on row to prove query filter, not just write path
    book = NewBook.query.filter_by(isbn13=ISBN).one()
    book.is_displayable = True
    db.session.commit()

    query_service = NewBookQueryService(MagicMock())
    books, total = query_service.get_new_books(days=90, page=1, per_page=50)
    ids = {b.isbn13 for b in books}
    assert ISBN not in ids

    source_control_service.set_flags(
        'harpercollins',
        site_display_primary=True,
        actor='test',
    )
    books2, _ = query_service.get_new_books(days=90, page=1, per_page=50)
    assert ISBN in {b.isbn13 for b in books2}


def test_redact_secrets_from_env():
    env = {
        'BATCH_IMPORT_SECRET': 'secret',
        'CRON_SECRET': 'cron',
        'PATH': '/usr/bin',
    }
    safe = redact_secrets_from_env(env)
    assert 'BATCH_IMPORT_SECRET' not in safe
    assert 'CRON_SECRET' not in safe
    assert safe['PATH'] == '/usr/bin'


def test_build_fixture_batch_draft_no_write(tmp_path: Path):
    fixtures = Path('tests/fixtures/publisher_observer/harpercollins')
    draft = build_fixture_batch_draft(
        fixtures / 'manifest.json',
        run_date='2026-08-12',
        producer='gha_observe',
        produced_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    assert draft['write_enabled'] is False
    assert draft['source_id'] == 'harpercollins'
    assert draft['batch_id'].startswith('harpercollins:')
