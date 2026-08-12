"""Issue #135: accepted / pending_review / rejected grading and work merge."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.batch_import_service import compute_content_sha256, import_batch
from app.services.publisher_observer.harpercollins import is_valid_isbn13


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
    return pub


def _isbn(base12: str) -> str:
    checksum = sum(int(base12[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    return base12 + str((10 - checksum % 10) % 10)


ISBN_A = _isbn('978006341811')
ISBN_B = _isbn('978006341822')
ISBN_C = _isbn('978006341833')


def _batch(records: list, source_id: str = 'harpercollins', **extra):
    schema = 'hc-observer-v1'
    digest = compute_content_sha256(source_id, schema, records)
    payload = {
        'batch_id': f'{source_id}:2026-08-12:{digest[:16]}',
        'schema_version': schema,
        'source_id': source_id,
        'produced_at': datetime.now(UTC).isoformat(),
        'producer': 'test',
        'content_sha256': digest,
        'records': records,
    }
    payload.update(extra)
    return payload


def test_isbns_valid():
    assert is_valid_isbn13(ISBN_A)
    assert is_valid_isbn13(ISBN_B)


def test_accepted_requires_recency_and_print_main(app, db, harper):
    recent = (date.today() - timedelta(days=5)).isoformat()
    records = [
        {
            'title': 'Recent Print',
            'author': 'Author A',
            'isbn13': ISBN_A,
            'source_url': 'https://www.harpercollins.com/products/recent-print',
            'publication_date': recent,
            'editions': [
                {'format': 'E-book', 'isbn13': ISBN_B, 'is_main': True},
                {'format': 'Hardcover', 'isbn13': ISBN_A, 'is_main': False},
            ],
            'field_provenance': [],
            'missing_fields': [],
        }
    ]
    result = import_batch(_batch(records))
    assert result.receipt['counts']['accepted'] == 1
    book = NewBook.query.filter_by(isbn13=ISBN_A).one()
    assert book.is_displayable is True
    editions = book.get_editions()
    main = next(e for e in editions if e.get('is_main'))
    assert main['format'] == 'Hardcover'
    assert main['isbn13'] == ISBN_A


def test_pending_review_for_missing_author_keeps_null(app, db, harper):
    records = [
        {
            'title': 'No Author Book',
            'author': None,
            'isbn13': ISBN_C,
            'source_url': 'https://www.harpercollins.com/products/no-author',
            'publication_date': None,
            'editions': [{'format': 'Hardcover', 'isbn13': ISBN_C, 'is_main': True}],
            'field_provenance': [],
            'missing_fields': ['author', 'publication_date'],
        }
    ]
    result = import_batch(_batch(records))
    assert result.receipt['counts']['pending_review'] == 1
    assert result.receipt['counts']['accepted'] == 0
    book = NewBook.query.filter_by(isbn13=ISBN_C).one()
    assert book.is_displayable is False
    assert book.author in ('', 'Unknown', None) or book.author == ''
    # must not invent a real author name
    assert book.author != 'Unknown Author'


def test_merge_by_canonical_url_combines_editions(app, db, harper):
    url = 'https://www.harpercollins.com/products/merged-work?utm=1'
    recent = (date.today() - timedelta(days=2)).isoformat()
    first = [
        {
            'title': 'Merged Work',
            'author': 'Author M',
            'isbn13': ISBN_A,
            'source_url': url,
            'publication_date': recent,
            'editions': [{'format': 'Hardcover', 'isbn13': ISBN_A, 'is_main': True}],
            'field_provenance': [
                {
                    'field': 'title',
                    'source_kind': '官网记录',
                    'source_url': url,
                    'observed_at': '2026-08-12T00:00:00+00:00',
                    'method': 'product_json',
                }
            ],
            'missing_fields': [],
        }
    ]
    import_batch(_batch(first))
    second = [
        {
            'title': 'Merged Work',
            'author': 'Author M',
            'isbn13': ISBN_B,
            'source_url': 'https://www.harpercollins.com/products/merged-work',
            'publication_date': recent,
            'editions': [{'format': 'Paperback', 'isbn13': ISBN_B, 'is_main': True}],
            'field_provenance': [
                {
                    'field': 'title',
                    'source_kind': '补全来源',
                    'source_url': url,
                    'observed_at': '2026-08-12T01:00:00+00:00',
                    'method': 'product_json',
                }
            ],
            'missing_fields': [],
        }
    ]
    import_batch(_batch(second))
    # same work card
    books = NewBook.query.filter(
        NewBook.publisher_id == harper.id,
        NewBook.title == 'Merged Work',
    ).all()
    assert len(books) == 1
    editions = books[0].get_editions()
    isbns = {e['isbn13'] for e in editions}
    assert ISBN_A in isbns and ISBN_B in isbns
    # main remains hardcover
    main = next(e for e in editions if e.get('is_main'))
    assert main['format'] == 'Hardcover'


def test_rejected_does_not_clobber_existing_success(app, db, harper):
    recent = (date.today() - timedelta(days=1)).isoformat()
    good = [
        {
            'title': 'Keep Me',
            'author': 'Solid Author',
            'isbn13': ISBN_A,
            'source_url': 'https://www.harpercollins.com/products/keep-me',
            'publication_date': recent,
            'editions': [{'format': 'Hardcover', 'isbn13': ISBN_A, 'is_main': True}],
            'field_provenance': [],
            'missing_fields': [],
        }
    ]
    import_batch(_batch(good))
    bad = [
        {
            'title': '',
            'author': 'X',
            'isbn13': ISBN_A,
            'source_url': 'https://www.harpercollins.com/products/keep-me',
            'editions': [],
            'field_provenance': [],
            'missing_fields': ['title'],
        }
    ]
    result = import_batch(_batch(bad))
    assert result.receipt['counts']['rejected'] == 1
    book = NewBook.query.filter_by(isbn13=ISBN_A).one()
    assert book.title == 'Keep Me'
    assert book.author == 'Solid Author'
