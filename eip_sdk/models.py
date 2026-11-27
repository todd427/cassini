"""Typed, zero-internal-dependency data models for the EIP Python client SDK.

All models map strictly to the public EIP REST API JSON contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

AssessmentMode = Literal["retrospective", "decision_time"]

NON_ORACLE_DISCLAIMER = (
    "EIP is an independent evidence-consistency and cryptographic navigation-message "
    "verification tool, not a truth oracle, operational safety certification, positioning "
    "accuracy guarantee, or automated final decision-maker."
)


@dataclass(frozen=True)
class HealthStatus:
    """Response from GET /health."""

    status: str
    contract_version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealthStatus:
        return cls(
            status=str(data.get("status", "unknown")),
            contract_version=str(data.get("contract_version", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "contract_version": self.contract_version}


@dataclass(frozen=True)
class Capabilities:
    """Response from GET /v1/capabilities."""

    contract_version: str
    supported_claim_types: list[str]
    supported_evidence_kinds: list[str]
    registered_policy_ids: list[str]
    assessment_modes: list[str]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Capabilities:
        return cls(
            contract_version=str(data.get("contract_version", "")),
            supported_claim_types=list(data.get("supported_claim_types", [])),
            supported_evidence_kinds=list(data.get("supported_evidence_kinds", [])),
            registered_policy_ids=list(data.get("registered_policy_ids", [])),
            assessment_modes=list(
                data.get("assessment_modes", ["retrospective", "decision_time"])
            ),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "supported_claim_types": list(self.supported_claim_types),
            "supported_evidence_kinds": list(self.supported_evidence_kinds),
            "registered_policy_ids": list(self.registered_policy_ids),
            "assessment_modes": list(self.assessment_modes),
        }


@dataclass(frozen=True)
class PolicySummary:
    """Policy specification returned by GET /v1/policies."""

    policy_id: str
    policy_version: str
    name: str
    description: str
    supported_claim_types: list[str]
    required_evidence_kinds: list[str]
    optional_evidence_kinds: list[str]
    thresholds: dict[str, Any]
    possible_outcomes: list[str]
    reason_explanations: dict[str, str]
    known_limitations: list[str]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicySummary:
        return cls(
            policy_id=str(data["policy_id"]),
            policy_version=str(data["policy_version"]),
            name=str(data.get("name", data["policy_id"])),
            description=str(data.get("description", "")),
            supported_claim_types=list(data.get("supported_claim_types", [])),
            required_evidence_kinds=list(data.get("required_evidence_kinds", [])),
            optional_evidence_kinds=list(data.get("optional_evidence_kinds", [])),
            thresholds=dict(data.get("thresholds", {})),
            possible_outcomes=list(data.get("possible_outcomes", [])),
            reason_explanations=dict(data.get("reason_explanations", {})),
            known_limitations=list(data.get("known_limitations", [])),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class EvidenceRecord:
    """Normalised evidence item returned by GET /v1/evidence or POST /v1/assess/graph."""

    id: str
    source: str
    kind: str
    product_id: str | None
    source_url: str | None
    observed_at: str | None
    available_at: str | None
    retrieved_at: str | None
    geometry: dict[str, Any] | None
    coverage: dict[str, Any] | None
    attributes: dict[str, Any]
    provenance: dict[str, Any] | None
    authentication: str
    sha256: str | None
    raw_path: str | None
    licence: str | None
    limitations: list[str]
    synthetic: bool
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        return cls(
            id=str(data["id"]),
            source=str(data["source"]),
            kind=str(data["kind"]),
            product_id=data.get("product_id"),
            source_url=data.get("source_url"),
            observed_at=data.get("observed_at"),
            available_at=data.get("available_at"),
            retrieved_at=data.get("retrieved_at"),
            geometry=data.get("geometry"),
            coverage=data.get("coverage"),
            attributes=dict(data.get("attributes") or {}),
            provenance=data.get("provenance"),
            authentication=str(data.get("authentication", "unknown")),
            sha256=data.get("sha256"),
            raw_path=data.get("raw_path"),
            licence=data.get("licence"),
            limitations=list(data.get("limitations") or []),
            synthetic=bool(data.get("synthetic", False)),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)

    def provenance_summary(self) -> dict[str, Any]:
        """Return a compact, auditable provenance summary without bulky polygon coordinates."""
        return {
            "id": self.id,
            "product_id": self.product_id,
            "source": self.source,
            "kind": self.kind,
            "observed_at": self.observed_at,
            "available_at": self.available_at,
            "retrieved_at": self.retrieved_at,
            "authentication": self.authentication,
            "sha256": self.sha256,
            "licence": self.licence,
            "synthetic": self.synthetic,
            "provenance": self.provenance,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class ClaimInput:
    """Structured claim payload for POST /v1/assess and POST /v1/assess/graph."""

    claim_id: str
    claim_type: str
    claimed_at: str
    source_label: str
    synthetic: bool = True
    geometry: dict[str, Any] | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    assessment_mode: AssessmentMode = "retrospective"
    decision_time: str | None = None
    assessed_at: str | None = None
    policy_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "geometry": self.geometry,
            "claimed_at": self.claimed_at,
            "source_label": self.source_label,
            "synthetic": self.synthetic,
            "attributes": dict(self.attributes),
            "assessment_mode": self.assessment_mode,
        }
        if self.decision_time is not None:
            payload["decision_time"] = self.decision_time
        if self.assessed_at is not None:
            payload["assessed_at"] = self.assessed_at
        if self.policy_id is not None:
            payload["policy_id"] = self.policy_id
        return payload

    def with_decision_time(self, decision_time: str) -> ClaimInput:
        """Return a copy of this claim configured for decision-time auditing."""
        return ClaimInput(
            claim_id=self.claim_id,
            claim_type=self.claim_type,
            claimed_at=self.claimed_at,
            source_label=self.source_label,
            synthetic=self.synthetic,
            geometry=self.geometry,
            attributes=dict(self.attributes),
            assessment_mode="decision_time",
            decision_time=decision_time,
            assessed_at=self.assessed_at,
            policy_id=self.policy_id,
        )

    @classmethod
    def road_passable(
        cls,
        *,
        claim_id: str,
        coordinates: list[list[float]],
        claimed_at: str,
        source_label: str,
        synthetic: bool = True,
        assessment_mode: AssessmentMode = "retrospective",
        decision_time: str | None = None,
    ) -> ClaimInput:
        """Construct a WGS84 LineString road passability claim."""
        return cls(
            claim_id=claim_id,
            claim_type="road_passable",
            geometry={"type": "LineString", "coordinates": coordinates},
            claimed_at=claimed_at,
            source_label=source_label,
            synthetic=synthetic,
            assessment_mode=assessment_mode,
            decision_time=decision_time,
        )

    @classmethod
    def galileo_nav_auth(
        cls,
        *,
        claim_id: str,
        claimed_at: str,
        source_label: str,
        svid: int | None = None,
        synthetic: bool = True,
        assessment_mode: AssessmentMode = "retrospective",
        decision_time: str | None = None,
    ) -> ClaimInput:
        """Construct a Galileo OSNMA navigation-message authentication claim."""
        attrs: dict[str, Any] = {}
        if svid is not None:
            attrs["svid"] = svid
        return cls(
            claim_id=claim_id,
            claim_type="gnss_nav_message_authenticated",
            geometry=None,
            claimed_at=claimed_at,
            source_label=source_label,
            synthetic=synthetic,
            attributes=attrs,
            assessment_mode=assessment_mode,
            decision_time=decision_time,
        )

    @classmethod
    def custom(
        cls,
        *,
        claim_id: str,
        claim_type: str,
        claimed_at: str,
        source_label: str,
        attributes: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
        synthetic: bool = True,
        assessment_mode: AssessmentMode = "retrospective",
        decision_time: str | None = None,
        policy_id: str | None = None,
    ) -> ClaimInput:
        """Construct a claim for any custom or newly registered domain policy."""
        return cls(
            claim_id=claim_id,
            claim_type=claim_type,
            geometry=geometry,
            claimed_at=claimed_at,
            source_label=source_label,
            synthetic=synthetic,
            attributes=dict(attributes or {}),
            assessment_mode=assessment_mode,
            decision_time=decision_time,
            policy_id=policy_id,
        )


@dataclass(frozen=True)
class Finding:
    """Per-evidence assessment finding."""

    evidence_id: str
    status: str
    age_hours: float | None
    reasons: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(
            evidence_id=str(data["evidence_id"]),
            status=str(data["status"]),
            age_hours=data.get("age_hours"),
            reasons=list(data.get("reasons") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "status": self.status,
            "age_hours": self.age_hours,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class IndependenceReport:
    """Source independence & shared-dependency summary."""

    status: str
    assessed_source_count: int
    independent_group_count: int | None
    correlated_groups: list[list[str]]
    shared_dependencies: list[str]
    notes: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndependenceReport:
        return cls(
            status=str(data["status"]),
            assessed_source_count=int(data.get("assessed_source_count", 0)),
            independent_group_count=data.get("independent_group_count"),
            correlated_groups=[list(g) for g in data.get("correlated_groups") or []],
            shared_dependencies=list(data.get("shared_dependencies") or []),
            notes=list(data.get("notes") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "assessed_source_count": self.assessed_source_count,
            "independent_group_count": self.independent_group_count,
            "correlated_groups": [list(g) for g in self.correlated_groups],
            "shared_dependencies": list(self.shared_dependencies),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class TemporalContextReport:
    """Temporal evaluation metadata."""

    assessment_mode: str
    claimed_at: str
    decision_time: str | None
    assessed_at: str | None
    excluded_not_available_ids: list[str]
    unknown_availability_ids: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemporalContextReport:
        return cls(
            assessment_mode=str(data.get("assessment_mode", "retrospective")),
            claimed_at=str(data.get("claimed_at", "")),
            decision_time=data.get("decision_time"),
            assessed_at=data.get("assessed_at"),
            excluded_not_available_ids=list(data.get("excluded_not_available_ids") or []),
            unknown_availability_ids=list(data.get("unknown_availability_ids") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_mode": self.assessment_mode,
            "claimed_at": self.claimed_at,
            "decision_time": self.decision_time,
            "assessed_at": self.assessed_at,
            "excluded_not_available_ids": list(self.excluded_not_available_ids),
            "unknown_availability_ids": list(self.unknown_availability_ids),
        }


@dataclass(frozen=True)
class TraceabilityReport:
    """Reproducibility and policy fingerprint metadata."""

    policy_id: str
    policy_version: str
    input_fingerprint: str
    assessed_at: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceabilityReport:
        return cls(
            policy_id=str(data.get("policy_id", "")),
            policy_version=str(data.get("policy_version", "")),
            input_fingerprint=str(data.get("input_fingerprint", "")),
            assessed_at=data.get("assessed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "input_fingerprint": self.input_fingerprint,
            "assessed_at": self.assessed_at,
        }


@dataclass(frozen=True)
class AssessmentResult:
    """Structured outcome from POST /v1/assess."""

    claim_id: str
    status: str
    policy_version: str
    reasons: list[str]
    evidence_ids: list[str]
    findings: list[Finding]
    limitations: list[str]
    synthetic: bool
    assessment_mode: str
    temporal_context: TemporalContextReport | None
    independence: IndependenceReport | None
    traceability: TraceabilityReport | None
    assessed_at_header: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_conflict(self) -> bool:
        return self.status == "potential_conflict"

    @property
    def is_insufficient(self) -> bool:
        return self.status == "insufficient_evidence"

    @property
    def is_authenticated(self) -> bool:
        return self.status == "authenticated"

    @property
    def is_authentication_failed(self) -> bool:
        return self.status == "authentication_failed"

    @property
    def requires_caution(self) -> bool:
        """EIP assessments always include epistemic limitations and require human judgement."""
        return True

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        assessed_at_header: str | None = None,
    ) -> AssessmentResult:
        tc_raw = data.get("temporal_context")
        ind_raw = data.get("independence")
        tr_raw = data.get("traceability")
        return cls(
            claim_id=str(data["claim_id"]),
            status=str(data["status"]),
            policy_version=str(data["policy_version"]),
            reasons=list(data.get("reasons") or []),
            evidence_ids=list(data.get("evidence_ids") or []),
            findings=[Finding.from_dict(f) for f in data.get("findings") or []],
            limitations=list(data.get("limitations") or []),
            synthetic=bool(data.get("synthetic", False)),
            assessment_mode=str(data.get("assessment_mode", "retrospective")),
            temporal_context=TemporalContextReport.from_dict(tc_raw) if tc_raw else None,
            independence=IndependenceReport.from_dict(ind_raw) if ind_raw else None,
            traceability=TraceabilityReport.from_dict(tr_raw) if tr_raw else None,
            assessed_at_header=assessed_at_header,
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class GraphNode:
    """Node in an API-derived EvidenceGraph."""

    id: str
    node_type: str
    label: str
    subtitle: str | None
    status: str | None
    relation_role: str | None
    authentication: str | None
    freshness: str | None
    independence_group: int | None
    synthetic: bool
    observed_at: str | None
    available_at: str | None
    retrieved_at: str | None
    age_hours: float | None
    reasons: list[str]
    limitations: list[str]
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphNode:
        return cls(
            id=str(data["id"]),
            node_type=str(data["node_type"]),
            label=str(data["label"]),
            subtitle=data.get("subtitle"),
            status=data.get("status"),
            relation_role=data.get("relation_role"),
            authentication=data.get("authentication"),
            freshness=data.get("freshness"),
            independence_group=data.get("independence_group"),
            synthetic=bool(data.get("synthetic", False)),
            observed_at=data.get("observed_at"),
            available_at=data.get("available_at"),
            retrieved_at=data.get("retrieved_at"),
            age_hours=data.get("age_hours"),
            reasons=list(data.get("reasons") or []),
            limitations=list(data.get("limitations") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_type": self.node_type,
            "label": self.label,
            "subtitle": self.subtitle,
            "status": self.status,
            "relation_role": self.relation_role,
            "authentication": self.authentication,
            "freshness": self.freshness,
            "independence_group": self.independence_group,
            "synthetic": self.synthetic,
            "observed_at": self.observed_at,
            "available_at": self.available_at,
            "retrieved_at": self.retrieved_at,
            "age_hours": self.age_hours,
            "reasons": list(self.reasons),
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GraphEdge:
    """Directed provenance or assessment edge in an EvidenceGraph."""

    id: str
    source: str
    target: str
    relation: str
    label: str
    shared: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphEdge:
        return cls(
            id=str(data["id"]),
            source=str(data["source"]),
            target=str(data["target"]),
            relation=str(data["relation"]),
            label=str(data["label"]),
            shared=bool(data.get("shared", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "label": self.label,
            "shared": self.shared,
        }


@dataclass(frozen=True)
class EvidenceGraph:
    """Domain-independent provenance and assessment graph returned by POST /v1/assess/graph."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    independence_status: str
    independent_group_count: int | None
    assessed_source_count: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def evidence_nodes(self) -> list[GraphNode]:
        return [n for n in self.nodes if n.node_type == "evidence"]

    def upstream_nodes(self) -> list[GraphNode]:
        return [
            n
            for n in self.nodes
            if n.node_type in {"original_source", "publisher", "upstream_dependency"}
        ]

    def shared_edges(self) -> list[GraphEdge]:
        return [e for e in self.edges if e.shared]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceGraph:
        return cls(
            nodes=[GraphNode.from_dict(n) for n in data.get("nodes") or []],
            edges=[GraphEdge.from_dict(e) for e in data.get("edges") or []],
            independence_status=str(data.get("independence_status", "unknown")),
            independent_group_count=data.get("independent_group_count"),
            assessed_source_count=int(data.get("assessed_source_count", 0)),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class AssessmentGraphResult:
    """Combined assessment, assessed evidence records, and evidence graph."""

    assessment: AssessmentResult
    evidence: list[EvidenceRecord]
    graph: EvidenceGraph
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        assessed_at_header: str | None = None,
    ) -> AssessmentGraphResult:
        return cls(
            assessment=AssessmentResult.from_dict(
                data["assessment"],
                assessed_at_header=assessed_at_header,
            ),
            evidence=[EvidenceRecord.from_dict(ev) for ev in data.get("evidence") or []],
            graph=EvidenceGraph.from_dict(data["graph"]),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class AssessmentReport:
    """Auditable, machine-readable enterprise assessment report exported by the SDK."""

    report_schema_version: str
    generated_at: str
    api_base_url: str
    server_assessed_at: str | None
    claim: dict[str, Any]
    assessment: dict[str, Any]
    evidence_provenance: list[dict[str, Any]]
    graph: dict[str, Any] | None
    disclaimer: str = NON_ORACLE_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_schema_version": self.report_schema_version,
            "generated_at": self.generated_at,
            "api_base_url": self.api_base_url,
            "server_assessed_at": self.server_assessed_at,
            "claim": dict(self.claim),
            "assessment": dict(self.assessment),
            "evidence_provenance": list(self.evidence_provenance),
            "graph": self.graph,
            "disclaimer": self.disclaimer,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def write_json(self, path: str | Path, *, indent: int = 2) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(indent=indent) + "\n", encoding="utf-8")
        return target

    @classmethod
    def from_graph_result(
        cls,
        *,
        api_base_url: str,
        claim_payload: dict[str, Any],
        graph_result: AssessmentGraphResult,
    ) -> AssessmentReport:
        return cls(
            report_schema_version="eip-report-0.6",
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            api_base_url=api_base_url,
            server_assessed_at=graph_result.assessment.assessed_at_header,
            claim=dict(claim_payload),
            assessment=graph_result.assessment.to_dict(),
            evidence_provenance=[ev.provenance_summary() for ev in graph_result.evidence],
            graph=graph_result.graph.to_dict(),
        )

    @classmethod
    def from_assessment_result(
        cls,
        *,
        api_base_url: str,
        claim_payload: dict[str, Any],
        result: AssessmentResult,
        evidence_records: list[EvidenceRecord] | None = None,
    ) -> AssessmentReport:
        ev_by_id = {ev.id: ev for ev in (evidence_records or [])}
        provenance = [
            ev_by_id[eid].provenance_summary()
            for eid in result.evidence_ids
            if eid in ev_by_id
        ]
        return cls(
            report_schema_version="eip-report-0.6",
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            api_base_url=api_base_url,
            server_assessed_at=result.assessed_at_header,
            claim=dict(claim_payload),
            assessment=result.to_dict(),
            evidence_provenance=provenance,
            graph=None,
        )
