"""Contract coverage for the HarperCollins observation prototype."""

import importlib
import json
from hashlib import sha256
from pathlib import Path

import pytest

from app.services.publisher_observer.contracts import (
    BookObservation,
    EditionObservation,
    EvidenceStatus,
    ExtractionEvidence,
    ExtractionMethod,
    ObservationReport,
    TemplateCandidate,
)

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'publisher_observer' / 'harpercollins'


def _observer_api():
    return importlib.import_module('app.services.publisher_observer.harpercollins')


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding='utf-8')


def _write_manifest(path: Path, fixtures: list[dict[str, object]], source: str = 'harpercollins') -> Path:
    _write_json(path, {'source': source, 'fixtures': fixtures})
    return path


def _collection_item(name: str, page: int, next_url: str | None = None) -> dict[str, object]:
    return {
        'name': name,
        'source_url': f'https://www.harpercollins.com/collections/new-releases?page={page}',
        'page': page,
        'next_url': next_url,
    }


def _codes(report: ObservationReport) -> set[str | None]:
    return {item.error_code for item in report.evidence}


def _write_collection_pair(
    directory: Path,
    *,
    stem: str,
    source_url: str,
    next_url: str | None,
    rows: list[object],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for method in ('css', 'xpath'):
        name = f'{stem}-{method}.json'
        _write_json(directory / name, rows)
        items.append(
            {
                'name': name,
                'source_url': source_url,
                'next_url': next_url,
            }
        )
    return items


@pytest.mark.parametrize('schema_name', ['COLLECTION_CSS_SCHEMA', 'COLLECTION_XPATH_SCHEMA'])
def test_collection_schema_matches_crawl4ai_09_contract(schema_name: str) -> None:
    api = _observer_api()
    schema = getattr(api, schema_name)

    assert set(schema) == {'name', 'baseSelector', 'fields'}
    assert isinstance(schema['baseSelector'], str) and schema['baseSelector']
    assert [field['name'] for field in schema['fields']] == ['title', 'url']
    for field in schema['fields']:
        expected_keys = {'name', 'selector', 'type'}
        if field['type'] == 'attribute':
            expected_keys.add('attribute')
        assert set(field) == expected_keys
        assert isinstance(field['selector'], str) and field['selector']
        if schema_name == 'COLLECTION_XPATH_SCHEMA' and field['type'] == 'text':
            # Crawl4AI's XPath text extractor expects an element and extracts
            # its text itself; a terminal /text() would return a string.
            assert not field['selector'].rstrip().endswith('/text()')


@pytest.mark.parametrize('schema_name', ['COLLECTION_CSS_SCHEMA', 'COLLECTION_XPATH_SCHEMA'])
def test_collection_schema_is_deeply_immutable_json_serializable_dict_list(
    schema_name: str,
) -> None:
    api = _observer_api()
    schema = getattr(api, schema_name)

    assert isinstance(schema, dict)
    assert isinstance(schema['fields'], list)
    assert json.loads(json.dumps(schema))['baseSelector'] == schema['baseSelector']
    with pytest.raises(TypeError):
        schema['baseSelector'] = 'tampered'
    with pytest.raises(TypeError):
        schema['fields'][0]['selector'] = 'tampered'
    with pytest.raises(TypeError):
        schema['fields'].append({'name': 'tampered'})


def test_parse_product_document_preserves_only_observed_whistler_fields() -> None:
    api = _observer_api()

    record, evidence = api.parse_product_document(FIXTURE_DIR / 'product-whistler.json')

    assert record.title == 'Whistler'
    assert record.author == 'Ann Patchett'
    assert [(item.isbn13, item.is_main) for item in record.editions] == [
        ('9780063416178', True),
        ('9780063416185', False),
    ]
    assert record.publication_date is None
    assert record.missing_fields == ('publication_date',)
    assert evidence.status is EvidenceStatus.VALIDATION_FAILED


def test_report_includes_exact_manifest_digest() -> None:
    api = _observer_api()
    manifest = FIXTURE_DIR / 'manifest.json'

    report = api.observe_fixture_manifest(manifest)

    expected = sha256(manifest.read_bytes()).hexdigest()
    assert report.manifest_sha256 == expected
    assert report.to_dict()['manifest_sha256'] == expected
    assert len(expected) == 64
    assert set(expected) <= set('0123456789abcdef')


def test_manifest_digest_changes_with_all_provenance_metadata(tmp_path: Path) -> None:
    api = _observer_api()
    rows = [{'title': 'One', 'url': 'https://www.harpercollins.com/products/one'}]
    for method in ('css', 'xpath'):
        _write_json(tmp_path / f'collection-page-1-{method}.json', rows)
    css = _collection_item('collection-page-1-css.json', 1)
    xpath = _collection_item('collection-page-1-xpath.json', 1)
    variants = [
        [css, xpath],
        [xpath, css],
        [{**css, 'status': 'access_blocked'}, xpath],
        [
            {
                **css,
                'source_url': 'https://www.harpercollins.com/collections/new-releases?page=2',
                'page': 2,
            },
            {
                **xpath,
                'source_url': 'https://www.harpercollins.com/collections/new-releases?page=2',
                'page': 2,
            },
        ],
        [
            {**css, 'next_url': 'https://www.harpercollins.com/collections/new-releases?page=2'},
            {**xpath, 'next_url': 'https://www.harpercollins.com/collections/new-releases?page=2'},
        ],
    ]
    observed: list[str | None] = []
    for index, fixtures in enumerate(variants):
        manifest = _write_manifest(tmp_path / f'manifest-{index}.json', fixtures)
        observed.append(api.observe_fixture_manifest(manifest).manifest_sha256)

    assert None not in observed
    assert len(set(observed)) == len(variants)


def test_atom_candidates_are_deduplicated_and_timestamps_are_discovery_only(
    tmp_path: Path,
) -> None:
    api = _observer_api()
    atom = tmp_path / 'feed.atom'
    atom.write_text(
        """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <updated>2027-01-03T04:05:06Z</updated>
          <entry><published>2027-01-02</published><link rel="alternate" href="https://www.harpercollins.com/products/one" /></entry>
          <entry><link rel="alternate" href="https://www.harpercollins.com/products/one" /></entry>
          <entry><link rel="self" href="https://www.harpercollins.com/products/self" /></entry>
          <entry><link rel="alternate" href="http://www.harpercollins.com/products/insecure" /></entry>
          <entry><link rel="alternate" href="https://example.test/products/off-host" /></entry>
        </feed>""",
        encoding='utf-8',
    )

    candidates, evidence = api.parse_atom_candidates(atom)

    assert candidates == ('https://www.harpercollins.com/products/one',)
    assert evidence.matched_count == 1
    assert '2027' not in (evidence.detail or '')
    manifest = _write_manifest(
        tmp_path / 'manifest.json',
        [
            {
                'name': atom.name,
                'source_url': 'https://www.harpercollins.com/blogs/literary-hub/new-releases.atom',
            }
        ],
    )
    payload = api.observe_fixture_manifest(manifest).to_dict()
    serialized = json.dumps(payload, sort_keys=True)
    assert '2027' not in serialized
    assert 'publication_date' not in serialized


@pytest.mark.parametrize(
    ('name', 'source_url', 'next_url'),
    [
        ('feed.atom', 'https://example.test/new-releases.atom', None),
        (
            'feed.atom',
            'https://user@www.harpercollins.com/blogs/literary-hub/new-releases.atom',
            None,
        ),
        ('product-book.json', 'https://example.test/products/book', None),
        (
            'collection-page-1-css.json',
            'https://user@www.harpercollins.com/collections/new-releases?page=1',
            None,
        ),
        (
            'collection-page-1-css.json',
            'https://www.harpercollins.com/collections/new-releases?sort_by=date',
            None,
        ),
        (
            'collection-page-1-css.json',
            'https://www.harpercollins.com/collections/new-releases?page=1#books',
            None,
        ),
        (
            'collection-page-1-css.json',
            'https://www.harpercollins.com/collections/new-releases?page=1',
            'https://www.harpercollins.com/collections/new-releases?page=2&sort=x',
        ),
        (
            'fixed-ai-candidate.json',
            'https://www.harpercollins.com/products/not-a-collection',
            None,
        ),
    ],
)
def test_untrusted_manifest_urls_are_rejected_before_document_reads(
    tmp_path: Path, name: str, source_url: str, next_url: str | None
) -> None:
    api = _observer_api()
    item: dict[str, object] = {'name': name, 'source_url': source_url}
    if next_url is not None:
        item['next_url'] = next_url

    with pytest.raises(ValueError, match=r'source_url|next_url'):
        api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', [item]))


def test_product_manifest_url_must_equal_fixture_canonical_url(tmp_path: Path) -> None:
    api = _observer_api()
    product = tmp_path / 'product-whistler.json'
    product.write_bytes((FIXTURE_DIR / 'product-whistler.json').read_bytes())
    manifest = _write_manifest(
        tmp_path / 'manifest.json',
        [
            {
                'name': product.name,
                'source_url': 'https://www.harpercollins.com/products/a-different-book',
            }
        ],
    )

    with pytest.raises(ValueError, match='canonical product'):
        api.observe_fixture_manifest(manifest)


@pytest.mark.parametrize('field', ['source_url', 'next_url', 'page'])
def test_collection_pair_metadata_must_agree(tmp_path: Path, field: str) -> None:
    api = _observer_api()
    css = _collection_item('collection-page-1-css.json', 1)
    xpath = _collection_item('collection-page-1-xpath.json', 1)
    if field == 'source_url':
        xpath[field] = 'https://www.harpercollins.com/collections/new-releases?page=2'
    elif field == 'next_url':
        css[field] = 'https://www.harpercollins.com/collections/new-releases?page=2'
        xpath[field] = None
    else:
        xpath[field] = 2

    with pytest.raises(ValueError, match='metadata'):
        api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', [css, xpath]))


def test_isbn_checksum_and_format_priority_choose_one_print_main(tmp_path: Path) -> None:
    api = _observer_api()
    product = tmp_path / 'product.json'
    _write_json(
        product,
        {
            'product': {
                'title': 'Format Test',
                'handle': 'format-test',
                'images': [{'alt': 'Format Test by A Writer (9780063416178)'}],
                'variants': [
                    {'title': 'Audiobook', 'barcode': '9780063416185'},
                    {'title': 'Large Print', 'sku': '9780063416192'},
                    {'title': 'Paperback', 'barcode': '9780063416208'},
                    {'title': 'Trade Paperback', 'barcode': '9780063416215'},
                    {'title': 'Hardcover', 'barcode': '9780063416222'},
                    {'title': 'E-book', 'barcode': '9780063416239'},
                    {'title': 'Duplicate', 'barcode': '9780063416222'},
                    {'title': 'Invalid', 'barcode': '9780063416179'},
                ],
            }
        },
    )

    record, _ = api.parse_product_document(product)

    assert api.is_valid_isbn13('9780063416178') is True
    assert api.is_valid_isbn13('9780063416179') is False
    assert [item.format for item in record.editions] == [
        'Hardcover',
        'Trade Paperback',
        'Paperback',
        'Large Print',
        'E-book',
        'Audiobook',
    ]
    assert [item.is_main for item in record.editions] == [True, False, False, False, False, False]


def test_isbn_dedup_keeps_best_ranked_representation(tmp_path: Path) -> None:
    api = _observer_api()
    product = tmp_path / 'product.json'
    _write_json(
        product,
        {
            'product': {
                'title': 'Duplicate Format',
                'handle': 'duplicate-format',
                'images': [{'alt': 'Duplicate Format by A Writer (9780063416178)'}],
                'variants': [
                    {'title': 'E-book', 'barcode': '9780063416178'},
                    {'title': 'Hardcover', 'barcode': '9780063416178'},
                ],
            }
        },
    )

    record, _ = api.parse_product_document(product)

    assert [(item.format, item.isbn13, item.is_main) for item in record.editions] == [
        ('Hardcover', '9780063416178', True)
    ]


@pytest.mark.parametrize(
    ('contents', 'expected_code'),
    [
        ('{', 'PRODUCT_JSON_INVALID'),
        ('[]', 'PRODUCT_JSON_SHAPE_INVALID'),
        ('{"product": []}', 'PRODUCT_JSON_SHAPE_INVALID'),
        ('{"product": {}}', 'PRODUCT_IDENTITY_MISSING'),
    ],
)
def test_invalid_product_documents_fail_without_empty_records(
    tmp_path: Path, contents: str, expected_code: str
) -> None:
    api = _observer_api()
    product = tmp_path / 'product-invalid.json'
    product.write_text(contents, encoding='utf-8')

    record, evidence = api.parse_product_document(product)

    assert record is None
    assert evidence.status is EvidenceStatus.EXTRACTION_FAILED
    assert evidence.error_code == expected_code
    manifest = _write_manifest(
        tmp_path / 'manifest.json',
        [
            {
                'name': product.name,
                'source_url': 'https://www.harpercollins.com/products/invalid',
            }
        ],
    )
    report = api.observe_fixture_manifest(manifest)
    assert report.empty_result is True
    assert report.records == ()


def test_collection_css_xpath_parity_includes_second_page() -> None:
    api = _observer_api()

    report = api.observe_fixture_manifest(FIXTURE_DIR / 'manifest.json')

    assert 'https://www.harpercollins.com/products/untitled-book' in report.candidate_urls
    page_two = [item for item in report.evidence if 'page-2' in item.document_id]
    assert page_two
    assert all(item.status is EvidenceStatus.VALID for item in page_two)


def test_collection_css_xpath_disagreement_is_template_drift(tmp_path: Path) -> None:
    api = _observer_api()
    _write_json(tmp_path / 'page-css.json', [{'title': 'One', 'url': 'https://www.harpercollins.com/products/one'}])
    _write_json(tmp_path / 'page-xpath.json', [{'title': 'Two', 'url': 'https://www.harpercollins.com/products/two'}])
    manifest = _write_manifest(
        tmp_path / 'manifest.json',
        [_collection_item('page-css.json', 1), _collection_item('page-xpath.json', 1)],
    )

    report = api.observe_fixture_manifest(manifest)

    assert 'TEMPLATE_DRIFT' in _codes(report)
    assert any(item.status is EvidenceStatus.EXTRACTION_FAILED for item in report.evidence)


def test_duplicate_collection_strategy_member_is_explicit_and_digest_complete(
    tmp_path: Path,
) -> None:
    api = _observer_api()
    rows = [{'title': 'One', 'url': 'https://www.harpercollins.com/products/one'}]
    fixtures = _write_collection_pair(
        tmp_path,
        stem='collection-page-1',
        source_url='https://www.harpercollins.com/collections/new-releases?page=1',
        next_url=None,
        rows=rows,
    )
    fixtures.insert(1, dict(fixtures[0]))

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))

    duplicates = [item for item in report.evidence if item.error_code == 'DUPLICATE_COLLECTION_MEMBER']
    assert duplicates
    css_digest = sha256((tmp_path / 'collection-page-1-css.json').read_bytes()).hexdigest()
    assert [item.input_sha256 for item in report.evidence].count(css_digest) >= 2
    assert report.candidate_urls == ()


