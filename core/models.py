"""Domain-independent Pydantic models for EIP (Contract v0.1 compatible, extended for v0.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from core.spatial import (
    GeoJSONGeometry,
    LineStringGeometry,
    PointGeometry,
    PolygonOrMultiPolygonGeometry,
)

CONTRACT_VERSION = "0.1"
CONTRACT_V02_VERSION = "0.2"

AuthenticationStatus = Literal["unknown", "verified", "failed"]
AssessmentMode = Literal["retrospective", "decision_time"]
IndependenceStatus = Literal[
    "single_source",
    "shared_dependencies_detected",
    "distinct_declared_sources",
    "unknown",
]


def _validate_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "Timestamp must be timezone-aware ISO 8601 (UTC 'Z' or explicit offset)."
        )
    return value.astimezone(timezone.utc)


def _serialize_utc(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.isoformat().replace("+00:00", "Z")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


AwareUtcDatetime = Annotated[
    datetime,
    AfterValidator(_validate_utc_aware),
    PlainSerializer(_serialize_utc, return_type=str),
]


class SourceProvenance(BaseModel):
    """Structured source lineage and upstream dependency metadata."""

    model_config = ConfigDict(extra="forbid")

    original_source: str | None = None
    publishing_organisation: str | None = None
    upstream_datasets: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    measurement_method: str | None = None
    shared_dependencies: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """Generic evidence record supporting spatial and non-spatial domains."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    product_id: str | None = None
    source_url: str | None = None
    observed_at: AwareUtcDatetime | None = None
    available_at: AwareUtcDatetime | None = None
    retrieved_at: AwareUtcDatetime | None = None
    kind: str = Field(min_length=1)
    geometry: GeoJSONGeometry | None = None
    coverage: PolygonOrMultiPolygonGeometry | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: SourceProvenance | None = None
    authentication: AuthenticationStatus = "unknown"
    sha256: str | None = None
    raw_path: str | None = None
    licence: str | None = None
    limitations: list[str] = Field(default_factory=list)
    synthetic: bool

    @field_validator("raw_path")
    @classmethod
    def validate_raw_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme:
            raise ValueError("raw_path must be a local relative path, not a URL.")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("raw_path must be a safe local relative path without '..'.")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if len(cleaned) != 64 or any(ch not in "0123456789abcdef" for ch in cleaned):
            raise ValueError("sha256 must be a 64-character lowercase hex digest.")
        return cleaned


class ClaimRequest(BaseModel):
    """Generic structured claim dispatched to a registered assessment policy."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    geometry: GeoJSONGeometry | None = None
    claimed_at: AwareUtcDatetime
    source_label: str = Field(min_length=1)
    synthetic: bool
    attributes: dict[str, Any] = Field(default_factory=dict)
    assessment_mode: AssessmentMode = "retrospective"
    decision_time: AwareUtcDatetime | None = None
    assessed_at: AwareUtcDatetime | None = None
    policy_id: str | None = None

    @model_validator(mode="after")
    def validate_temporal_mode(self) -> ClaimRequest:
        if self.assessment_mode == "decision_time" and self.decision_time is None:
            raise ValueError(
                "decision_time is required when assessment_mode is 'decision_time'."
            )
        return self


class EvidenceFinding(BaseModel):
    """Per-evidence assessment finding (v0.1 compatible field set)."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    status: str
    age_hours: float | None
    reasons: list[str]


class IndependenceSummary(BaseModel):
    """Summary of source independence and detected shared upstream dependencies."""

    model_config = ConfigDict(extra="forbid")

    status: IndependenceStatus
    assessed_source_count: int
    independent_group_count: int | None
    correlated_groups: list[list[str]] = Field(default_factory=list)
    shared_dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TemporalContext(BaseModel):
    """Explicit temporal context distinguishing claim, decision, assessment, and availability."""

    model_config = ConfigDict(extra="forbid")

    assessment_mode: AssessmentMode
    claimed_at: AwareUtcDatetime
    decision_time: AwareUtcDatetime | None = None
    assessed_at: AwareUtcDatetime | None = None
    excluded_not_available_ids: list[str] = Field(default_factory=list)
    unknown_availability_ids: list[str] = Field(default_factory=list)


class AssessmentTraceability(BaseModel):
    """Deterministic traceability record for audit and replay."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    policy_version: str
    input_fingerprint: str
    assessed_at: AwareUtcDatetime | None = None


class AssessmentResponse(BaseModel):
    """Assessment response preserving v0.1 fields and adding v0.2 metadata."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: str
    policy_version: str
    reasons: list[str]
    evidence_ids: list[str]
    findings: list[EvidenceFinding]
    limitations: list[str]
    synthetic: bool
    assessment_mode: AssessmentMode = "retrospective"
    temporal_context: TemporalContext | None = None
    independence: IndependenceSummary | None = None
    traceability: AssessmentTraceability | None = None


class PolicySpec(BaseModel):
    """Declarative metadata describing a registered assessment policy."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    supported_claim_types: list[str] = Field(min_length=1)
    required_evidence_kinds: list[str] = Field(default_factory=list)
    optional_evidence_kinds: list[str] = Field(default_factory=list)
    evidence_relevance_criteria: list[str] = Field(default_factory=list)
    assessment_rules_summary: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    possible_outcomes: list[str] = Field(min_length=1)
    reason_explanations: dict[str, str] = Field(default_factory=dict)
    known_limitations: list[str] = Field(default_factory=list)


class PolicyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_V02_VERSION
    policies: list[PolicySpec]


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_V02_VERSION
    compatible_contract_versions: list[str] = Field(
        default_factory=lambda: [CONTRACT_VERSION, CONTRACT_V02_VERSION]
    )
    supported_claim_types: list[str]
    supported_evidence_kinds: list[str]
    registered_policy_ids: list[str]
    assessment_modes: list[AssessmentMode] = Field(
        default_factory=lambda: ["retrospective", "decision_time"]
    )


class EvidenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Evidence]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    contract_version: str = CONTRACT_VERSION


__all__ = [
    "CONTRACT_VERSION",
    "CONTRACT_V02_VERSION",
    "AssessmentMode",
    "AssessmentResponse",
    "AssessmentTraceability",
    "AuthenticationStatus",
    "AwareUtcDatetime",
    "CapabilitiesResponse",
    "ClaimRequest",
    "Evidence",
    "EvidenceFinding",
    "EvidenceListResponse",
    "GeoJSONGeometry",
    "HealthResponse",
    "IndependenceStatus",
    "IndependenceSummary",
    "LineStringGeometry",
    "PointGeometry",
    "PolicyListResponse",
    "PolicySpec",
    "PolygonOrMultiPolygonGeometry",
    "SourceProvenance",
    "TemporalContext",
]
