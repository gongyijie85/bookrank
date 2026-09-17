# HarperCollins observation prototype — issue #120

## Scope and safety boundary

This prototype answers issue #120 with deterministic, local fixtures only. It observes HarperCollins discovery and product representations and produces immutable, serialization-safe records and evidence. It does not crawl the live site, import Crawl4AI, open a browser, read credentials, connect to a database, mutate extraction rules, call a write endpoint, or invoke the current publisher sync path. `ObservationReport.write_enabled` is permanently `false`.

The source boundary is explicit: only a manifest whose source is exactly `harpercollins` is accepted, and this check occurs before any listed document is read. Hachette and every other publisher are out of scope; this work provides no Hachette automation or reusable live-crawl registration.

## Method comparison

| Method | Prototype role | Deterministic observation | Result / boundary |
| --- | --- | --- | --- |
| Atom | Discovery | Parses alternate links, HTTPS-allowlists only `www.harpercollins.com/products/`, preserves first-seen order, and deduplicates | Useful for candidate URLs; Atom `published` and `updated` timestamps are discovery metadata, never book publication dates |
| Product JSON | Book and edition observation | Builds the canonical product URL from the handle; extracts author only from strict `Title by Author (ISBN)` image alt text; checksum-validates and ranks editions | Best deterministic edition source in the fixtures; Shopify timestamps are not accepted as publication dates |
| CSS | Primary collection candidate for #125 | Compares captured output from a deeply immutable, JSON-serializable Crawl4AI 0.9.x schema using `baseSelector` and per-field `selector` keys | Valid when its ordered normalized product URLs agree with XPath |
| XPath | Parity oracle | Independently compares captured output from an equivalently shaped immutable Crawl4AI 0.9.x XPath schema | Validates CSS output; it is not a second production rule |
| Dynamic pagination | Coverage and stopping behavior | Includes page 2; stops on an empty page, a repeated normalized URL signature, or before page 11 | Every stop emits explicit `EMPTY`, `DUPLICATE_PAGE`, or `PAGE_LIMIT_REACHED` evidence |
| Drift handling | Failure visibility | Zero matches or CSS/XPath disagreement emit `EXTRACTION_FAILED` evidence with `TEMPLATE_DRIFT` | Drift remains visible and never becomes a successful observation |
| Fixed AI candidate | Post-drift proposal only | Uses one fixed fixture and a one-call budget for the entire manifest; the caller object must match the manifest-owned path, digest, document name, and candidate content | Candidate must remain `verified=false`; provenance mismatch and pre-verified input fail closed; it never becomes a selector, rule, or book automatically; `ACCESS_BLOCKED` never triggers it |

## Decision

Use Atom for discovery and product JSON for deterministic edition observations. Treat the versioned CSS schema as the primary collection extraction candidate and the versioned XPath schema as its parity oracle. Consider an AI selector candidate only after explicit template drift, with one call total per observation. AI output must remain unverified evidence for manual review and must never mutate rules or produce books automatically.

This decision deliberately prefers explicit partial records over invented values. A missing author remains `null`; an unavailable publication date remains `null`; missing fields are listed on the record; and an empty manifest produces `EvidenceStatus.EMPTY` rather than success.

## Issue #120 question-to-evidence map

| #120 question | Fixture and behavior test | Observed status |
| --- | --- | --- |
| Can Atom provide safe product discovery without duplicates? | `new-releases.atom`; `test_atom_candidates_are_deduplicated_and_timestamps_are_discovery_only` | Yes for allowlisted product candidates; timestamps are excluded from publication data |
| Can the product document provide deterministic title, author, and editions? | `product-whistler.json`; `test_parse_product_document_preserves_only_observed_whistler_fields` | Title, strict-alt author, and two checksum-valid editions observed deterministically |
| Which edition should be main, and can invalid ISBNs be rejected? | Temporary product fixture; `test_isbn_checksum_and_format_priority_choose_one_print_main` | Hardcover, Trade Paperback/Paperback, then Large Print rank ahead of electronic/audio; exactly one print main; invalid checksum rejected |
| Are missing required values explicit rather than fabricated? | `product-missing-author.json`; `test_missing_author_and_date_are_not_invented` | Author and publication date remain missing; no placeholder author or Shopify-derived date |
| Do CSS and XPath agree on the captured collection? | `collection-page-1-*.json`, `collection-page-2-*.json`; `test_collection_css_xpath_parity_includes_second_page` | Ordered normalized URL parity is valid on both captured pages |
| Is CSS/XPath disagreement detected? | Temporary unequal CSS/XPath outputs; `test_collection_css_xpath_disagreement_is_template_drift` | Explicit `EXTRACTION_FAILED` / `TEMPLATE_DRIFT` |
| Is dynamic page 2 included, and are pagination loops bounded? | Page 2 fixtures plus generated pagination fixtures; `test_collection_pagination_stops_explicitly` | Page 2 included; empty, duplicate signature, and ten-page ceiling each stop explicitly |
| What happens when templates return zero matches? | `collection-drift-css.json`, `collection-drift-xpath.json`; manifest fallback test | Zero matches remain drift failures and do not masquerade as success |
| Can fallback usage be bounded across multiple drift pages? | `fixed-ai-candidate.json`; `test_multiple_drift_pages_consume_one_fallback_call` | Exactly one proposal call total, candidate unverified |
| Does access blocking invoke fallback? | Generated blocked manifest; `test_access_blocked_never_calls_fallback` | No; `ACCESS_BLOCKED` is recorded and fallback calls remain zero |
| Is publisher scope rejected before document access? | Generated manifests naming Hachette and other sources; `test_non_harper_source_is_rejected_before_documents_are_read` | Non-HarperCollins sources raise `ValueError` before listed paths are resolved or read |
| Are empty results, malformed rows, digests, serialization, and no-write behavior auditable? | `manifest.json` and generated malformed/empty manifests; deterministic/safety, malformed-product/collection, empty-manifest, fallback-provenance, and symlink-boundary tests | SHA-256 input evidence, explicit malformed/empty evidence, manifest-bound fallback provenance, resolved-path containment with symlink rejection, stable `to_dict`, no fixture bodies/secrets/import paths/database paths, and writes disabled |

## Known gaps

- Author data can be absent because the prototype accepts only the strict image-alt representation.
- A true book publication date is unavailable in the captured product JSON; Shopify catalog timestamps are insufficient evidence.
- The captured fixtures do not prove catalog-wide selector or pagination coverage.
- Production execution is blocked by issue #124 and remains outside this prototype.

## Recommendation for #125

Execute these versioned, runtime-immutable CSS and XPath schemas directly through one Crawl4AI 0.9.2 crawler using raw fixture input, with CSS as the primary result and XPath as the parity oracle. Preserve the canonical manifest URL preflight, manifest SHA-256, per-input digests, duplicate-member/source rejection, drift, pagination, and one-call unverified-candidate controls. No live crawl is authorized by #120 or this recommendation.
