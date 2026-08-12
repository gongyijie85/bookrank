# HarperCollins Observation Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the no-write HarperCollins fixture prototype requested by GitHub #120 so a human can review the extraction choices before the Crawl4AI runner in #125 is implemented.

**Architecture:** Add a new `publisher_observer` package that is deliberately disconnected from Flask, SQLAlchemy, `BookInfo`, crawler registration, and production sync. Pure functions parse trimmed Atom and Shopify product JSON fixtures, compare already-extracted CSS/XPath collection observations, enforce bounded pagination, and build a deterministic audit report. A fixed-response template fallback may add an unverified candidate once per source/run; it never changes extraction rules or promotes a record.

**Tech Stack:** Python 3.13-compatible standard library, dataclasses, enums, `xml.etree.ElementTree`, pytest. Crawl4AI and Playwright are intentionally deferred to #125.

---

## Non-negotiable scope

- Only `harpercollins` is accepted as a source. `hachette` and arbitrary source identifiers fail closed.
- No network calls, database imports, Flask app creation, production secrets, write endpoints, or changes under `static/data/`.
- Atom timestamps and Shopify `published_at`/`created_at` are discovery metadata, never publication dates.
- ISBN-13 values must pass checksum validation. All valid editions are retained; the main edition is chosen deterministically from print formats.
- CSS is the recommended primary collection strategy; XPath is a parity oracle. The prototype consumes fixture outputs from both strategies; #125 will execute the schemas through Crawl4AI.
- Zero selector matches, CSS/XPath disagreement, duplicate pagination, empty pages, access blocks, and missing required fields remain explicit report evidence.
- AI fallback uses a fixed fixture response, is invoked only for extraction drift, and is capped at one invocation per source/run. It cannot run for robots/access failures.
- Reports contain content digests and compact errors, never raw successful pages or full failed pages.

### Task 1: Observation contracts and trimmed fixtures

**Files:**
- Create: `app/services/publisher_observer/__init__.py`
- Create: `app/services/publisher_observer/contracts.py`
- Create: `tests/fixtures/publisher_observer/harpercollins/manifest.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/new-releases.atom`
- Create: `tests/fixtures/publisher_observer/harpercollins/product-whistler.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/product-missing-author.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/collection-page-1-css.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/collection-page-1-xpath.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/collection-page-2-css.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/collection-page-2-xpath.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/collection-drift-css.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/collection-drift-xpath.json`
- Create: `tests/fixtures/publisher_observer/harpercollins/fixed-ai-candidate.json`
- Create: `tests/test_harpercollins_observation_config.py`

- [ ] **Step 1: Write failing contract and serialization tests**

Add tests that instantiate the public contracts and assert stable JSON-ready output. Use this public shape:

```python
from app.services.publisher_observer.contracts import (
    BookObservation,
    EditionObservation,
    EvidenceStatus,
    ExtractionEvidence,
    ExtractionMethod,
    ObservationReport,
)


def test_observation_report_serializes_stably_without_raw_page_content():
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
    assert payload['write_enabled'] is False
    assert payload['records'][0]['editions'][0]['isbn13'] == '9780063416178'
    assert 'raw_html' not in repr(payload)
    assert 'content' not in payload['evidence'][0]
```

Also test that tuple ordering is preserved and enum values serialize as lower snake-case strings.

- [ ] **Step 2: Run the contract test and verify the expected import failure**

Run:

```powershell
python -m pytest tests/test_harpercollins_observation_config.py -q --no-cov
```

Expected: FAIL during collection because `app.services.publisher_observer` does not exist.

- [ ] **Step 3: Implement immutable contracts**

Create enums with these exact values:

```python
class ExtractionMethod(StrEnum):
    ATOM = 'atom'
    PRODUCT_JSON = 'product_json'
    CSS = 'css'
    XPATH = 'xpath'
    AI_CANDIDATE = 'ai_candidate'


class EvidenceStatus(StrEnum):
    VALID = 'valid'
    EXTRACTION_FAILED = 'extraction_failed'
    VALIDATION_FAILED = 'validation_failed'
    ACCESS_BLOCKED = 'access_blocked'
    EMPTY = 'empty'
```

Implement frozen dataclasses with the fields shown in the test. `EditionObservation` has `format`, `isbn13`, and `is_main`. `BookObservation` has `title`, `author`, `source_url`, `editions`, `publication_date`, and `missing_fields`. `ExtractionEvidence` has `document_id`, `source_url`, `method`, `status`, `matched_count`, `input_sha256`, `error_code`, and `detail`. Add a frozen `TemplateCandidate` with `selector_kind`, `selector`, `reason`, and `verified=False`.

