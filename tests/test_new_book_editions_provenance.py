"""Issue #132: NewBook 关联版本与字段出处增量存储。"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.new_book import NewBook, Publisher


@pytest.fixture
def publisher(app, db):
    name_en = 'TestPublisher132'
    pub = Publisher.query.filter_by(name_en=name_en).first()
    if pub is None:
        pub = Publisher(
            name='测试出版社-132',
            name_en=name_en,
            crawler_class='HarperCollinsGoogleCrawler',
            is_active=True,
        )
        db.session.add(pub)
        db.session.commit()
    return pub.id


def test_new_book_without_editions_keeps_legacy_to_dict_shape(app, db, publisher):
    with app.app_context():
        book = NewBook(
            publisher_id=publisher,
            title='Legacy Title',
            author='Legacy Author',
            isbn13='9780063416178',
            publication_date=date(2026, 8, 1),
            is_displayable=True,
        )
        db.session.add(book)
        db.session.commit()

        payload = book.to_dict()
        assert payload['title'] == 'Legacy Title'
        assert payload['isbn13'] == '9780063416178'
        assert payload.get('editions') == []
        assert payload.get('field_provenance') == []
        assert payload.get('canonical_source_url') is None
        assert payload.get('last_import_batch_id') is None


def test_persist_and_read_back_editions_and_provenance(app, db, publisher):
    with app.app_context():
        isbn = '9780063416999'
        book = NewBook(
            publisher_id=publisher,
            title='Whistler',
            author='Ann Patchett',
            isbn13=isbn,
            source_url='https://www.harpercollins.com/products/whistler-ann-patchett',
            publication_date=date(2026, 8, 1),
        )
        book.set_editions(
            [
                {'format': 'Hardcover', 'isbn13': isbn, 'is_main': True},
                {'format': 'E-book', 'isbn13': '9780063416185', 'is_main': False},
            ]
        )
        book.set_field_provenance(
            [
                {
                    'field': 'title',
                    'source_kind': '官网记录',
                    'source_url': book.source_url,
                    'observed_at': '2026-08-12T00:00:00+00:00',
                    'method': 'product_json',
                }
            ]
        )
        book.canonical_source_url = book.source_url
        book.last_import_batch_id = 'harpercollins:2026-08-12:abcd1234efgh5678'
        db.session.add(book)
        db.session.commit()

        loaded = NewBook.query.filter_by(isbn13=isbn).one()
        editions = loaded.get_editions()
        assert len(editions) == 2
        main = next(item for item in editions if item['is_main'])
        assert main['isbn13'] == loaded.isbn13
        assert main['format'] == 'Hardcover'
        assert loaded.get_field_provenance()[0]['source_kind'] == '官网记录'
        assert loaded.canonical_source_url == book.source_url
        assert loaded.last_import_batch_id.startswith('harpercollins:')

        payload = loaded.to_dict()
        assert any(e['isbn13'] == isbn for e in payload['editions'])
        assert payload['field_provenance'][0]['field'] == 'title'


def test_publisher_source_control_defaults_keep_legacy_path(app, db, publisher):
    """预留来源开关字段：默认不改变现网写入/展示路径语义。"""
    with app.app_context():
        pub = db.session.get(Publisher, publisher)
        assert pub is not None
        assert pub.site_crawl_enabled is False
        assert pub.site_import_enabled is False
        assert pub.site_display_primary is False
        assert pub.fallback_google_enabled is True
        assert pub.source_status == 'healthy'
        assert pub.consecutive_failures == 0
        assert pub.consecutive_successes == 0
        assert pub.last_success_batch_id is None
