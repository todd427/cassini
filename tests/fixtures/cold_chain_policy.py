"""Test-only non-geographical assessment policy demonstrating EIP v0.2 extensibility.

Domain: Pharmaceutical cold-chain temperature compliance (`cold_chain_within_limits`).
Demonstrates that a completely different, non-geographical domain can be
registered, discovered, and evaluated without modifying `core/` or `api/`.
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


class ColdChainTestPolicy:
    """Minimal test-only policy evaluating cold-chain temperature telemetry."""

    def __init__(self, max_age_hours: float = 6.0) -> None:
        self._max_age_hours = max_age_hours
        self._spec = PolicySpec(
            policy_id="test-cold-chain",
            policy_version="test-cold-chain-0.1",
            name="Test-Only Cold-Chain Temperature Compliance",
            description=(
                "Synthetic test policy verifying whether non-geographical cold-chain "
                "temperature telemetry conflicts with a claimed in-range shipment state."
            ),
            supported_claim_types=["cold_chain_within_limits"],
            required_evidence_kinds=["temperature_telemetry"],
            optional_evidence_kinds=[],
            evidence_relevance_criteria=[
                "Evidence kind equals 'temperature_telemetry'.",
                "Evidence requires no GeoJSON geometry (geometry may be null).",
                "Evidence attributes include numeric 'min_temp_c' and 'max_temp_c'.",
                "Observation age within max_age_hours of claimed_at.",
            ],
            assessment_rules_summary=[
                "Any eligible reading outside [allowed_min_c, allowed_max_c] -> potential_conflict (TEMPERATURE_EXCURSION_DETECTED).",
                "All readings within limits with at least one eligible reading -> within_limits (WITHIN_TEMPERATURE_LIMITS).",
                "Missing/stale/unverified-availability/incomplete readings -> insufficient_evidence.",
            ],
            thresholds={"max_age_hours": max_age_hours},
            possible_outcomes=[
                "potential_conflict",
                "within_limits",
                "insufficient_evidence",
            ],
            reason_explanations={
                "TEMPERATURE_EXCURSION_DETECTED": (
                    "Observed telemetry fell outside the claimed allowed temperature bounds."
                ),
                "WITHIN_TEMPERATURE_LIMITS": (
                    "Qualifying telemetry stayed within declared bounds; does not guarantee product potency."
                ),
                "OBSERVATION_STALE": (
                    f"Telemetry age exceeded the {max_age_hours:g}-hour policy window."
                ),
                "OBSERVATION_TIME_UNKNOWN": "Telemetry record lacks observed_at timestamp.",
                "TELEMETRY_INCOMPLETE": "Telemetry record lacks numeric min_temp_c or max_temp_c.",
                "NOT_AVAILABLE_AT_DECISION_TIME": (
                    "Telemetry was recorded or published after decision_time."
                ),
                "AVAILABILITY_TIME_UNKNOWN": (
                    "Telemetry lacks available_at timestamp for decision-time verification."
                ),
            },
            known_limitations=[
                "Test-only synthetic demonstration policy; not validated for pharmaceutical QA or regulatory release.",
                "Sensor readings within limits do not guarantee thermal uniformity across the entire container.",
            ],
        )

    @property
    def spec(self) -> PolicySpec:
        return self._spec

    def validate_claim(self, claim: ClaimRequest) -> None:
        lo = claim.attributes.get("allowed_min_c")
        hi = claim.attributes.get("allowed_max_c")
        if (
            isinstance(lo, bool)
            or isinstance(hi, bool)
            or not isinstance(lo, (int, float))
            or not isinstance(hi, (int, float))
        ):
            raise ClaimValidationError(
                "cold_chain_within_limits claims require numeric attributes.allowed_min_c and attributes.allowed_max_c.",
                field_path="attributes",
            )
        if lo >= hi:
            raise ClaimValidationError(
                "attributes.allowed_min_c must be strictly less than attributes.allowed_max_c.",
                field_path="attributes",
            )

    def is_evidence_relevant(self, claim: ClaimRequest, evidence: Evidence) -> bool:
        return evidence.kind == "temperature_telemetry"

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

        obs_min = evidence.attributes.get("min_temp_c")
        obs_max = evidence.attributes.get("max_temp_c")
        if (
            isinstance(obs_min, bool)
            or isinstance(obs_max, bool)
            or not isinstance(obs_min, (int, float))
            or not isinstance(obs_max, (int, float))
        ):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="insufficient_evidence",
                age_hours=age_hours,
                reasons=["TELEMETRY_INCOMPLETE"],
            )

        allowed_min = float(claim.attributes["allowed_min_c"])
        allowed_max = float(claim.attributes["allowed_max_c"])
        if float(obs_min) < allowed_min or float(obs_max) > allowed_max:
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="potential_conflict",
                age_hours=age_hours,
                reasons=["TEMPERATURE_EXCURSION_DETECTED"],
            )

        return EvidenceFinding(
            evidence_id=evidence.id,
            status="within_limits",
            age_hours=age_hours,
            reasons=["WITHIN_TEMPERATURE_LIMITS"],
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
            status = "potential_conflict"
        elif any(f.status == "within_limits" for f in findings):
            status = "within_limits"
        else:
            status = "insufficient_evidence"

        reasons: list[str] = []
        for f in findings:
            if f.status == status:
                for r in f.reasons:
                    if r not in reasons:
                        reasons.append(r)
        for f in findings:
            if f.status != status:
                for r in f.reasons:
                    if r not in reasons:
                        reasons.append(r)

        limitations = list(self._spec.known_limitations)
        if (
            independence.status == "shared_dependencies_detected"
            and independence.independent_group_count == 1
        ):
            limitations.append(
                "All cold-chain telemetry records share an upstream source and represent a single non-independent observation lineage."
            )

        return PolicyDecision(status=status, reasons=reasons, limitations=limitations)
