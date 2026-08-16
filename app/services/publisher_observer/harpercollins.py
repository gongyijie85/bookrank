"""Deterministic, fixture-only HarperCollins observation prototype.

This module parses captured inputs.  It deliberately has no crawler, network,
database, or rule-mutation integration.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import parse_qsl, urlsplit

from .contracts import (
    BookObservation,
    EditionObservation,
    EvidenceStatus,
    ExtractionEvidence,
    ExtractionMethod,
    ObservationReport,
)


class _FrozenDict(dict[str, Any]):
    def _reject(self, *_args: Any, **_kwargs: Any) -> NoReturn:
        raise TypeError('versioned extraction schemas are immutable')

    __setitem__ = _reject  # type: ignore[assignment]
    __delitem__ = _reject  # type: ignore[assignment]
    __ior__ = _reject  # type: ignore[assignment]
    clear = _reject  # type: ignore[assignment]
    pop = _reject  # type: ignore[assignment]
    popitem = _reject  # type: ignore[assignment]
    setdefault = _reject  # type: ignore[assignment]
    update = _reject  # type: ignore[assignment]


class _FrozenList(list[Any]):
    def _reject(self, *_args: Any, **_kwargs: Any) -> NoReturn:
        raise TypeError('versioned extraction schemas are immutable')

    __setitem__ = _reject  # type: ignore[assignment]
    __delitem__ = _reject  # type: ignore[assignment]
    __iadd__ = _reject  # type: ignore[assignment]
    __imul__ = _reject  # type: ignore[assignment]
    append = _reject  # type: ignore[assignment]
    clear = _reject  # type: ignore[assignment]
    extend = _reject  # type: ignore[assignment]
    insert = _reject  # type: ignore[assignment]
    pop = _reject  # type: ignore[assignment]
    remove = _reject  # type: ignore[assignment]
    reverse = _reject  # type: ignore[assignment]
    sort = _reject  # type: ignore[assignment]


def _freeze_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_schema(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return _FrozenList(_freeze_schema(item) for item in value)
    return value


SOURCE_ID = 'harpercollins'
SCHEMA_VERSION = 'hc-observer-v1'
MAX_COLLECTION_PAGES = 10

# Versioned extraction candidates for issue #125.  They are data only: this
# prototype compares previously captured CSS/XPath outputs and never executes
# selectors or imports a crawling framework.
COLLECTION_CSS_SCHEMA: dict[str, Any] = _freeze_schema(
    {
        'name': 'harpercollins-collection-css-v1',
        'baseSelector': 'article.product-card',
        'fields': [
            {'name': 'title', 'selector': 'a.product-card__title', 'type': 'text'},
            {
                'name': 'url',
                'selector': 'a.product-card__title',
                'type': 'attribute',
                'attribute': 'href',
            },
        ],
    }
)
COLLECTION_XPATH_SCHEMA: dict[str, Any] = _freeze_schema(
    {
        'name': 'harpercollins-collection-xpath-v1',
        'baseSelector': "//article[contains(@class, 'product-card')]",
        'fields': [
            {
                'name': 'title',
                # JsonXPathExtractionStrategy's text fields must select an element;
                # the strategy extracts that element's text itself.
                'selector': ".//a[contains(@class, 'product-card__title')]",
                'type': 'text',
            },
            {
                'name': 'url',
                'selector': ".//a[contains(@class, 'product-card__title')]",
                'type': 'attribute',
                'attribute': 'href',
            },
        ],
    }
)

_ALLOWED_HOST = 'www.harpercollins.com'
_PRODUCT_PREFIX = '/products/'
_ATOM_SOURCE_URL = 'https://www.harpercollins.com/blogs/literary-hub/new-releases.atom'
_COLLECTION_PATH = '/collections/new-releases'
_HANDLE_PATTERN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
_COLLECTION_SUFFIXES = ('-css.json', '-xpath.json')


def is_valid_isbn13(value: object) -> bool:
    """Return whether *value* is a checksum-valid ISBN-13 string."""

    if not isinstance(value, str) or len(value) != 13 or not value.isascii():
        return False
    if not value.isdigit() or not value.startswith(('978', '979')):
        return False
    checksum = sum(int(character) * (1 if index % 2 == 0 else 3) for index, character in enumerate(value[:12]))
    expected = (10 - checksum % 10) % 10
    return expected == int(value[-1])


def parse_atom_candidates(
    path: str | Path,
) -> tuple[tuple[str, ...], ExtractionEvidence]:
    """Parse allowlisted alternate product links from an Atom fixture."""

    fixture_path = Path(path)
    raw = fixture_path.read_bytes()
    digest = _digest(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return (), _evidence(
            fixture_path.name,
            '',
            ExtractionMethod.ATOM,
            EvidenceStatus.EXTRACTION_FAILED,
            0,
            digest,
            'ATOM_PARSE_ERROR',
        )

    candidates: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) != 'link':
            continue
        relation = element.attrib.get('rel', 'alternate')
        if relation != 'alternate':
            continue
        candidate = _normalize_product_url(element.attrib.get('href'))
        if candidate is not None and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    status = EvidenceStatus.VALID if candidates else EvidenceStatus.EMPTY
    error_code = None if candidates else 'NO_ALLOWED_PRODUCT_LINKS'
    return tuple(candidates), _evidence(
        fixture_path.name,
        '',
        ExtractionMethod.ATOM,
        status,
        len(candidates),
        digest,
        error_code,
    )


def parse_product_document(
    path: str | Path,
) -> tuple[BookObservation | None, ExtractionEvidence]:
    """Parse observed product fields without using Shopify timestamps as dates."""

    fixture_path = Path(path)
    raw = fixture_path.read_bytes()
    digest = _digest(raw)
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _evidence(
            fixture_path.name,
            '',
            ExtractionMethod.PRODUCT_JSON,
            EvidenceStatus.EXTRACTION_FAILED,
            0,
            digest,
            'PRODUCT_JSON_INVALID',
        )

    if not isinstance(document, dict) or not isinstance(document.get('product'), dict):
        return None, _evidence(
            fixture_path.name,
            '',
            ExtractionMethod.PRODUCT_JSON,
            EvidenceStatus.EXTRACTION_FAILED,
            0,
            digest,
            'PRODUCT_JSON_SHAPE_INVALID',
        )
    product = document['product']
    title_value = product.get('title')
    title = title_value.strip() if isinstance(title_value, str) else ''
    source_url = _canonical_product_url(product.get('handle')) or ''
    if not title or not source_url:
        return None, _evidence(
            fixture_path.name,
            source_url,
            ExtractionMethod.PRODUCT_JSON,
            EvidenceStatus.EXTRACTION_FAILED,
            0,
            digest,
            'PRODUCT_IDENTITY_MISSING',
        )
    author = _strict_author(product.get('images'), title)
    editions = _parse_editions(product.get('variants'))

    missing: list[str] = []
    if author is None:
        missing.append('author')
    if not editions:
        missing.append('isbn13')
    # Shopify's published_at/created_at/updated_at describe catalog state, not
    # the book's publication date, so the deterministic prototype ignores them.
    publication_date = None
    missing.append('publication_date')

    record = BookObservation(
        title=title,
        author=author,
        source_url=source_url,
        editions=editions,
        publication_date=publication_date,
        missing_fields=tuple(missing),
    )
    status = EvidenceStatus.VALID if not missing else EvidenceStatus.VALIDATION_FAILED
    return record, _evidence(
        fixture_path.name,
        source_url,
        ExtractionMethod.PRODUCT_JSON,
        status,
        len(editions),
        digest,
        None if not missing else 'MISSING_REQUIRED_FIELDS',
        None if not missing else ','.join(missing),
    )


def _validate_manifest_metadata(fixtures: list[dict[str, Any]]) -> None:
    for item in fixtures:
        name = item.get('name')
        if not isinstance(name, str) or not name:
            continue
        source_url = item.get('source_url')
        if not isinstance(source_url, str):
            raise ValueError(f'{name} source_url must be a string')
        if name.endswith('.atom'):
            if source_url != _ATOM_SOURCE_URL:
                raise ValueError('Atom source_url must be the canonical HarperCollins feed')
        elif name.startswith('product-') and name.endswith('.json'):
            if _normalize_product_url(source_url) != source_url:
                raise ValueError('product source_url must be an official HTTPS product URL')
        elif (name.endswith(_COLLECTION_SUFFIXES) or name == 'fixed-ai-candidate.json') and _normalize_collection_url(
            source_url
        ) != source_url:
            raise ValueError('collection or AI source_url must be the canonical HarperCollins collection URL')
        if name.endswith(_COLLECTION_SUFFIXES) and 'page' in item:
            page = item.get('page')
            if (
                isinstance(page, bool)
                or not isinstance(page, int)
                or page < 1
                or _collection_page_number(source_url) != page
            ):
                raise ValueError('collection page metadata must match the source_url page')
        if name.endswith(_COLLECTION_SUFFIXES) and 'next_url' in item:
            next_url = item.get('next_url')
            if next_url is not None and (
                not isinstance(next_url, str) or _normalize_collection_url(next_url) != next_url
            ):
                raise ValueError('collection next_url must be a canonical HarperCollins collection URL')


def observe_fixture_manifest(manifest_path: str | Path) -> ObservationReport:
    """Observe one HarperCollins fixture manifest without external side effects."""

    path = Path(manifest_path)
    manifest_raw = path.read_bytes()
    manifest_digest = _digest(manifest_raw)
    manifest = json.loads(manifest_raw)
    if not isinstance(manifest, dict) or manifest.get('source') != SOURCE_ID:
        # Source is checked before resolving or reading any listed document.
        raise ValueError('fixture manifest source must be harpercollins')
    fixtures_value = manifest.get('fixtures', [])
    if not isinstance(fixtures_value, list):
        raise ValueError('fixture manifest fixtures must be a list')
    if any(not isinstance(item, dict) for item in fixtures_value):
        raise ValueError('every fixture manifest entry must be an object')
    fixtures = [item for item in fixtures_value if isinstance(item, dict)]
    _validate_manifest_metadata(fixtures)

    if not fixtures:
        return ObservationReport(
            source=SOURCE_ID,
            schema_version=SCHEMA_VERSION,
            records=(),
            evidence=(
                _evidence(
                    path.name,
                    '',
                    ExtractionMethod.MANIFEST,
                    EvidenceStatus.EMPTY,
                    0,
                    manifest_digest,
                    'EMPTY_MANIFEST',
                ),
            ),
            candidate_urls=(),
            unverified_ai_candidates=(),
            ai_fallback_calls=0,
            manifest_sha256=manifest_digest,
        )

    base_dir = path.parent
    evidence: list[ExtractionEvidence] = []
    records: list[BookObservation] = []
    candidate_urls: list[str] = []
    seen_candidates: set[str] = set()
    collection_items: list[dict[str, Any]] = []

    for item in fixtures:
        name = item.get('name')
        source_url = _string_value(item, 'source_url')
        if not isinstance(name, str) or not name:
            evidence.append(
                _metadata_evidence(
                    'invalid-manifest-item',
                    source_url,
                    ExtractionMethod.CSS,
                    EvidenceStatus.EXTRACTION_FAILED,
                    item,
                    'INVALID_MANIFEST_ITEM',
                )
            )
            continue
        if name.endswith(_COLLECTION_SUFFIXES):
            collection_items.append(item)
            continue
        if item.get('status') == EvidenceStatus.ACCESS_BLOCKED.value:
            evidence.append(
                _metadata_evidence(
                    name,
                    source_url,
                    _method_from_name(name),
                    EvidenceStatus.ACCESS_BLOCKED,
                    item,
                    'ACCESS_BLOCKED',
                )
            )
            continue
        if name == 'fixed-ai-candidate.json':
            continue

        fixture_path = _safe_fixture_path(base_dir, name)
        if name.endswith('.atom'):
            candidates, item_evidence = parse_atom_candidates(fixture_path)
            evidence.append(replace(item_evidence, source_url=source_url))
            _extend_unique(candidate_urls, seen_candidates, candidates)
        elif name.startswith('product-') and name.endswith('.json'):
            record, item_evidence = parse_product_document(fixture_path)
            if record is not None and source_url != record.source_url:
                raise ValueError('product source_url must equal the fixture canonical product URL')
            evidence.append(
                replace(
                    item_evidence,
                    source_url=record.source_url if record is not None else '',
                )
            )
            if record is not None:
                records.append(record)
                if record.source_url:
                    _extend_unique(candidate_urls, seen_candidates, (record.source_url,))
        else:
            raw = fixture_path.read_bytes()
            evidence.append(
                _evidence(
                    name,
                    source_url,
                    ExtractionMethod.PRODUCT_JSON,
                    EvidenceStatus.EXTRACTION_FAILED,
                    0,
                    _digest(raw),
                    'UNSUPPORTED_FIXTURE',
                )
            )

    collection_evidence, collection_candidates = _observe_collections(base_dir, collection_items, manifest_digest)
    evidence.extend(collection_evidence)
    _extend_unique(candidate_urls, seen_candidates, collection_candidates)

    return ObservationReport(
        source=SOURCE_ID,
        schema_version=SCHEMA_VERSION,
        records=tuple(records),
        evidence=tuple(evidence),
        candidate_urls=tuple(candidate_urls),
        unverified_ai_candidates=(),
        ai_fallback_calls=0,
        manifest_sha256=manifest_digest,
    )


def _observe_collections(
    base_dir: Path,
    items: list[dict[str, Any]],
    manifest_digest: str,
) -> tuple[list[ExtractionEvidence], tuple[str, ...]]:
    evidence: list[ExtractionEvidence] = []
    candidates: list[str] = []
    seen_candidates: set[str] = set()
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    members: dict[str, list[tuple[ExtractionMethod, dict[str, Any]]]] = {}
    duplicate_member_keys: set[str] = set()
    order: list[str] = []
    for item in items:
        name = item.get('name')
        if not isinstance(name, str):
            continue
        method = 'css' if name.endswith('-css.json') else 'xpath'
        key = name.removesuffix(f'-{method}.json')
        if key not in pairs:
            pairs[key] = {}
            members[key] = []
            order.append(key)
        extraction_method = ExtractionMethod.CSS if method == 'css' else ExtractionMethod.XPATH
        members[key].append((extraction_method, item))
        if method in pairs[key]:
            duplicate_member_keys.add(key)
        else:
            pairs[key][method] = item

    for key in order:
        pair = pairs[key]
        css = pair.get('css')
        xpath = pair.get('xpath')
        if (
            css is not None
            and xpath is not None
            and any(css.get(field) != xpath.get(field) for field in ('source_url', 'next_url', 'page'))
        ):
            raise ValueError('CSS/XPath collection pair metadata must agree')

    keys_by_source: dict[str, list[str]] = {}
    for key in order:
        keys_by_source.setdefault(_pair_source_url(pairs[key]), []).append(key)
    duplicate_source_keys = {
        key for source_keys in keys_by_source.values() if len(source_keys) > 1 for key in source_keys
    }
    conflicted_keys = duplicate_member_keys | duplicate_source_keys
    for key in order:
        if key not in conflicted_keys:
            continue
        error_code = 'DUPLICATE_COLLECTION_MEMBER' if key in duplicate_member_keys else 'DUPLICATE_SOURCE_URL'
        evidence.extend(
            _collection_conflict_evidence(base_dir, item, method, error_code) for method, item in members[key]
        )

    traversal_order = [key for key in order if key not in conflicted_keys]

    source_to_key = {_pair_source_url(pairs[pair_key]): pair_key for pair_key in traversal_order}
    referenced_urls = {
        next_url
        for key, pair in pairs.items()
        if key in traversal_order
        if (next_url := _pair_next_url(pair)) is not None
    }
    roots = [pair_key for pair_key in traversal_order if _pair_source_url(pairs[pair_key]) not in referenced_urls]
    visited: set[str] = set()
    suppressed: set[str] = set()

    for root in roots + [key for key in traversal_order if key not in roots]:
        if root in visited or root in suppressed:
            continue
        current_key: str | None = root
        page_count = 0
        signatures: set[tuple[str, ...]] = set()
        while current_key is not None and current_key not in suppressed:
            if current_key in visited:
                evidence.append(_cycle_evidence(current_key, pairs[current_key], manifest_digest))
                break
            pair = pairs[current_key]
            source_url = _pair_source_url(pair)
            if page_count >= MAX_COLLECTION_PAGES:
                evidence.append(
                    _evidence(
                        'collection-page-limit',
                        source_url,
                        ExtractionMethod.CSS,
                        EvidenceStatus.EMPTY,
                        0,
                        manifest_digest,
                        'PAGE_LIMIT_REACHED',
                    )
                )
                _suppress_collection_chain(current_key, pairs, source_to_key, visited, suppressed)
                break

            visited.add(current_key)
            page_count += 1
            css_urls, css_evidence = _read_collection_output(base_dir, pair.get('css'), ExtractionMethod.CSS)
            xpath_urls, xpath_evidence = _read_collection_output(base_dir, pair.get('xpath'), ExtractionMethod.XPATH)
            stop_series = False

            if EvidenceStatus.ACCESS_BLOCKED in {
                css_evidence.status,
                xpath_evidence.status,
            }:
                evidence.extend((css_evidence, xpath_evidence))
                stop_series = True
            elif css_evidence.error_code or xpath_evidence.error_code:
                evidence.extend((css_evidence, xpath_evidence))
                evidence.append(
                    _evidence(
                        f'{current_key}-parity',
                        source_url,
                        ExtractionMethod.XPATH,
                        EvidenceStatus.EXTRACTION_FAILED,
                        0,
                        _combined_digest(css_evidence.input_sha256, xpath_evidence.input_sha256),
                        'TEMPLATE_DRIFT',
                    )
                )
                stop_series = True
            elif not css_urls and not xpath_urls:
                evidence.extend(
                    (
                        replace(
                            css_evidence,
                            status=EvidenceStatus.EXTRACTION_FAILED,
                            error_code='TEMPLATE_DRIFT',
                        ),
                        replace(
                            xpath_evidence,
                            status=EvidenceStatus.EXTRACTION_FAILED,
                            error_code='TEMPLATE_DRIFT',
                        ),
                        _evidence(
                            f'{current_key}-pagination',
                            source_url,
                            ExtractionMethod.CSS,
                            EvidenceStatus.EMPTY,
                            0,
                            _combined_digest(css_evidence.input_sha256, xpath_evidence.input_sha256),
                            'EMPTY',
                        ),
                    )
                )
                stop_series = True
            elif css_urls != xpath_urls:
                evidence.extend(
                    (
                        replace(
                            css_evidence,
                            status=EvidenceStatus.EXTRACTION_FAILED,
                            error_code='TEMPLATE_DRIFT',
                        ),
                        replace(
                            xpath_evidence,
                            status=EvidenceStatus.EXTRACTION_FAILED,
                            error_code='TEMPLATE_DRIFT',
                        ),
                    )
                )
            elif css_urls in signatures:
                evidence.extend(
                    (
                        replace(
                            css_evidence,
                            status=EvidenceStatus.EMPTY,
                            error_code='DUPLICATE_PAGE',
                        ),
                        replace(
                            xpath_evidence,
                            status=EvidenceStatus.EMPTY,
                            error_code='DUPLICATE_PAGE',
                        ),
                    )
                )
                stop_series = True
            else:
                signatures.add(css_urls)
                evidence.extend((css_evidence, xpath_evidence))
                _extend_unique(candidates, seen_candidates, css_urls)

            if stop_series:
                next_url = _pair_next_url(pair)
                next_key = source_to_key.get(next_url) if next_url is not None else None
                _suppress_collection_chain(next_key, pairs, source_to_key, visited, suppressed)
                break
            next_url = _pair_next_url(pair)
            next_key = source_to_key.get(next_url) if next_url is not None else None
            if next_url is not None and next_key is None:
                evidence.append(
                    _evidence(
                        f'{current_key}-missing-next-page',
                        source_url,
                        ExtractionMethod.CSS,
                        EvidenceStatus.EXTRACTION_FAILED,
                        0,
                        manifest_digest,
                        'MISSING_NEXT_PAGE',
                        next_url,
                    )
                )
                break
            if next_key is not None and next_key in visited:
                evidence.append(_cycle_evidence(current_key, pair, manifest_digest))
                break
            current_key = next_key

    return evidence, tuple(candidates)


def _cycle_evidence(
    key: str,
    pair: dict[str, dict[str, Any]],
    manifest_digest: str,
) -> ExtractionEvidence:
    return _evidence(
        f'{key}-pagination-cycle',
        _pair_source_url(pair),
        ExtractionMethod.CSS,
        EvidenceStatus.EMPTY,
        0,
        manifest_digest,
        'DUPLICATE_PAGE',
    )


def _suppress_collection_chain(
    start_key: str | None,
    pairs: dict[str, dict[str, dict[str, Any]]],
    source_to_key: dict[str, str],
    visited: set[str],
    suppressed: set[str],
) -> None:
    current_key = start_key
    while current_key is not None and current_key not in visited and current_key not in suppressed:
        suppressed.add(current_key)
        next_url = _pair_next_url(pairs[current_key])
        current_key = source_to_key.get(next_url) if next_url is not None else None


def _collection_conflict_evidence(
    base_dir: Path,
    item: dict[str, Any],
    method: ExtractionMethod,
    error_code: str,
) -> ExtractionEvidence:
    name = item.get('name')
    source_url = _string_value(item, 'source_url')
    if not isinstance(name, str) or item.get('status') == EvidenceStatus.ACCESS_BLOCKED.value:
        return _metadata_evidence(
            name if isinstance(name, str) else 'invalid-collection-item',
            source_url,
            method,
            EvidenceStatus.EXTRACTION_FAILED,
            item,
            error_code,
        )
    raw = _safe_fixture_path(base_dir, name).read_bytes()
    return _evidence(
        name,
        source_url,
        method,
        EvidenceStatus.EXTRACTION_FAILED,
        0,
        _digest(raw),
        error_code,
    )


def _read_collection_output(
    base_dir: Path,
    item: dict[str, Any] | None,
    method: ExtractionMethod,
) -> tuple[tuple[str, ...], ExtractionEvidence]:
    if item is None:
        digest = _digest(f'missing:{method.value}'.encode())
        return (), _evidence(
            f'missing-{method.value}',
            '',
            method,
            EvidenceStatus.EXTRACTION_FAILED,
            0,
            digest,
            'MISSING_PARITY_FIXTURE',
        )
    name = item.get('name')
    source_url = _string_value(item, 'source_url')
    if not isinstance(name, str):
        return (), _metadata_evidence(
            'invalid-collection-item',
            source_url,
            method,
            EvidenceStatus.EXTRACTION_FAILED,
            item,
            'INVALID_MANIFEST_ITEM',
        )
    if item.get('status') == EvidenceStatus.ACCESS_BLOCKED.value:
        return (), _metadata_evidence(
            name,
            source_url,
            method,
            EvidenceStatus.ACCESS_BLOCKED,
            item,
            'ACCESS_BLOCKED',
        )
    raw = _safe_fixture_path(base_dir, name).read_bytes()
    digest = _digest(raw)
    try:
        rows = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        rows = None
    if not isinstance(rows, list):
        return (), _evidence(
            name,
            source_url,
            method,
            EvidenceStatus.EXTRACTION_FAILED,
            0,
            digest,
            'COLLECTION_JSON_INVALID',
        )

    urls: list[str] = []
    seen: set[str] = set()
    rejected_count = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected_count += 1
            continue
        title = row.get('title')
        url = _normalize_product_url(row.get('url'))
        if not isinstance(title, str) or not title.strip() or url is None:
            rejected_count += 1
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    status = EvidenceStatus.VALIDATION_FAILED if rejected_count else EvidenceStatus.VALID
    return tuple(urls), _evidence(
        name,
        source_url,
        method,
        status,
        len(urls),
        digest,
        'COLLECTION_ROWS_REJECTED' if rejected_count else None,
        f'rejected_rows={rejected_count}' if rejected_count else None,
    )


def _parse_editions(value: object) -> tuple[EditionObservation, ...]:
    if not isinstance(value, list):
        return ()
    best_by_isbn: dict[str, tuple[int, int, str, str, bool]] = {}
    for index, variant in enumerate(value):
        if not isinstance(variant, dict):
            continue
        format_value = variant.get('title')
        book_format = format_value.strip() if isinstance(format_value, str) else ''
        if not book_format:
            continue
        isbn = next(
            (candidate for field in ('barcode', 'sku') if is_valid_isbn13(candidate := variant.get(field))),
            None,
        )
        if not isinstance(isbn, str):
            continue
        rank, is_print = _format_rank(book_format)
        representation = (rank, index, book_format, isbn, is_print)
        current = best_by_isbn.get(isbn)
        if current is None or representation[:2] < current[:2]:
            best_by_isbn[isbn] = representation
    observed = list(best_by_isbn.values())
    observed.sort(key=lambda item: (item[0], item[1]))
    main_isbn = next((item[3] for item in observed if item[4]), None)
    return tuple(EditionObservation(book_format, isbn, isbn == main_isbn) for _, _, book_format, isbn, _ in observed)


def _format_rank(value: str) -> tuple[int, bool]:
    normalized = re.sub(r'\s+', ' ', value.strip().casefold())
    ranks: dict[str, tuple[int, bool]] = {
        'hardcover': (0, True),
        'trade paperback': (1, True),
        'paperback': (2, True),
        'large print': (3, True),
        'e-book': (10, False),
        'ebook': (10, False),
        'digital': (10, False),
        'audiobook': (11, False),
        'audio': (11, False),
    }
    return ranks.get(normalized, (20, False))


def _strict_author(images: object, title: str) -> str | None:
    if not title or not isinstance(images, list):
        return None
    pattern = re.compile(rf'{re.escape(title)} by (?P<author>[^()]+) \((?P<isbn>\d{{13}})\)')
    for image in images:
        if not isinstance(image, dict):
            continue
        alt = image.get('alt')
        if not isinstance(alt, str):
            continue
        match = pattern.fullmatch(alt)
        if match and is_valid_isbn13(match.group('isbn')):
            author = match.group('author').strip()
            return author or None
    return None


def _canonical_product_url(handle: object) -> str | None:
    if not isinstance(handle, str) or _HANDLE_PATTERN.fullmatch(handle) is None:
        return None
    return f'https://{_ALLOWED_HOST}{_PRODUCT_PREFIX}{handle}'


def _normalize_product_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme != 'https' or parsed.netloc != _ALLOWED_HOST or not parsed.path.startswith(_PRODUCT_PREFIX):
        return None
    handle = parsed.path.removeprefix(_PRODUCT_PREFIX).rstrip('/')
    if _HANDLE_PATTERN.fullmatch(handle) is None:
        return None
    return _canonical_product_url(handle)


def _normalize_collection_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.netloc != _ALLOWED_HOST or parsed.path != _COLLECTION_PATH or parsed.fragment:
        return None
    canonical = f'https://{_ALLOWED_HOST}{_COLLECTION_PATH}'
    if not parsed.query:
        return canonical
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if len(query) != 1 or query[0][0] != 'page':
        return None
    page = query[0][1]
    if not page.isascii() or not page.isdigit() or int(page) < 1 or str(int(page)) != page:
        return None
    return f'{canonical}?page={page}'


def _collection_page_number(value: str) -> int | None:
    normalized = _normalize_collection_url(value)
    if normalized is None:
        return None
    query = parse_qsl(urlsplit(normalized).query, keep_blank_values=True)
    return int(query[0][1]) if query else 1


def _safe_fixture_path(base_dir: Path, name: str) -> Path:
    if Path(name).name != name:
        raise ValueError('fixture names must be plain filenames')
    resolved_base = base_dir.resolve(strict=True)
    candidate = resolved_base / name
    if candidate.is_symlink():
        raise ValueError('symlinked fixture files are not allowed')
    resolved_candidate = candidate.resolve(strict=True)
    try:
        resolved_candidate.relative_to(resolved_base)
    except ValueError as error:
        raise ValueError('fixture path escapes manifest directory') from error
    return resolved_candidate


def _method_from_name(name: str) -> ExtractionMethod:
    if name.endswith('.atom'):
        return ExtractionMethod.ATOM
    if name.endswith('-css.json'):
        return ExtractionMethod.CSS
    if name.endswith('-xpath.json'):
        return ExtractionMethod.XPATH
    if name == 'fixed-ai-candidate.json':
        return ExtractionMethod.AI_CANDIDATE
    return ExtractionMethod.PRODUCT_JSON


def _string_value(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ''


def _pair_source_url(pair: dict[str, dict[str, Any]]) -> str:
    for method in ('css', 'xpath'):
        value = pair.get(method, {}).get('source_url')
        if isinstance(value, str):
            return value
    return ''


def _pair_next_url(pair: dict[str, dict[str, Any]]) -> str | None:
    for method in ('css', 'xpath'):
        item = pair.get(method, {})
        if 'next_url' in item:
            value = item.get('next_url')
            return value if isinstance(value, str) and value else None
    return None


def _extend_unique(target: list[str], seen: set[str], values: tuple[str, ...]) -> None:
    for value in values:
        if value not in seen:
            seen.add(value)
            target.append(value)


def _local_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def _metadata_evidence(
    document_id: str,
    source_url: str,
    method: ExtractionMethod,
    status: EvidenceStatus,
    metadata: object,
    error_code: str,
) -> ExtractionEvidence:
    raw = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
    return _evidence(document_id, source_url, method, status, 0, _digest(raw), error_code)


def _evidence(
    document_id: str,
    source_url: str,
    method: ExtractionMethod,
    status: EvidenceStatus,
    matched_count: int,
    input_sha256: str,
    error_code: str | None,
    detail: str | None = None,
) -> ExtractionEvidence:
    return ExtractionEvidence(
        document_id=document_id,
        source_url=source_url,
        method=method,
        status=status,
        matched_count=matched_count,
        input_sha256=input_sha256,
        error_code=error_code,
        detail=detail,
    )


def _combined_digest(first: str, second: str) -> str:
    return _digest(f'{first}:{second}'.encode())


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


__all__ = [
    'COLLECTION_CSS_SCHEMA',
    'COLLECTION_XPATH_SCHEMA',
    'MAX_COLLECTION_PAGES',
    'SCHEMA_VERSION',
    'SOURCE_ID',
    'is_valid_isbn13',
    'observe_fixture_manifest',
    'parse_atom_candidates',
    'parse_product_document',
]