def test_duplicate_collection_source_across_pages_fails_all_conflicting_inputs(
    tmp_path: Path,
) -> None:
    api = _observer_api()
    source_url = 'https://www.harpercollins.com/collections/new-releases?page=1'
    fixtures: list[dict[str, object]] = []
    for page in (1, 2):
        fixtures.extend(
            _write_collection_pair(
                tmp_path,
                stem=f'collection-page-{page}',
                source_url=source_url,
                next_url=None,
                rows=[
                    {
                        'title': f'Book {page}',
                        'url': f'https://www.harpercollins.com/products/book-{page}',
                    }
                ],
            )
        )

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))

    conflicts = [item for item in report.evidence if item.error_code == 'DUPLICATE_SOURCE_URL']
    assert len(conflicts) == 4
    assert report.candidate_urls == ()


def test_collection_rows_rejected_by_both_strategies_remain_explicit_drift(
    tmp_path: Path,
) -> None:
    api = _observer_api()
    rows: list[object] = [
        {'title': 'Valid', 'url': 'https://www.harpercollins.com/products/valid'},
        {'title': 'Missing URL'},
        {'url': 'https://www.harpercollins.com/products/missing-title'},
        'not-a-row',
    ]
    fixtures = _write_collection_pair(
        tmp_path,
        stem='collection-mixed',
        source_url='https://www.harpercollins.com/collections/new-releases',
        next_url=None,
        rows=rows,
    )

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))

    rejected = [item for item in report.evidence if item.error_code == 'COLLECTION_ROWS_REJECTED']
    assert len(rejected) == 2
    assert all(item.status is EvidenceStatus.VALIDATION_FAILED for item in rejected)
    assert all(item.matched_count == 1 for item in rejected)
    assert 'TEMPLATE_DRIFT' in _codes(report)


