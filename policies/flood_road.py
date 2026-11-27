"""Flood-road passability assessment policy (policy_version: flood-road-0.1).

Preserves 100% of EIP v0.1.0/v0.2.0 direct `flood_extent` behaviour while
supporting optional indirect/contextual evidence (`hydrometric_water_level`,
`meteorological_rainfall`) introduced in v0.3.0.

Epistemic rules:
- Direct observations (`flood_extent`): can produce `potential_conflict` or
  `no_mapped_overlap` (when full coverage is documented).
- Indirect contextual observations (`hydrometric_water_level`,
  `meteorological_rainfall`): can produce `contextual_support` or
  `contextual_neutral` per-source findings, but NEVER alone establish
  `potential_conflict` or `no_mapped_overlap` for a specific road segment.
- Absence of mapped flooding is never proof of road safety.
"""

from __future__ import annotations

import math

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
DEFAULT_HYDROMETRIC_RADIUS_KM = 10.0
DEFAULT_METEOROLOGICAL_RADIUS_KM = 40.0

DIRECT_EVIDENCE_KINDS = ("flood_extent",)
OPTIONAL_CONTEXTUAL_KINDS = ("hydrometric_water_level", "meteorological_rainfall")


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    r_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * r_km * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _min_distance_point_to_line_km(
    pt_lon: float,
    pt_lat: float,
    claim_geom,
) -> float:
    nearest = claim_geom.interpolate(claim_geom.project(to_shapely_point(pt_lon, pt_lat)))
    return _haversine_km(pt_lon, pt_lat, nearest.x, nearest.y)


def to_shapely_point(lon: float, lat: float):
    from shapely.geometry import Point

    return Point(lon, lat)


