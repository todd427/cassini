"""Domain-independent evidence graph builder derived strictly from API assessment data.

Constructs a structured node-and-edge graph representing:
- Claim under evaluation
- Individual evidence records (with authentication, freshness, independence group, role)
- Original observation sources (only when declared in provenance)
- Publishing organisations (only when declared in provenance)
- Shared upstream datasets & dependencies (only when declared in provenance)
- Missing evidence (explicitly represented when no relevant evidence was available)

Never invents relationships or metadata absent from actual provenance/assessment inputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import AssessmentResponse, ClaimRequest, Evidence

NodeType = Literal[
    "claim",
    "evidence",
    "original_source",
    "publisher",
    "upstream_dependency",
    "missing_evidence",
]

EvidenceRelationRole = Literal[
    "potentially_contradicting",
    "supporting",
    "contextual",
    "failed_authentication",
    "unsuitable",
    "inconclusive",
]

FreshnessState = Literal[
    "fresh",
    "stale",
    "time_unknown",
    "not_available_at_decision",
    "availability_unknown",
]


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    node_type: NodeType
    label: str
    subtitle: str | None = None
    status: str | None = None
    relation_role: EvidenceRelationRole | None = None
    authentication: str | None = None
    freshness: FreshnessState | None = None
    independence_group: int | None = None
    synthetic: bool = False
    observed_at: str | None = None
    available_at: str | None = None
    retrieved_at: str | None = None
    age_hours: float | None = None
    reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    relation: str
    label: str
    shared: bool = False


class EvidenceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    independence_status: str
    independent_group_count: int | None = None
    assessed_source_count: int = 0


class AssessmentGraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: AssessmentResponse
    evidence: list[Evidence]
    graph: EvidenceGraph


def _slug(prefix: str, value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return f"{prefix}:{cleaned.strip('-') or 'unnamed'}"


def _classify_relation(finding_status: str, reasons: Sequence[str]) -> tuple[EvidenceRelationRole, str, str]:
    if "AUTHENTICATION_FAILED" in reasons or finding_status == "authentication_failed":
        return ("failed_authentication", "failed_authentication", "Failed auth")
    if finding_status == "evidence_unsuitable":
        return ("unsuitable", "unsuitable_for_claim", "Unsuitable")
    if finding_status == "potential_conflict":
        return ("potentially_contradicting", "potentially_contradicts", "Potential conflict")
    if finding_status in ("authenticated", "no_mapped_overlap", "within_limits"):
        return ("supporting", "supports_or_consistent", "Consistent / Verified")
    if finding_status in ("contextual_support", "contextual_neutral"):
        return ("contextual", "contextual_evidence", "Contextual (indirect)")
    return ("inconclusive", "inconclusive_for_claim", "Inconclusive")


def _classify_freshness(reasons: Sequence[str]) -> FreshnessState:
    if "NOT_AVAILABLE_AT_DECISION_TIME" in reasons:
        return "not_available_at_decision"
    if "AVAILABILITY_TIME_UNKNOWN" in reasons:
        return "availability_unknown"
    if "OBSERVATION_STALE" in reasons:
        return "stale"
    if "OBSERVATION_TIME_UNKNOWN" in reasons:
        return "time_unknown"
    return "fresh"


def build_evidence_graph(
    claim: ClaimRequest,
    evidence_items: Sequence[Evidence],
    assessment: AssessmentResponse,
) -> EvidenceGraph:
    """Build a deterministic, domain-independent evidence graph from actual assessment data."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()

    def add_node(node: GraphNode) -> None:
        if node.id not in seen_nodes:
            seen_nodes.add(node.id)
            nodes.append(node)

    def add_edge(edge: GraphEdge) -> None:
        if edge.id not in seen_edges:
            seen_edges.add(edge.id)
            edges.append(edge)

    claim_node_id = f"claim:{claim.claim_id}"
    claim_dump = claim.model_dump(mode="json")
    add_node(
        GraphNode(
            id=claim_node_id,
            node_type="claim",
            label=claim.source_label,
            subtitle=f"{claim.claim_type} · {assessment.policy_version}",
            status=assessment.status,
            synthetic=claim.synthetic,
            observed_at=claim_dump["claimed_at"],
            reasons=list(assessment.reasons),
            limitations=list(assessment.limitations),
            metadata={
                "claim_id": claim.claim_id,
                "claim_type": claim.claim_type,
                "assessment_mode": assessment.assessment_mode,
                "decision_time": (
                    assessment.temporal_context.model_dump(mode="json")["decision_time"]
                    if assessment.temporal_context
                    else None
                ),
                "policy_version": assessment.policy_version,
                "policy_id": (
                    assessment.traceability.policy_id if assessment.traceability else None
                ),
            },
        )
    )

    ev_by_id = {ev.id: ev for ev in evidence_items}
    finding_by_id = {f.evidence_id: f for f in assessment.findings}

    # Map evidence_id -> 1-based independence group index from assessment.independence
    group_by_ev: dict[str, int] = {}
    if assessment.independence:
        for grp_idx, grp in enumerate(assessment.independence.correlated_groups, start=1):
            for eid in grp:
                group_by_ev[eid] = grp_idx

    if not assessment.evidence_ids:
        missing_id = "missing:no-evidence"
        add_node(
            GraphNode(
                id=missing_id,
                node_type="missing_evidence",
                label="No qualifying evidence available",
                subtitle="NO_EVIDENCE",
                status="insufficient_evidence",
                relation_role="inconclusive",
                reasons=["NO_EVIDENCE"],
                limitations=[
                    "No relevant evidence records were loaded or available for this claim."
                ],
            )
        )
        add_edge(
            GraphEdge(
                id=f"edge:{missing_id}->{claim_node_id}",
                source=missing_id,
                target=claim_node_id,
                relation="missing_evidence",
                label="No evidence",
            )
        )
        return EvidenceGraph(
            nodes=nodes,
            edges=edges,
            independence_status=(
                assessment.independence.status if assessment.independence else "unknown"
            ),
            independent_group_count=(
                assessment.independence.independent_group_count
                if assessment.independence
                else 0
            ),
            assessed_source_count=0,
        )

    # Track reference counts so shared upstream/original sources are highlighted accurately
    upstream_consumers: dict[str, set[str]] = {}
    orig_consumers: dict[str, set[str]] = {}

    assessed_evidence: list[Evidence] = [
        ev_by_id[eid] for eid in assessment.evidence_ids if eid in ev_by_id
    ]
    for ev in assessed_evidence:
        if ev.provenance:
            if ev.provenance.original_source:
                k = _slug("orig", ev.provenance.original_source)
                orig_consumers.setdefault(k, set()).add(ev.id)
            for ds in ev.provenance.upstream_datasets:
                k = _slug("upstream", ds)
                upstream_consumers.setdefault(k, set()).add(ev.id)
            for dep in ev.provenance.shared_dependencies:
                k = _slug("dep", dep)
                upstream_consumers.setdefault(k, set()).add(ev.id)

    for ev in assessed_evidence:
        ev_node_id = f"evidence:{ev.id}"
        finding = finding_by_id.get(ev.id)
        f_status = finding.status if finding else "insufficient_evidence"
        f_reasons = list(finding.reasons) if finding else []
        f_age = finding.age_hours if finding else None
        rel_role, edge_rel, edge_label = _classify_relation(f_status, f_reasons)
        freshness = _classify_freshness(f_reasons)
        ev_dump = ev.model_dump(mode="json")

        add_node(
            GraphNode(
                id=ev_node_id,
                node_type="evidence",
                label=ev.product_id or ev.id,
                subtitle=f"{ev.kind} · {ev.source}",
                status=f_status,
                relation_role=rel_role,
                authentication=ev.authentication,
                freshness=freshness,
                independence_group=group_by_ev.get(ev.id),
                synthetic=ev.synthetic,
                observed_at=ev_dump["observed_at"],
                available_at=ev_dump["available_at"],
                retrieved_at=ev_dump["retrieved_at"],
                age_hours=f_age,
                reasons=f_reasons,
                limitations=list(ev.limitations),
                metadata={
                    "evidence_id": ev.id,
                    "source": ev.source,
                    "kind": ev.kind,
                    "product_id": ev.product_id,
                    "source_url": ev.source_url,
                    "raw_path": ev.raw_path,
                    "sha256": ev.sha256,
                    "licence": ev.licence,
                    "attributes": ev.attributes,
                    "provenance": ev_dump["provenance"],
                },
            )
        )

        add_edge(
            GraphEdge(
                id=f"edge:{ev_node_id}->{claim_node_id}",
                source=ev_node_id,
                target=claim_node_id,
                relation=edge_rel,
                label=edge_label,
            )
        )

        # Provenance & upstream nodes — created strictly from declared provenance
        prov = ev.provenance
        if prov:
            if prov.original_source:
                orig_id = _slug("orig", prov.original_source)
                is_shared = len(orig_consumers.get(orig_id, set())) > 1
                add_node(
                    GraphNode(
                        id=orig_id,
                        node_type="original_source",
                        label=prov.original_source,
                        subtitle=prov.measurement_method or "Original observation source",
                        status="shared" if is_shared else "distinct",
                        metadata={
                            "measurement_method": prov.measurement_method,
                            "shared_across_evidence": is_shared,
                        },
                    )
                )
                add_edge(
                    GraphEdge(
                        id=f"edge:{orig_id}->{ev_node_id}",
                        source=orig_id,
                        target=ev_node_id,
                        relation="observed_by",
                        label="Shared source" if is_shared else "Observed by",
                        shared=is_shared,
                    )
                )

            if prov.publishing_organisation:
                pub_id = _slug("pub", prov.publishing_organisation)
                add_node(
                    GraphNode(
                        id=pub_id,
                        node_type="publisher",
                        label=prov.publishing_organisation,
                        subtitle="Publishing organisation",
                    )
                )
                add_edge(
                    GraphEdge(
                        id=f"edge:{pub_id}->{ev_node_id}",
                        source=pub_id,
                        target=ev_node_id,
                        relation="published_by",
                        label="Published by",
                    )
                )

            for ds in prov.upstream_datasets:
                up_id = _slug("upstream", ds)
                is_shared = len(upstream_consumers.get(up_id, set())) > 1
                add_node(
                    GraphNode(
                        id=up_id,
                        node_type="upstream_dependency",
                        label=ds,
                        subtitle="Shared upstream dataset" if is_shared else "Upstream dataset",
                        status="shared" if is_shared else "distinct",
                    )
                )
                add_edge(
                    GraphEdge(
                        id=f"edge:{up_id}->{ev_node_id}",
                        source=up_id,
                        target=ev_node_id,
                        relation="upstream_dataset",
                        label="Shared upstream" if is_shared else "Upstream dataset",
                        shared=is_shared,
                    )
                )

            for dep in prov.shared_dependencies:
                dep_id = _slug("dep", dep)
                is_shared = len(upstream_consumers.get(dep_id, set())) > 1
                add_node(
                    GraphNode(
                        id=dep_id,
                        node_type="upstream_dependency",
                        label=dep,
                        subtitle="Declared dependency",
                        status="shared" if is_shared else "declared",
                    )
                )
                add_edge(
                    GraphEdge(
                        id=f"edge:{dep_id}->{ev_node_id}",
                        source=dep_id,
                        target=ev_node_id,
                        relation="shared_dependency",
                        label="Shared dependency" if is_shared else "Depends on",
                        shared=is_shared,
                    )
                )

            for parent_id in prov.derived_from:
                parent_node_id = f"evidence:{parent_id}"
                if parent_id in ev_by_id:
                    add_edge(
                        GraphEdge(
                            id=f"edge:{parent_node_id}->{ev_node_id}:derived",
                            source=parent_node_id,
                            target=ev_node_id,
                            relation="derived_from",
                            label="Derived from",
                            shared=True,
                        )
                    )

    return EvidenceGraph(
        nodes=nodes,
        edges=edges,
        independence_status=(
            assessment.independence.status if assessment.independence else "unknown"
        ),
        independent_group_count=(
            assessment.independence.independent_group_count
            if assessment.independence
            else None
        ),
        assessed_source_count=len(assessed_evidence),
    )