@pytest.mark.parametrize(
    ('mode', 'expected_code'),
    [
        ('repeat', 'DUPLICATE_PAGE'),
        ('empty', 'EMPTY'),
        ('limit', 'PAGE_LIMIT_REACHED'),
    ],
)
def test_collection_pagination_stops_explicitly(tmp_path: Path, mode: str, expected_code: str) -> None:
    api = _observer_api()
    fixtures: list[dict[str, object]] = []
    page_count = 12 if mode == 'limit' else 3
    for page in range(1, page_count + 1):
        if mode == 'empty' and page == 2:
            rows: list[dict[str, str]] = []
        elif mode == 'repeat':
            rows = [{'title': 'Same', 'url': 'https://www.harpercollins.com/products/same'}]
        else:
            rows = [{'title': str(page), 'url': f'https://www.harpercollins.com/products/book-{page}'}]
        next_url = (
            f'https://www.harpercollins.com/collections/new-releases?page={page + 1}' if page < page_count else None
        )
        for method in ('css', 'xpath'):
            name = f'collection-page-{page}-{method}.json'
            _write_json(tmp_path / name, rows)
            fixtures.append(_collection_item(name, page, next_url))
    manifest = _write_manifest(tmp_path / 'manifest.json', fixtures)

    report = api.observe_fixture_manifest(manifest)

    assert expected_code in _codes(report)
    if mode == 'limit':
        assert not any(marker in item.document_id for marker in ('page-11', 'page-12') for item in report.evidence)
    else:
        assert not any('page-3' in item.document_id for item in report.evidence)


