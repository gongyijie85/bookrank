"""Immutable, serialization-safe contracts for publisher observations."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ExtractionMethod(StrEnum):
    MANIFEST = "manifest"
    ATOM = "atom"
    PRODUCT_JSON = "product_json"
    CSS = "css"
    XPATH = "xpath"
    AI_CANDIDATE = "ai_candidate"


class EvidenceStatus(StrEnum):
    VALID = "valid"
    EXTRACTION_FAILED = "extraction_failed"
    VALIDATION_FAILED = "validation_failed"
    ACCESS_BLOCKED = "access_blocked"
    EMPTY = "empty"


@dataclass(frozen=True)
class EditionObservation:
    format: str
    isbn13: str
    is_main: bool


@dataclass(frozen=True)
class BookObservation:
    title: str
    author: str | None
    source_url: str
    editions: tuple[EditionObservation, ...]
    publication_date: str | None
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionEvidence:
    document_id: str
    source_url: str
    method: ExtractionMethod
    status: EvidenceStatus
    matched_count: int
    input_sha256: str
    error_code: str | None
    detail: str | None


@dataclass(frozen=True)
class TemplateCandidate:
    selector_kind: str
    selector: str
    reason: str
    verified: bool = False


@dataclass(frozen=True)
class ObservationReport:
    source: str
    schema_version: str
    records: tuple[BookObservation, ...]
    evidence: tuple[ExtractionEvidence, ...]
    candidate_urls: tuple[str, ...]
    unverified_ai_candidates: tuple[TemplateCandidate, ...]
    ai_fallback_calls: int
    manifest_sha256: str | None = None
    write_enabled: bool = field(default=False, init=False)

    @property
    def empty_result(self) -> bool:
        return not self.records

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "schema_version": self.schema_version,
            "manifest_sha256": self.manifest_sha256,
            "records": [
                _serialize(record)
                for record in sorted(self.records, key=lambda item: (item.source_url, item.title))
            ],
            "evidence": [
                _serialize(item)
                for item in sorted(
                    self.evidence, key=lambda item: (item.document_id, item.method.value)
                )
            ],
            "candidate_urls": sorted(self.candidate_urls),
            "unverified_ai_candidates": [
                _serialize(item)
                for item in sorted(
                    self.unverified_ai_candidates,
                    key=lambda item: (item.selector_kind, item.selector),
                )
            ],
            "ai_fallback_calls": self.ai_fallback_calls,
            "write_enabled": self.write_enabled,
            "empty_result": self.empty_result,
        }


def _serialize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    return value
