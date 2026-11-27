"""Generic, domain-independent evidence assessment engine.

Contains zero domain-specific rules, thresholds, or interpretations.
All domain logic lives in registered AssessmentPolicy implementations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from core.independence import analyze_source_independence
from core.integrity import is_authentication_failed, is_authentication_unverified
from core.models import (
    AssessmentResponse,
    AssessmentTraceability,
    ClaimRequest,
    Evidence,
    EvidenceFinding,
    TemporalContext,
)
from core.policy import AssessmentContext, EvidenceContext, PolicyRegistry
from core.temporal import evaluate_temporal_eligibility


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _compute_input_fingerprint(
    claim: ClaimRequest,
    evidence_items: Sequence[Evidence],
    policy_id: str,
    policy_version: str,
) -> str:
    canonical = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "claim": claim.model_dump(mode="json", exclude={"assessed_at"}),
        "evidence": [
            {
                "id": ev.id,
                "kind": ev.kind,
                "observed_at": ev.model_dump(mode="json")["observed_at"],
                "available_at": ev.model_dump(mode="json")["available_at"],
                "sha256": ev.sha256,
                "authentication": ev.authentication,
                "synthetic": ev.synthetic,
            }
            for ev in evidence_items
        ],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AssessmentEngine:
    """Domain-independent engine orchestrating generic checks and policy dispatch."""

    def __init__(self, registry: PolicyRegistry) -> None:
        self.registry = registry

    def assess(
        self,
        claim: ClaimRequest,
        evidence_items: Sequence[Evidence],
        assessed_at: datetime | None = None,
    ) -> AssessmentResponse:
        policy = self.registry.resolve(claim.claim_type, claim.policy_id)
        spec = policy.spec
        policy.validate_claim(claim)

        effective_assessed_at = assessed_at if assessed_at is not None else claim.assessed_at
        relevant_evidence = [
            ev for ev in evidence_items if policy.is_evidence_relevant(claim, ev)
        ]

        fingerprint = _compute_input_fingerprint(
            claim=claim,
            evidence_items=relevant_evidence,
            policy_id=spec.policy_id,
            policy_version=spec.policy_version,
        )
        traceability = AssessmentTraceability(
            policy_id=spec.policy_id,
            policy_version=spec.policy_version,
            input_fingerprint=fingerprint,
            assessed_at=effective_assessed_at,
        )

        if not relevant_evidence:
            independence = analyze_source_independence([])
            temporal_ctx = TemporalContext(
                assessment_mode=claim.assessment_mode,
                claimed_at=claim.claimed_at,
                decision_time=claim.decision_time,
                assessed_at=effective_assessed_at,
            )
            limitations = [
                "No evidence records were available for assessment.",
                *spec.known_limitations,
            ]
            return AssessmentResponse(
                claim_id=claim.claim_id,
                status="insufficient_evidence",
                policy_version=spec.policy_version,
                reasons=["NO_EVIDENCE"],
                evidence_ids=[],
                findings=[],
                limitations=_dedupe_preserve_order(limitations),
                synthetic=claim.synthetic,
                assessment_mode=claim.assessment_mode,
                temporal_context=temporal_ctx,
                independence=independence,
                traceability=traceability,
            )

        findings: list[EvidenceFinding] = []
        excluded_not_available_ids: list[str] = []
        unknown_availability_ids: list[str] = []

        for ev in relevant_evidence:
            temporal = evaluate_temporal_eligibility(
                evidence=ev,
                claimed_at=claim.claimed_at,
                assessment_mode=claim.assessment_mode,
                decision_time=claim.decision_time,
            )

            if is_authentication_failed(ev):
                findings.append(
                    EvidenceFinding(
                        evidence_id=ev.id,
                        status="insufficient_evidence",
                        age_hours=temporal.age_hours,
                        reasons=["AUTHENTICATION_FAILED"],
                    )
                )
                continue

            if not temporal.eligible:
                reason = temporal.exclusion_reason or "NOT_AVAILABLE_AT_DECISION_TIME"
                if temporal.availability_status == "availability_unknown":
                    unknown_availability_ids.append(ev.id)
                else:
                    excluded_not_available_ids.append(ev.id)
                findings.append(
                    EvidenceFinding(
                        evidence_id=ev.id,
                        status="insufficient_evidence",
                        age_hours=temporal.age_hours,
                        reasons=[reason],
                    )
                )
                continue

            ev_context = EvidenceContext(
                temporal=temporal,
                assessment_mode=claim.assessment_mode,
                decision_time=claim.decision_time,
            )
            findings.append(policy.evaluate_evidence(claim, ev, ev_context))

        independence = analyze_source_independence(relevant_evidence)
        assess_context = AssessmentContext(
            assessment_mode=claim.assessment_mode,
            decision_time=claim.decision_time,
            assessed_at=effective_assessed_at,
        )
        decision = policy.aggregate(
            claim=claim,
            findings=findings,
            evidence_items=relevant_evidence,
            independence=independence,
            context=assess_context,
        )

        limitations: list[str] = list(decision.limitations)

        if any(is_authentication_unverified(ev) for ev in relevant_evidence):
            limitations.append(
                "Evidence authenticity is unknown (unverified); SHA-256 checksums prove local byte integrity only."
            )
        if any(is_authentication_failed(ev) for ev in relevant_evidence):
            limitations.append(
                "Evidence items with failed authentication were excluded from conflict determination."
            )
        if excluded_not_available_ids:
            limitations.append(
                "One or more evidence items were acquired or published after decision_time and were excluded from decision-time assessment."
            )
        if unknown_availability_ids:
            limitations.append(
                "One or more evidence items lack a documented availability/publication timestamp (available_at is null) and could not be demonstrated as available at decision_time."
            )
        if len(relevant_evidence) > 1:
            limitations.extend(independence.notes)

        for ev in relevant_evidence:
            limitations.extend(ev.limitations)

        synthetic_flag = bool(
            claim.synthetic or any(ev.synthetic for ev in relevant_evidence)
        )
        temporal_ctx = TemporalContext(
            assessment_mode=claim.assessment_mode,
            claimed_at=claim.claimed_at,
            decision_time=claim.decision_time,
            assessed_at=effective_assessed_at,
            excluded_not_available_ids=excluded_not_available_ids,
            unknown_availability_ids=unknown_availability_ids,
        )

        return AssessmentResponse(
            claim_id=claim.claim_id,
            status=decision.status,
            policy_version=spec.policy_version,
            reasons=decision.reasons,
            evidence_ids=[ev.id for ev in relevant_evidence],
            findings=findings,
            limitations=_dedupe_preserve_order(limitations),
            synthetic=synthetic_flag,
            assessment_mode=claim.assessment_mode,
            temporal_context=temporal_ctx,
            independence=independence,
            traceability=traceability,
        )
