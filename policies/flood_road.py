"""Flood-road passability assessment policy (policy_version: flood-road-0.1).

Preserves 100% of EIP v0.1.0 flood-road assessment behaviour while implementing
the domain-independent v0.2 AssessmentPolicy protocol.
"""

from __future__ import annotations

from core.models import (
    ClaimRequest,
    Evidence,
    EvidenceFinding,
    IndependenceSummary,
    PolicySpec,
)
from core.policy import (
    AssessmentContext,
    ClaimValidationError,
    EvidenceContext,
    PolicyDecision,
)
from core.spatial import evaluate_spatial_relation, to_shapely

POLICY_ID = "flood-road"
POLICY_VERSION = "flood-road-0.1"
DEFAULT_MAX_AGE_HOURS = 24.0


class FloodRoadPolicy:
    """Evaluates road passability claims against mapped flood extent polygons."""

    def __init__(self, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> None:
        self._max_age_hours = max_age_hours
        self._spec = PolicySpec(
            policy_id=POLICY_ID,
            policy_version=POLICY_VERSION,
            name="Flood Extent vs Road Passability",
            description=(
                "Evaluates whether mapped flood extent observations overlap a claimed "
                "passable road LineString within a configured temporal window."
            ),
            supported_claim_types=["road_passable"],
            required_evidence_kinds=["flood_extent"],
            optional_evidence_kinds=[],
            evidence_relevance_criteria=[
                "Evidence kind equals 'flood_extent'.",
                "Evidence geometry is a valid WGS84 Polygon or MultiPolygon.",
                "Observation timestamp is within max_age_hours of claimed_at.",
                "In decision_time mode, evidence must be observed and demonstrably available on or before decision_time.",
            ],
            assessment_rules_summary=[
                "Intersecting fresh flood extent -> potential_conflict (FLOOD_EXTENT_INTERSECTS).",
                "Non-intersecting fresh observation whose documented coverage encloses the entire road -> no_mapped_overlap (NO_MAPPED_OVERLAP).",
                "Stale observation, unknown observation time, unknown/partial/outside coverage, failed authentication, or missing availability at decision time -> insufficient_evidence.",
                "Multi-source precedence: potential_conflict > no_mapped_overlap > insufficient_evidence.",
            ],
            thresholds={"max_age_hours": max_age_hours},
            possible_outcomes=[
                "potential_conflict",
                "no_mapped_overlap",
                "insufficient_evidence",
            ],
            reason_explanations={
                "FLOOD_EXTENT_INTERSECTS": (
                    "Qualifying flood extent polygon intersects the claimed road LineString within the policy window."
                ),
                "NO_MAPPED_OVERLAP": (
                    "Fresh observation with documented coverage enclosing the entire road shows no mapped flood intersection."
                ),
                "OBSERVATION_STALE": (
                    f"Absolute time difference between observation and claim exceeds {max_age_hours:g} hours."
                ),
                "OBSERVATION_TIME_UNKNOWN": (
                    "Evidence record has no documented acquisition timestamp (observed_at is null)."
                ),
                "COVERAGE_UNKNOWN": (
                    "No documented observation coverage polygon is present, so a negative finding cannot be made."
                ),
                "OUTSIDE_COVERAGE": (
                    "Part or all of the claimed road lies outside documented observation coverage."
                ),
                "NO_EVIDENCE": "No relevant flood_extent evidence records were available.",
                "AUTHENTICATION_FAILED": (
                    "Evidence item failed authentication and was excluded from conflict determination."
                ),
                "NOT_AVAILABLE_AT_DECISION_TIME": (
                    "Evidence was observed or became available after the specified decision_time."
                ),
                "AVAILABILITY_TIME_UNKNOWN": (
                    "Evidence lacks a documented available_at timestamp and cannot be shown to have been available at decision_time."
                ),
            },
            known_limitations=[
                "Absence of evidence does not establish road passability or safety.",
                "The 24-hour assessment window is a demonstration policy, not operational safety guidance.",
            ],
        )

    @property
    def spec(self) -> PolicySpec:
        return self._spec

    def validate_claim(self, claim: ClaimRequest) -> None:
        if claim.geometry is None or claim.geometry.type != "LineString":
            raise ClaimValidationError(
                "road_passable claims require a valid WGS84 GeoJSON LineString geometry.",
                field_path="geometry",
            )

    def is_evidence_relevant(self, claim: ClaimRequest, evidence: Evidence) -> bool:
        return evidence.kind == "flood_extent"

    def evaluate_evidence(
        self,
        claim: ClaimRequest,
        evidence: Evidence,
        context: EvidenceContext,
    ) -> EvidenceFinding:
        age_hours = context.temporal.age_hours

        if evidence.observed_at is None or age_hours is None:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=None,
                reasons=["OBSERVATION_TIME_UNKNOWN"],
            )

        if age_hours > self._max_age_hours:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["OBSERVATION_STALE"],
            )

        if evidence.geometry is None or evidence.geometry.type not in (
            "Polygon",
            "MultiPolygon",
        ):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["COVERAGE_UNKNOWN"],
            )

        claim_geom = to_shapely(claim.geometry)  # type: ignore[arg-type]
        flood_geom = to_shapely(evidence.geometry)
        cov_geom = to_shapely(evidence.coverage) if evidence.coverage is not None else None
        spatial = evaluate_spatial_relation(claim_geom, flood_geom, cov_geom)

        if spatial.has_coverage and not spatial.intersects_coverage:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["OUTSIDE_COVERAGE"],
            )

        if spatial.intersects_observation:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="potential_conflict",
                age_hours=age_hours,
                reasons=["FLOOD_EXTENT_INTERSECTS"],
            )

        if not spatial.has_coverage:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["COVERAGE_UNKNOWN"],
            )

        if spatial.fully_within_coverage:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="no_mapped_overlap",
                age_hours=age_hours,
                reasons=["NO_MAPPED_OVERLAP"],
            )

        return EvidenceFinding(
            evidence_id=evidence.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["OUTSIDE_COVERAGE"],
        )

    def aggregate(
        self,
        claim: ClaimRequest,
        findings: list[EvidenceFinding],
        evidence_items: list[Evidence],
        independence: IndependenceSummary,
        context: AssessmentContext,
    ) -> PolicyDecision:
        if any(f.status == "potential_conflict" for f in findings):
            overall_status = "potential_conflict"
        elif any(f.status == "no_mapped_overlap" for f in findings):
            overall_status = "no_mapped_overlap"
        else:
            overall_status = "insufficient_evidence"

        primary_reasons: list[str] = []
        secondary_reasons: list[str] = []
        for f in findings:
            target = primary_reasons if f.status == overall_status else secondary_reasons
            target.extend(f.reasons)

        ordered_reasons: list[str] = []
        for reason in primary_reasons + secondary_reasons:
            if reason not in ordered_reasons:
                ordered_reasons.append(reason)

        limitations: list[str] = []
        if overall_status == "potential_conflict":
            limitations.append(
                "Mapped flood overlap does not establish road impassability."
            )
        elif overall_status == "no_mapped_overlap":
            limitations.append(
                "Absence of mapped flood overlap does not establish road passability or safety."
            )
        else:
            limitations.append(
                "Insufficient evidence to determine flood overlap; absence of mapped flooding is not proof of safety."
            )

        if context.assessment_mode == "retrospective":
            limitations.append(
                "Historical replay evaluates observations within a 24-hour window (before or after claim time) as a demo policy, not operational safety guidance."
            )
        else:
            limitations.append(
                "Decision-time assessment evaluates only observations demonstrably acquired and available on or before decision_time within a 24-hour policy window."
            )

        return PolicyDecision(
            status=overall_status,
            reasons=ordered_reasons,
            limitations=limitations,
        )
