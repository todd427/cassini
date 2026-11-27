"""Deterministic spatial/temporal evidence assessment engine (policy flood-road-0.1)."""

from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import shape

from core.models import (
    MAX_AGE_HOURS,
    POLICY_VERSION,
    AssessmentResponse,
    AssessmentStatus,
    ClaimRequest,
    Evidence,
    EvidenceFinding,
    ReasonCode,
)


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _compute_age_hours(claim: ClaimRequest, ev: Evidence) -> float | None:
    if ev.observed_at is None:
        return None
    delta_seconds = abs((ev.observed_at - claim.claimed_at).total_seconds())
    return round(delta_seconds / 3600.0, 6)


def _evaluate_single_evidence(
    claim: ClaimRequest,
    claim_geom,
    ev: Evidence,
    max_age_hours: float,
) -> EvidenceFinding:
    age_hours = _compute_age_hours(claim, ev)

    if ev.authentication == "failed":
        return EvidenceFinding(
            evidence_id=ev.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["AUTHENTICATION_FAILED"],
        )

    if ev.observed_at is None or age_hours is None:
        return EvidenceFinding(
            evidence_id=ev.id,
            status="insufficient_evidence",
            age_hours=None,
            reasons=["OBSERVATION_TIME_UNKNOWN"],
        )

    if age_hours > max_age_hours:
        return EvidenceFinding(
            evidence_id=ev.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["OBSERVATION_STALE"],
        )

    flood_geom = shape(ev.geometry.model_dump())
    cov_geom = shape(ev.coverage.model_dump()) if ev.coverage is not None else None

    if cov_geom is not None and not cov_geom.intersects(claim_geom):
        return EvidenceFinding(
            evidence_id=ev.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["OUTSIDE_COVERAGE"],
        )

    if flood_geom.intersects(claim_geom):
        return EvidenceFinding(
            evidence_id=ev.id,
            status="potential_conflict",
            age_hours=age_hours,
            reasons=["FLOOD_EXTENT_INTERSECTS"],
        )

    if cov_geom is None:
        return EvidenceFinding(
            evidence_id=ev.id,
            status="insufficient_evidence",
            age_hours=age_hours,
            reasons=["COVERAGE_UNKNOWN"],
        )

    if cov_geom.covers(claim_geom):
        return EvidenceFinding(
            evidence_id=ev.id,
            status="no_mapped_overlap",
            age_hours=age_hours,
            reasons=["NO_MAPPED_OVERLAP"],
        )

    return EvidenceFinding(
        evidence_id=ev.id,
        status="insufficient_evidence",
        age_hours=age_hours,
        reasons=["OUTSIDE_COVERAGE"],
    )


def assess_claim(
    claim: ClaimRequest,
    evidence_items: Sequence[Evidence],
    max_age_hours: float = MAX_AGE_HOURS,
) -> AssessmentResponse:
    """Assess a road passability claim against independent flood extent evidence."""
    if not evidence_items:
        return AssessmentResponse(
            claim_id=claim.claim_id,
            status="insufficient_evidence",
            policy_version=POLICY_VERSION,
            reasons=["NO_EVIDENCE"],
            evidence_ids=[],
            findings=[],
            limitations=[
                "No evidence records were available for assessment.",
                "Absence of evidence does not establish road passability or safety.",
                "The 24-hour assessment window is a demonstration policy, not operational safety guidance.",
            ],
            synthetic=claim.synthetic,
        )

    claim_geom = shape(claim.geometry.model_dump())
    findings: list[EvidenceFinding] = [
        _evaluate_single_evidence(claim, claim_geom, ev, max_age_hours)
        for ev in evidence_items
    ]

    if any(f.status == "potential_conflict" for f in findings):
        overall_status: AssessmentStatus = "potential_conflict"
    elif any(f.status == "no_mapped_overlap" for f in findings):
        overall_status = "no_mapped_overlap"
    else:
        overall_status = "insufficient_evidence"

    primary_reasons: list[ReasonCode] = []
    secondary_reasons: list[ReasonCode] = []
    for f in findings:
        target = primary_reasons if f.status == overall_status else secondary_reasons
        for reason in f.reasons:
            target.append(reason)

    ordered_reasons: list[ReasonCode] = []
    for reason in primary_reasons + secondary_reasons:
        if reason not in ordered_reasons:
            ordered_reasons.append(reason)

    limitations: list[str] = []
    if overall_status == "potential_conflict":
        limitations.append("Mapped flood overlap does not establish road impassability.")
    elif overall_status == "no_mapped_overlap":
        limitations.append(
            "Absence of mapped flood overlap does not establish road passability or safety."
        )
    else:
        limitations.append(
            "Insufficient evidence to determine flood overlap; absence of mapped flooding is not proof of safety."
        )

    if any(ev.authentication == "unknown" for ev in evidence_items):
        limitations.append(
            "Evidence authenticity is unknown (unverified); SHA-256 checksums prove local byte integrity only."
        )
    if any(ev.authentication == "failed" for ev in evidence_items):
        limitations.append(
            "Evidence items with failed authentication were excluded from conflict determination."
        )
    if len(evidence_items) > 1:
        limitations.append(
            "Multiple evidence records may derive from correlated observations and are not treated as independent."
        )
    limitations.append(
        "Historical replay evaluates observations within a 24-hour window (before or after claim time) as a demo policy, not operational safety guidance."
    )
    for ev in evidence_items:
        limitations.extend(ev.limitations)

    synthetic_flag = bool(claim.synthetic or any(ev.synthetic for ev in evidence_items))

    return AssessmentResponse(
        claim_id=claim.claim_id,
        status=overall_status,
        policy_version=POLICY_VERSION,
        reasons=ordered_reasons,
        evidence_ids=[ev.id for ev in evidence_items],
        findings=findings,
        limitations=_dedupe_preserve_order(limitations),
        synthetic=synthetic_flag,
    )