class FloodRoadPolicy:
    """Evaluates road passability claims against direct flood extent and optional contextual sources."""

    def __init__(
        self,
        max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
        hydrometric_radius_km: float = DEFAULT_HYDROMETRIC_RADIUS_KM,
        meteorological_radius_km: float = DEFAULT_METEOROLOGICAL_RADIUS_KM,
    ) -> None:
        self._max_age_hours = max_age_hours
        self._hydrometric_radius_km = hydrometric_radius_km
        self._meteorological_radius_km = meteorological_radius_km
        self._spec = PolicySpec(
            policy_id=POLICY_ID,
            policy_version=POLICY_VERSION,
            name="Flood Extent vs Road Passability",
            description=(
                "Evaluates whether direct mapped flood extent observations overlap a claimed "
                "passable road LineString within a configured temporal window, enriched with "
                "optional independent indirect contextual observations (hydrometric water level "
                "and regional rainfall) that never substitute for direct road inundation evidence."
            ),
            supported_claim_types=["road_passable"],
            required_evidence_kinds=list(DIRECT_EVIDENCE_KINDS),
            optional_evidence_kinds=list(OPTIONAL_CONTEXTUAL_KINDS),
            evidence_relevance_criteria=[
                "Direct evidence: kind equals 'flood_extent' with valid WGS84 Polygon/MultiPolygon.",
                f"Optional indirect evidence: 'hydrometric_water_level' within {hydrometric_radius_km:g} km of the claimed road.",
                f"Optional indirect evidence: 'meteorological_rainfall' within {meteorological_radius_km:g} km of the claimed road.",
                f"Observation timestamp within {max_age_hours:g} hours of claimed_at.",
                "In decision_time mode, evidence must be observed and demonstrably available on or before decision_time.",
            ],
            assessment_rules_summary=[
                "Intersecting fresh direct flood_extent -> potential_conflict (FLOOD_EXTENT_INTERSECTS).",
                "Non-intersecting fresh direct flood_extent whose documented coverage encloses the entire road -> no_mapped_overlap (NO_MAPPED_OVERLAP).",
                "Indirect contextual observations (hydrometric stage, rainfall) produce contextual_support/contextual_neutral findings only and NEVER alone trigger potential_conflict or no_mapped_overlap.",
                "If only indirect contextual observations qualify without direct flood_extent -> insufficient_evidence (INDIRECT_EVIDENCE_ONLY).",
                "Multi-source precedence across direct findings: potential_conflict > no_mapped_overlap > insufficient_evidence.",
            ],
            thresholds={
                "max_age_hours": max_age_hours,
                "hydrometric_radius_km": hydrometric_radius_km,
                "meteorological_radius_km": meteorological_radius_km,
            },
            possible_outcomes=[
                "potential_conflict",
                "no_mapped_overlap",
                "insufficient_evidence",
            ],
            reason_explanations={
                "FLOOD_EXTENT_INTERSECTS": (
                    "Qualifying direct flood extent polygon intersects the claimed road LineString within the policy window."
                ),
                "NO_MAPPED_OVERLAP": (
                    "Fresh direct observation with documented coverage enclosing the entire road shows no mapped flood intersection."
                ),
                "CONTEXTUAL_WATER_LEVEL_ELEVATED": (
                    "Nearby hydrometric gauge recorded elevated water stage (>= historical 95th percentile); indirect context only, not direct proof of road flooding."
                ),
                "CONTEXTUAL_WATER_LEVEL_NORMAL": (
                    "Nearby hydrometric gauge recorded water stage below historical 95th percentile; indirect context only, not proof of road safety."
                ),
                "CONTEXTUAL_RAINFALL_OBSERVED": (
                    "Regional weather station recorded notable precipitation; indirect environmental context only, not direct proof of road flooding."
                ),
                "CONTEXTUAL_RAINFALL_LOW": (
                    "Regional weather station recorded low/zero precipitation; indirect context only, not proof of road safety."
                ),
                "INDIRECT_EVIDENCE_ONLY": (
                    "Only indirect contextual observations (water level or rainfall) qualified; direct spatial flood observation is required to evaluate road-segment overlap."
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
                    "Part or all of the claimed road lies outside documented observation coverage or station spatial relevance radius."
                ),
                "NO_EVIDENCE": "No relevant flood or contextual evidence records were available.",
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
                "Elevated water levels or rainfall are indirect indicators and cannot prove that a specific road segment was flooded.",
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
        return evidence.kind in DIRECT_EVIDENCE_KINDS or evidence.kind in OPTIONAL_CONTEXTUAL_KINDS

    def _evaluate_direct_flood(
        self,
        claim: ClaimRequest,
        evidence: Evidence,
        age_hours: float,
    ) -> EvidenceFinding:
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

    def _evaluate_hydrometric(
        self,
        claim: ClaimRequest,
        evidence: Evidence,
        age_hours: float,
    ) -> EvidenceFinding:
        if evidence.geometry is None or evidence.geometry.type != "Point":
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["COVERAGE_UNKNOWN"],
            )
        claim_geom = to_shapely(claim.geometry)  # type: ignore[arg-type]
        lon, lat = evidence.geometry.coordinates[0], evidence.geometry.coordinates[1]
        dist_km = _min_distance_point_to_line_km(lon, lat, claim_geom)
        if dist_km > self._hydrometric_radius_km:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["OUTSIDE_COVERAGE"],
            )

        stage = evidence.attributes.get("stage_maod")
        p95 = evidence.attributes.get("historical_p95_maod")
        above_p95 = evidence.attributes.get("above_historical_p95")
        if above_p95 is True or (
            isinstance(stage, (int, float))
            and isinstance(p95, (int, float))
            and float(stage) >= float(p95)
        ):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="contextual_support",
                age_hours=age_hours,
                reasons=["CONTEXTUAL_WATER_LEVEL_ELEVATED"],
            )
        if isinstance(stage, (int, float)):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="contextual_neutral",
                age_hours=age_hours,
                reasons=["CONTEXTUAL_WATER_LEVEL_NORMAL"],
            )
        return EvidenceFinding(
            evidence_id=evidence.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["COVERAGE_UNKNOWN"],
        )

    def _evaluate_meteorological(
        self,
        claim: ClaimRequest,
        evidence: Evidence,
        age_hours: float,
    ) -> EvidenceFinding:
        if evidence.geometry is None or evidence.geometry.type != "Point":
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["COVERAGE_UNKNOWN"],
            )
        claim_geom = to_shapely(claim.geometry)  # type: ignore[arg-type]
        lon, lat = evidence.geometry.coordinates[0], evidence.geometry.coordinates[1]
        dist_km = _min_distance_point_to_line_km(lon, lat, claim_geom)
        if dist_km > self._meteorological_radius_km:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["OUTSIDE_COVERAGE"],
            )

        rain_mm = evidence.attributes.get("rain_mm")
        rain_5d = evidence.attributes.get("cumulative_5day_rain_mm")
        if (
            isinstance(rain_mm, (int, float))
            and (float(rain_mm) >= 5.0 or (isinstance(rain_5d, (int, float)) and float(rain_5d) >= 20.0))
        ):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="contextual_support",
                age_hours=age_hours,
                reasons=["CONTEXTUAL_RAINFALL_OBSERVED"],
            )
        if isinstance(rain_mm, (int, float)):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="contextual_neutral",
                age_hours=age_hours,
                reasons=["CONTEXTUAL_RAINFALL_LOW"],
            )
        return EvidenceFinding(
            evidence_id=evidence.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["COVERAGE_UNKNOWN"],
        )

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

        if evidence.kind == "flood_extent":
            return self._evaluate_direct_flood(claim, evidence, age_hours)
        if evidence.kind == "hydrometric_water_level":
            return self._evaluate_hydrometric(claim, evidence, age_hours)
        if evidence.kind == "meteorological_rainfall":
            return self._evaluate_meteorological(claim, evidence, age_hours)

        return EvidenceFinding(
            evidence_id=evidence.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["COVERAGE_UNKNOWN"],
        )

    def aggregate(
        self,
        claim: ClaimRequest,
        findings: list[EvidenceFinding],
        evidence_items: list[Evidence],
        independence: IndependenceSummary,
        context: AssessmentContext,
    ) -> PolicyDecision:
        kind_by_id = {ev.id: ev.kind for ev in evidence_items}
        direct_findings = [
            f for f in findings if kind_by_id.get(f.evidence_id) in DIRECT_EVIDENCE_KINDS
        ]
        contextual_findings = [
            f for f in findings if kind_by_id.get(f.evidence_id) in OPTIONAL_CONTEXTUAL_KINDS
        ]

        if any(f.status == "potential_conflict" for f in direct_findings):
            overall_status = "potential_conflict"
        elif any(f.status == "no_mapped_overlap" for f in direct_findings):
            overall_status = "no_mapped_overlap"
        else:
            overall_status = "insufficient_evidence"

        primary_reasons: list[str] = []
        secondary_reasons: list[str] = []

        has_qualifying_contextual = any(
            f.status in ("contextual_support", "contextual_neutral")
            for f in contextual_findings
        )

        # If overall is insufficient_evidence and no direct evidence was provided
        # while indirect contextual evidence qualified, surface INDIRECT_EVIDENCE_ONLY
        if (
            overall_status == "insufficient_evidence"
            and len(direct_findings) == 0
            and has_qualifying_contextual
        ):
            primary_reasons.append("INDIRECT_EVIDENCE_ONLY")

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
            if any(f.status == "no_mapped_overlap" for f in direct_findings):
                limitations.append(
                    "Direct flood observations disagree (at least one overlaps while another shows no mapped overlap); potential_conflict takes precedence."
                )
        elif overall_status == "no_mapped_overlap":
            limitations.append(
                "Absence of mapped flood overlap does not establish road passability or safety."
            )
            if any(f.status == "contextual_support" for f in contextual_findings):
                limitations.append(
                    "Independent contextual observations indicate elevated regional flood conditions despite no mapped overlap on this specific road segment."
                )
        else:
            limitations.append(
                "Insufficient evidence to determine flood overlap; absence of mapped flooding is not proof of safety."
            )

        if has_qualifying_contextual:
            limitations.append(
                "Hydrometric water levels and regional rainfall are indirect contextual indicators and do not establish whether a specific road segment was flooded."
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