def test_missing_declared_next_page_is_explicit_failure(tmp_path: Path) -> None:
    api = _observer_api()
    next_url = 'https://www.harpercollins.com/collections/new-releases?page=2'
    fixtures = _write_collection_pair(
        tmp_path,
        stem='collection-page-1',
        source_url='https://www.harpercollins.com/collections/new-releases?page=1',
        next_url=next_url,
        rows=[
            {
                'title': 'One',
                'url': 'https://www.harpercollins.com/products/one',
            }
        ],
    )

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))

    missing = [item for item in report.evidence if item.error_code == 'MISSING_NEXT_PAGE']
    assert len(missing) == 1
    assert missing[0].status is EvidenceStatus.EXTRACTION_FAILED
    assert missing[0].detail == next_url


def test_collection_page_metadata_must_match_source_url(tmp_path: Path) -> None:
    api = _observer_api()
    fixtures = [
        _collection_item('collection-page-1-css.json', page=2),
        _collection_item('collection-page-1-xpath.json', page=2),
    ]
    for item in fixtures:
        item['page'] = 1

    with pytest.raises(ValueError, match='page metadata'):
        api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))


def test_collection_self_cycle_emits_duplicate_page_evidence(tmp_path: Path) -> None:
    api = _observer_api()
    url = 'https://www.harpercollins.com/collections/new-releases?page=1'
    fixtures = _write_collection_pair(
        tmp_path,
        stem='collection-self',
        source_url=url,
        next_url=url,
        rows=[{'title': 'One', 'url': 'https://www.harpercollins.com/products/one'}],
    )

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))

    assert 'DUPLICATE_PAGE' in _codes(report)
    assert any('cycle' in item.document_id for item in report.evidence)