`ObservationReport` has `source`, `schema_version`, `records`, `evidence`, `candidate_urls`, `unverified_ai_candidates`, `ai_fallback_calls`, and fixed `write_enabled=False`. Its `empty_result` property is `not self.records`. Its `to_dict()` must recursively turn dataclasses, tuples, and enums into JSON-ready primitives and must sort records by `(source_url, title)`, candidate URLs lexicographically, evidence by `(document_id, method.value)`, and AI candidates by `(selector_kind, selector)`.

Export only these public types from `app/services/publisher_observer/__init__.py`; do not register a crawler.

- [ ] **Step 4: Add minimal factual fixtures**

The Atom fixture contains two entries with canonical `/products/...` links and one deliberate duplicate link. The Whistler product fixture contains a valid Hardcover ISBN `9780063416178`, a valid E-book ISBN `9780063416185`, an image alt of `Whistler by Ann Patchett (9780063416178)`, and a Shopify `published_at` timestamp. The missing-author fixture contains a valid print ISBN but no independent author and no matching image alt. Keep descriptions and copyrighted prose out of the fixtures.

Each collection output fixture is a compact array of objects with only `title` and `url`; the page-1 CSS and XPath arrays are equivalent, as are page 2. Drift arrays are empty. `manifest.json` names each fixture, supplies source URL/page number/next URL, and sets `source` to `harpercollins`; it contains no live execution flag or credential field. The fixed AI fixture contains one selector candidate, not a book record.

- [ ] **Step 5: Run contract tests**

Run:

```powershell
python -m pytest tests/test_harpercollins_observation_config.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 6: Run lint and commit Task 1**

Run:

```powershell
ruff check app/services/publisher_observer tests/test_harpercollins_observation_config.py
```

Expected: PASS.

Commit:

```powershell
git add app/services/publisher_observer tests/fixtures/publisher_observer tests/test_harpercollins_observation_config.py
git commit -m "feat(observer): define HarperCollins observation contracts"
```

### Task 2: Deterministic HarperCollins prototype and audit report

**Files:**
- Create: `app/services/publisher_observer/harpercollins.py`
- Modify: `app/services/publisher_observer/__init__.py`
- Modify: `tests/test_harpercollins_observation_config.py`
- Create: `research/issue-120-harpercollins-observation-prototype.md`

- [ ] **Step 1: Write failing behavior tests**

Add fixture-to-report tests against these public functions/classes:

```python
from app.services.publisher_observer.harpercollins import (
    FixedTemplateFallback,
    observe_fixture_manifest,
    parse_atom_candidates,
    parse_product_document,
)


def test_product_json_retains_editions_and_never_uses_shopify_time_as_publication_date(fixtures_dir):
    book, evidence = parse_product_document(fixtures_dir / 'product-whistler.json')

    assert book.title == 'Whistler'
    assert book.author == 'Ann Patchett'
    assert [edition.isbn13 for edition in book.editions] == ['9780063416178', '9780063416185']
    assert [edition.is_main for edition in book.editions] == [True, False]
    assert book.publication_date is None
    assert book.missing_fields == ('publication_date',)
    assert evidence.status is EvidenceStatus.VALIDATION_FAILED


def test_fixture_manifest_builds_auditable_report_and_caps_ai_fallback(fixtures_dir):
    fallback = FixedTemplateFallback.from_path(fixtures_dir / 'fixed-ai-candidate.json')

    report = observe_fixture_manifest(fixtures_dir / 'manifest.json', fallback=fallback)

    assert report.source == 'harpercollins'
    assert report.schema_version == 'hc-observer-v1'
    assert report.ai_fallback_calls == 1
    assert fallback.call_count == 1
    assert report.unverified_ai_candidates[0].verified is False
    assert any(item.error_code == 'TEMPLATE_DRIFT' for item in report.evidence)
    assert all(len(item.input_sha256) == 64 for item in report.evidence)
    assert report.write_enabled is False
```

Add separate tests for:

- Atom candidate de-duplication and the fact that Atom dates never populate publication dates.
- ISBN-13 checksum rejection and deterministic main-print ranking: Hardcover, Trade Paperback/Paperback, Large Print; electronic/audio formats never become main.
- Equivalent CSS/XPath fixture outputs produce valid parity evidence; disagreement produces `TEMPLATE_DRIFT`.
- Page 2 is included; a repeated page signature, empty page, or more than 10 pages stops traversal with explicit evidence.
- Multiple drift pages call the fixed fallback once total.
- `ACCESS_BLOCKED` evidence never calls the fallback.
- A manifest with `source: hachette` or any source other than `harpercollins` raises `ValueError` before reading listed documents.
- Missing author and publication date remain explicit missing fields; no `Unknown Author` or invented value appears.
- Empty manifests produce an empty report with `EvidenceStatus.EMPTY`, not success.
- Two identical runs produce identical `to_dict()` output.
- The report contains no fixture content, raw HTML, production secret names, import URL, or database path.

- [ ] **Step 2: Run behavior tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_harpercollins_observation_config.py -q --no-cov
```

