"""Issue #134: 采集批次幂等导入入口。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from app.models.new_book import NewBook, Publisher


@pytest.fixture
def import_secret(app):
    app.config['BATCH_IMPORT_SECRET'] = 'test-batch-import-secret'
    return 'test-batch-import-secret'


@pytest.fixture
def harper_publisher(app, db):
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
    return pub


def _canonical_sha(source_id: str, schema_version: str, records: list) -> str:
    body = {
        'source_id': source_id,
        'schema_version': schema_version,
        'records': records,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()


def _valid_batch(**overrides):
    records = [
        {
            'title': 'Import Test Book',
            'author': 'Test Author',
            'isbn13': '9780063417113',
            'source_url': 'https://www.harpercollins.com/products/import-test-book',
            'publication_date': '2026-08-01',
            'missing_fields': [],
            'editions': [{'format': 'Hardcover', 'isbn13': '9780063417113', 'is_main': True}],
            'field_provenance': [],
        }
    ]
    source_id = 'harpercollins'
    schema_version = 'hc-observer-v1'
    digest = _canonical_sha(source_id, schema_version, records)
    batch = {
        'batch_id': f'{source_id}:2026-08-12:{digest[:16]}',
        'schema_version': schema_version,
        'source_id': source_id,
        'produced_at': datetime.now(UTC).isoformat(),
        'producer': 'test',
        'content_sha256': digest,
        'write_enabled': True,
        'records': records,
    }
    batch.update(overrides)
    return batch


class TestBatchImportAuth:
    def test_missing_secret_config_returns_401(self, client):
        response = client.post(
            '/api/new-books/import-batch',
            json=_valid_batch(),
            headers={'Authorization': 'Bearer anything'},
        )
        assert response.status_code == 401

    def test_wrong_token_returns_401(self, client, import_secret):
        response = client.post(
            '/api/new-books/import-batch',
            json=_valid_batch(),
            headers={'Authorization': 'Bearer wrong'},
        )
        assert response.status_code == 401

    def test_cron_secret_does_not_authorize_import(self, client, import_secret, app):
        app.config['CRON_SECRET'] = 'cron-only'
        response = client.post(
            '/api/new-books/import-batch',
            json=_valid_batch(),
            headers={'Authorization': 'Bearer cron-only'},
        )
        assert response.status_code == 401


class TestBatchImportValidation:
    def test_expired_batch_rejected(self, client, import_secret, harper_publisher):
        old = (datetime.now(UTC) - timedelta(hours=49)).isoformat()
        batch = _valid_batch(produced_at=old)
        response = client.post(
            '/api/new-books/import-batch',
            json=batch,
            headers={'Authorization': f'Bearer {import_secret}'},
        )
        assert response.status_code == 400
        body = response.get_json()
        assert body['success'] is False
        assert body['errors']['code'] == 'EXPIRED'
        assert NewBook.query.filter_by(isbn13='9780063417113').count() == 0

    def test_digest_mismatch_rejected(self, client, import_secret, harper_publisher):
        batch = _valid_batch(content_sha256='0' * 64)
        response = client.post(
            '/api/new-books/import-batch',
            json=batch,
            headers={'Authorization': f'Bearer {import_secret}'},
        )
        assert response.status_code == 409
        assert response.get_json()['errors']['code'] == 'DIGEST_MISMATCH'

    def test_unknown_source_rejected(self, client, import_secret, db):
        records = [
            {
                'title': 'X',
                'author': 'Y',
                'isbn13': '9780063417229',
                'source_url': 'https://example.com/x',
                'missing_fields': [],
                'editions': [],
                'field_provenance': [],
            }
        ]
        digest = _canonical_sha('hachette', 'hc-observer-v1', records)
        batch = {
            'batch_id': f'hachette:2026-08-12:{digest[:16]}',
            'schema_version': 'hc-observer-v1',
            'source_id': 'hachette',
            'produced_at': datetime.now(UTC).isoformat(),
            'producer': 'test',
            'content_sha256': digest,
            'records': records,
        }
        response = client.post(
            '/api/new-books/import-batch',
            json=batch,
            headers={'Authorization': f'Bearer {import_secret}'},
        )
        assert response.status_code == 400
        assert response.get_json()['errors']['code'] == 'SOURCE_MISMATCH'


class TestBatchImportApply:
    def test_valid_batch_imports_book(self, client, import_secret, harper_publisher, db):
        batch = _valid_batch()
        response = client.post(
            '/api/new-books/import-batch',
            json=batch,
            headers={'Authorization': f'Bearer {import_secret}'},
        )
        assert response.status_code == 200
        data = response.get_json()['data']
        assert data['status'] == 'applied'
        assert data['batch_id'] == batch['batch_id']
        assert data['counts']['accepted'] >= 1

        book = NewBook.query.filter_by(isbn13='9780063417113').one()
        assert book.title == 'Import Test Book'
        assert book.publisher_id == harper_publisher.id
        assert book.last_import_batch_id == batch['batch_id']
        assert book.get_editions()[0]['is_main'] is True

    def test_identical_batch_is_idempotent(self, client, import_secret, harper_publisher, db):
        batch = _valid_batch()
        headers = {'Authorization': f'Bearer {import_secret}'}
        first = client.post('/api/new-books/import-batch', json=batch, headers=headers)
        second = client.post('/api/new-books/import-batch', json=batch, headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.get_json()['data']['status'] == 'duplicate'
        assert NewBook.query.filter_by(isbn13='9780063417113').count() == 1

    def test_same_batch_id_different_content_conflicts(self, client, import_secret, harper_publisher, db):
        batch = _valid_batch()
        headers = {'Authorization': f'Bearer {import_secret}'}
        client.post('/api/new-books/import-batch', json=batch, headers=headers)

        other_records = [
            {
                'title': 'Other Book',
                'author': 'Other Author',
                'isbn13': '9780063417335',
                'source_url': 'https://www.harpercollins.com/products/other',
                'missing_fields': [],
                'editions': [],
                'field_provenance': [],
            }
        ]
        other_digest = _canonical_sha('harpercollins', 'hc-observer-v1', other_records)
        conflict = {
            **batch,
            'content_sha256': other_digest,
            'records': other_records,
            # keep original batch_id
        }
        response = client.post('/api/new-books/import-batch', json=conflict, headers=headers)
        assert response.status_code == 409
        assert response.get_json()['errors']['code'] == 'DIGEST_MISMATCH'