def test_collection_root_entering_cycle_emits_duplicate_page_evidence(
    tmp_path: Path,
) -> None:
    api = _observer_api()
    urls = [f'https://www.harpercollins.com/collections/new-releases?page={page}' for page in (1, 2, 3)]
    fixtures: list[dict[str, object]] = []
    for index, (source_url, next_url) in enumerate(zip(urls, (urls[1], urls[2], urls[1]), strict=True), start=1):
        fixtures.extend(
            _write_collection_pair(
                tmp_path,
                stem=f'collection-cycle-{index}',
                source_url=source_url,
                next_url=next_url,
                rows=[
                    {
                        'title': f'Book {index}',
                        'url': f'https://www.harpercollins.com/products/book-{index}',
                    }
                ],
            )
        )

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', fixtures))

    assert 'DUPLICATE_PAGE' in _codes(report)
    assert len(report.candidate_urls) == 3


@pytest.mark.parametrize('source', ['hachette', 'penguin-random-house', ''])
def test_non_harper_source_is_rejected_before_documents_are_read(tmp_path: Path, source: str) -> None:
    api = _observer_api()
    manifest = _write_manifest(
        tmp_path / 'manifest.json',
        [{'name': 'does-not-exist.json', 'source_url': 'https://example.test'}],
        source=source,
    )

    with pytest.raises(ValueError, match='harpercollins'):
        api.observe_fixture_manifest(manifest)


