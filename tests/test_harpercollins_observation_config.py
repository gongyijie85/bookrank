"""Contract coverage for the HarperCollins observation prototype."""

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


def test_observation_report_serializes_a_safe_deterministic_payload() -> None:
    edition = EditionObservation(
        format="Hardcover", isbn13="9780063416178", is_main=True
    )
    book = BookObservation(
        title="Whistler",
        author="Ann Patchett",
        source_url="https://www.harpercollins.com/products/whistler-ann-patchett",
        editions=(edition,),
        publication_date=None,
        missing_fields=("publication_date",),
    )
    evidence = ExtractionEvidence(
        document_id="product-whistler",
        source_url=book.source_url,
        method=ExtractionMethod.PRODUCT_JSON,
        status=EvidenceStatus.VALIDATION_FAILED,
        matched_count=1,
        input_sha256="a" * 64,
        error_code="MISSING_REQUIRED_FIELDS",
        detail="publication_date",
    )
    report = ObservationReport(
        source="harpercollins",
        schema_version="hc-observer-v1",
        records=(book,),
        evidence=(evidence,),
        candidate_urls=(book.source_url,),
        unverified_ai_candidates=(),
        ai_fallback_calls=0,
    )

    payload = report.to_dict()

    assert payload["empty_result"] is False
    assert payload["write_enabled"] is False
    assert payload["records"][0]["editions"][0]["isbn13"] == "9780063416178"
    assert payload["evidence"][0]["method"] == "product_json"
    assert payload["evidence"][0]["status"] == "validation_failed"
    assert "raw_html" not in str(payload)
    assert "content" not in str(payload)


def test_observation_report_serializes_tuples_in_stable_order() -> None:
    first = BookObservation(
        title="Alpha",
        author="A Author",
        source_url="https://example.test/products/a",
        editions=(),
        publication_date=None,
        missing_fields=(),
    )
    second = BookObservation(
        title="Beta",
        author="B Author",
        source_url="https://example.test/products/b",
        editions=(),
        publication_date=None,
        missing_fields=(),
    )
    report = ObservationReport(
        source="harpercollins",
        schema_version="hc-observer-v1",
        records=(second, first),
        evidence=(
            ExtractionEvidence(
                document_id="z-document",
                source_url=second.source_url,
                method=ExtractionMethod.XPATH,
                status=EvidenceStatus.VALID,
                matched_count=1,
                input_sha256="b" * 64,
                error_code=None,
                detail=None,
            ),
            ExtractionEvidence(
                document_id="a-document",
                source_url=first.source_url,
                method=ExtractionMethod.CSS,
                status=EvidenceStatus.VALID,
                matched_count=1,
                input_sha256="c" * 64,
                error_code=None,
                detail=None,
            ),
        ),
        candidate_urls=(second.source_url, first.source_url),
        unverified_ai_candidates=(
            TemplateCandidate("xpath", "//main", "fallback"),
            TemplateCandidate("css", ".product", "fallback"),
        ),
        ai_fallback_calls=2,
    )

    payload = report.to_dict()

    assert [item["title"] for item in payload["records"]] == ["Alpha", "Beta"]
    assert [item["document_id"] for item in payload["evidence"]] == [
        "a-document",
        "z-document",
    ]
    assert payload["candidate_urls"] == [first.source_url, second.source_url]
    assert [item["selector_kind"] for item in payload["unverified_ai_candidates"]] == [
        "css",
        "xpath",
    ]


def test_observation_report_cannot_enable_writes() -> None:
    with pytest.raises(TypeError, match="write_enabled"):
        ObservationReport(
            source="harpercollins",
            schema_version="hc-observer-v1",
            records=(),
            evidence=(),
            candidate_urls=(),
            unverified_ai_candidates=(),
            ai_fallback_calls=0,
            write_enabled=True,
        )