Expected: FAIL because `harpercollins.py` and its functions do not exist.

- [ ] **Step 3: Implement deterministic parsing and comparison**

In `harpercollins.py`, define `SOURCE_ID = 'harpercollins'`, `SCHEMA_VERSION = 'hc-observer-v1'`, `MAX_COLLECTION_PAGES = 10`, a strict product URL allowlist for HTTPS `www.harpercollins.com/products/`, and versioned Crawl4AI candidate schemas named `COLLECTION_CSS_SCHEMA` and `COLLECTION_XPATH_SCHEMA`. Both schemas extract only product title and canonical link from a collection hit. They are data constants for #125, not executed in this ticket.

Implement `parse_atom_candidates(path)` with `xml.etree.ElementTree`: accept only alternate links on the allowed host/path, preserve first-seen order, remove duplicates, and return candidates plus evidence containing the SHA-256 of the fixture bytes. Do not map Atom `published` or `updated` into a publication date.

Implement `is_valid_isbn13(value)` with the standard alternating 1/3 checksum. Implement `parse_product_document(path)` with `json.loads()`: derive the canonical product URL from the handle, parse an author only from the strict `Title by Author (ISBN)` image-alt pattern, retain valid variant SKU/barcode values once, sort editions by the fixed print/electronic rank, and set exactly one main print edition when available. Ignore Shopify timestamps for publication date. Evidence is `VALID` only when title, author, at least one valid ISBN, and a real publication date exist; otherwise use `VALIDATION_FAILED` and list missing fields.

Implement collection comparison by loading the CSS and XPath output arrays referenced by the manifest. Normalize and allowlist URLs, de-duplicate them, compare the two ordered URL sets, and emit parity evidence. Use a page signature made from the normalized product URLs to stop repeated pages. Stop at empty pages and `MAX_COLLECTION_PAGES`; emit `EMPTY`, `DUPLICATE_PAGE`, or `PAGE_LIMIT_REACHED` evidence rather than silently succeeding. Treat zero matches or CSS/XPath disagreement as `EXTRACTION_FAILED` with `TEMPLATE_DRIFT`.

Implement `FixedTemplateFallback.from_path(path)` and `propose(reason)`; it increments `call_count` and returns only `TemplateCandidate` values from the fixed fixture. `observe_fixture_manifest()` owns the one-call budget: it may call `propose()` once after the first `TEMPLATE_DRIFT`, never for `ACCESS_BLOCKED`, and never turns candidates into rules or book records.

The report records all input digests and compact errors, but not fixture bodies. Reject a non-HarperCollins source immediately. Stable-sort all output through `ObservationReport.to_dict()`.

- [ ] **Step 4: Run behavior tests**

Run:

```powershell
python -m pytest tests/test_harpercollins_observation_config.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 5: Write the prototype decision report**

Create `research/issue-120-harpercollins-observation-prototype.md` with:

- Scope and explicit no-write/no-Hachette boundary.
- A table comparing Atom, product JSON, CSS, XPath, dynamic pagination, drift detection, and fixed AI fallback.
- Decision: Atom for candidate discovery, product JSON for deterministic editions, CSS primary for collection hits, XPath as parity oracle, AI candidate generation only after drift and never automatic rule mutation.
- Known gaps: author may be absent, true publication date remains unavailable, collection coverage is unproven, production use remains blocked by #124.
- A mapping from every #120 question to a fixture/test and its observed status.
- Recommendation that #125 execute the versioned schemas through one Crawl4AI 0.9.2 crawler using raw fixture input; no live crawl is authorized by this prototype.

- [ ] **Step 6: Run quality gates**

Run:

```powershell
ruff check app/services/publisher_observer tests/test_harpercollins_observation_config.py
mypy app/services/publisher_observer
python -m pytest tests/test_harpercollins_observation_config.py -q --no-cov
python -m pytest tests/ -q
```

Expected: all commands PASS; full suite remains at or above the configured coverage threshold.

- [ ] **Step 7: Commit Task 2**

```powershell
git add app/services/publisher_observer tests/test_harpercollins_observation_config.py research/issue-120-harpercollins-observation-prototype.md
git commit -m "feat(observer): prototype HarperCollins extraction config"
```

## Final verification

- [ ] `git diff origin/main...HEAD -- app/services/publisher_crawler app/services/publisher_data.py app/services/new_book update_books.py static/data` is empty.
- [ ] `rg -n "hachette|sqlalchemy|flask|db\.session|CRON_SECRET|ZHIPU_API_KEY" app/services/publisher_observer tests/test_harpercollins_observation_config.py` returns only the intentional test asserting that `hachette` is rejected; no imports or secret handling are present.
- [ ] `git status --short` is clean after the two commits.
- [ ] #120 remains a prototype for human review. Do not start #125, change production source mapping, or perform a live crawl in this branch.