@pytest.mark.parametrize('invalid_entry', [None, [], 'fixture', 7])
def test_non_object_manifest_entries_are_rejected_before_fixture_reads(tmp_path: Path, invalid_entry: object) -> None:
    api = _observer_api()
    manifest = tmp_path / 'manifest.json'
    _write_json(
        manifest,
        {
            'source': 'harpercollins',
            'fixtures': [
                invalid_entry,
                {
                    'name': 'does-not-exist.json',
                    'source_url': 'https://www.harpercollins.com/products/missing',
                },
            ],
        },
    )

    with pytest.raises(ValueError, match='object'):
        api.observe_fixture_manifest(manifest)


def test_symlinked_fixture_files_are_rejected_including_chains(tmp_path: Path) -> None:
    api = _observer_api()
    payload = {
        'product': {
            'title': 'Linked',
            'handle': 'linked',
            'images': [],
            'variants': [],
        }
    }
    outside = tmp_path.parent / f'{tmp_path.name}-outside.json'
    _write_json(outside, payload)
    real = tmp_path / 'real-product.json'
    _write_json(real, payload)
    escape_link = tmp_path / 'product-escape.json'
    chain_tail = tmp_path / 'chain-tail.json'
    chain_head = tmp_path / 'product-chain.json'
    try:
        escape_link.symlink_to(outside)
        chain_tail.symlink_to(real)
        chain_head.symlink_to(chain_tail)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f'symlink creation unavailable: {error}')

    for fixture_name in (escape_link.name, chain_head.name):
        manifest = _write_manifest(
            tmp_path / f'{fixture_name}.manifest.json',
            [
                {
                    'name': fixture_name,
                    'source_url': 'https://www.harpercollins.com/products/linked',
                }
            ],
        )
        with pytest.raises(ValueError, match='symlink'):
            api.observe_fixture_manifest(manifest)


def test_missing_author_and_date_are_not_invented() -> None:
    api = _observer_api()

    record, evidence = api.parse_product_document(FIXTURE_DIR / 'product-missing-author.json')

    assert record.author is None
    assert record.publication_date is None
    assert record.missing_fields == ('author', 'publication_date')
    assert evidence.status is EvidenceStatus.VALIDATION_FAILED
    assert 'Unknown Author' not in str(record)


def test_empty_manifest_is_explicitly_empty(tmp_path: Path) -> None:
    api = _observer_api()

    report = api.observe_fixture_manifest(_write_manifest(tmp_path / 'manifest.json', []))

    assert report.empty_result is True
    assert report.evidence
    assert report.evidence[0].status is EvidenceStatus.EMPTY
    assert report.evidence[0].method is ExtractionMethod.MANIFEST
    assert report.records == report.candidate_urls == ()


def test_identical_runs_are_byte_for_byte_deterministic_and_safe() -> None:
    api = _observer_api()
    first = api.observe_fixture_manifest(FIXTURE_DIR / 'manifest.json').to_dict()
    second = api.observe_fixture_manifest(FIXTURE_DIR / 'manifest.json').to_dict()

    assert first == second
    serialized = json.dumps(first, sort_keys=True)
    for forbidden in (
        '"product":',
        '<feed',
        'raw_html',
        'DATABASE_URL',
        'SECRET_KEY',
        '/admin/import',
        'sqlite:///',
    ):
        assert forbidden not in serialized


def test_public_package_exports_observer_api() -> None:
    from app.services import publisher_observer

    assert publisher_observer.observe_fixture_manifest
    assert publisher_observer.parse_atom_candidates
    assert publisher_observer.parse_product_document


def test_observation_report_serializes_a_safe_deterministic_payload() -> None:
    edition = EditionObservation(format='Hardcover', isbn13='9780063416178', is_main=True)
    book = BookObservation(
        title='Whistler',
        author='Ann Patchett',
        source_url='https://www.harpercollins.com/products/whistler-ann-patchett',
        editions=(edition,),
        publication_date=None,
        missing_fields=('publication_date',),
    )
    evidence = ExtractionEvidence(
        document_id='product-whistler',
        source_url=book.source_url,
        method=ExtractionMethod.PRODUCT_JSON,
        status=EvidenceStatus.VALIDATION_FAILED,
        matched_count=1,
        input_sha256='a' * 64,
        error_code='MISSING_REQUIRED_FIELDS',
        detail='publication_date',
    )
    report = ObservationReport(
        source='harpercollins',
        schema_version='hc-observer-v1',
        records=(book,),
        evidence=(evidence,),
        candidate_urls=(book.source_url,),
        unverified_ai_candidates=(),
        ai_fallback_calls=0,
    )

    payload = report.to_dict()

    assert payload['empty_result'] is False
    assert payload['records'][0]['editions'][0]['isbn13'] == '9780063416178'
    assert payload['evidence'][0]['method'] == 'product_json'
    assert payload['evidence'][0]['status'] == 'validation_failed'
    assert 'raw_html' not in str(payload)
    assert 'content' not in str(payload)


def test_observation_report_serializes_tuples_in_stable_order() -> None:
    first = BookObservation(
        title='Alpha',
        author='A Author',
        source_url='https://example.test/products/a',
        editions=(
            EditionObservation('E-book', '9780063416185', False),
            EditionObservation('Hardcover', '9780063416178', True),
        ),
        publication_date=None,
        missing_fields=('publication_date', 'author'),
    )
    second = BookObservation(
        title='Beta',
        author='B Author',
        source_url='https://example.test/products/b',
        editions=(),
        publication_date=None,
        missing_fields=(),
    )
    report = ObservationReport(
        source='harpercollins',
        schema_version='hc-observer-v1',
        records=(second, first),
        evidence=(
            ExtractionEvidence(
                document_id='z-document',
                source_url=second.source_url,
                method=ExtractionMethod.XPATH,
                status=EvidenceStatus.VALID,
                matched_count=1,
                input_sha256='b' * 64,
                error_code=None,
                detail=None,
            ),
            ExtractionEvidence(
                document_id='a-document',
                source_url=first.source_url,
                method=ExtractionMethod.CSS,
                status=EvidenceStatus.VALID,
                matched_count=1,
                input_sha256='c' * 64,
                error_code=None,
                detail=None,
            ),
        ),
        candidate_urls=(second.source_url, first.source_url),
        unverified_ai_candidates=(
            TemplateCandidate('xpath', '//main', 'fallback'),
            TemplateCandidate('css', '.product', 'fallback'),
        ),
        ai_fallback_calls=2,
    )

    payload = report.to_dict()

    assert [item['title'] for item in payload['records']] == ['Alpha', 'Beta']
    assert [item['document_id'] for item in payload['evidence']] == [
        'a-document',
        'z-document',
    ]
    assert payload['candidate_urls'] == [first.source_url, second.source_url]
    assert [item['selector_kind'] for item in payload['unverified_ai_candidates']] == [
        'css',
        'xpath',
    ]
    assert [item['format'] for item in payload['records'][0]['editions']] == [
        'E-book',
        'Hardcover',
    ]
    assert payload['records'][0]['missing_fields'] == ['publication_date', 'author']


def test_fixture_manifest_lists_every_harpercollins_fixture() -> None:
    fixture_dir = Path(__file__).parent / 'fixtures' / 'publisher_observer' / 'harpercollins'
    manifest = json.loads((fixture_dir / 'manifest.json').read_text(encoding='utf-8'))
    fixture_names = {item['name'] for item in manifest['fixtures']}

    assert manifest['source'] == 'harpercollins'
    assert fixture_names == {
        'new-releases.atom',
        'product-whistler.json',
        'product-missing-author.json',
        'collection-page-1-css.json',
        'collection-page-1-xpath.json',
        'collection-page-2-css.json',
        'collection-page-2-xpath.json',
        'collection-drift-css.json',
        'collection-drift-xpath.json',
        'fixed-ai-candidate.json',
    }
    assert all('live' not in item and 'credentials' not in item for item in manifest['fixtures'])
    by_name = {item['name']: item for item in manifest['fixtures']}
    assert all(item['source_url'] for item in by_name.values())
    assert by_name['collection-page-1-xpath.json']['page'] == 1
    assert by_name['collection-page-1-xpath.json']['next_url'].endswith('page=2')
    assert by_name['collection-page-2-xpath.json'] == {
        'name': 'collection-page-2-xpath.json',
        'source_url': 'https://www.harpercollins.com/collections/new-releases?page=2',
        'page': 2,
        'next_url': None,
    }
