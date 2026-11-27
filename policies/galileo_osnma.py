"""Galileo OSNMA Navigation-Message Authentication policy (galileo-osnma-0.1).

Supports two explicit claim types:
- `gnss_nav_message_authenticated`: Assesses whether broadcast Galileo I/NAV
  navigation messages (ephemeris/clock/iono/health ADKD=0) were cryptographically
  authenticated via OSNMA, distinguishing locally verified cryptography from
  externally reported flags, pending verification, outages, and failures.
- `gnss_position_accurate`: Explicitly demonstrates that navigation-message
  authentication CANNOT establish user positioning accuracy, receiver
  trustworthiness, or immunity to meaconing/relay spoofing (`evidence_unsuitable`).

Zero modifications to `core/` are required to register or run this policy.
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

POLICY_ID = "galileo-osnma"
POLICY_VERSION = "galileo-osnma-0.1"
DEFAULT_MAX_AGE_HOURS = 1.0


class GalileoOsnmaPolicy:
    """Evaluates Galileo OSNMA navigation-message authentication claims."""

    def __init__(self, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> None:
        self._max_age_hours = max_age_hours
        self._spec = PolicySpec(
            policy_id=POLICY_ID,
            policy_version=POLICY_VERSION,
            name="Galileo OSNMA Navigation-Message Authentication",
            description=(
                "Evaluates whether recorded or observed Galileo E1-B I/NAV navigation "
                "messages (ADKD=0 ephemeris/clock data) passed local OSNMA cryptographic "
                "verification. Explicitly rejects using navigation-message authentication "
                "to prove user positioning accuracy or receiver integrity."
            ),
            supported_claim_types=[
                "gnss_nav_message_authenticated",
                "gnss_position_accurate",
            ],
            required_evidence_kinds=["gnss_osnma_auth"],
            optional_evidence_kinds=[],
            evidence_relevance_criteria=[
                "Evidence kind equals 'gnss_osnma_auth'.",
                f"Observation timestamp is within {max_age_hours:g} hour(s) of claimed_at.",
                "Optional claim attribute 'svid' (1-36) matches authenticated_svids if specified.",
                "In decision_time mode, evidence must be observed and demonstrably available on or before decision_time.",
            ],
            assessment_rules_summary=[
                "Claim type 'gnss_position_accurate' -> evidence_unsuitable (NAV_AUTH_INSUFFICIENT_FOR_POSITIONING): OSNMA authenticates navigation bits only, never user position.",
                "Local cryptographic verification passed (Merkle + ECDSA + TESLA + MAC Tag0) -> authenticated (OSNMA_LOCALLY_VERIFIED).",
                "Failed cryptographic verification -> authentication_failed (AUTHENTICATION_FAILED).",
                "Incomplete DSM-KROOT or awaiting delayed TESLA key disclosure -> authentication_pending (OSNMA_AUTHENTICATION_PENDING).",
                "OSNMA broadcast absent / outage -> authentication_unavailable (OSNMA_AUTHENTICATION_UNAVAILABLE).",
                "Externally reported authentication without local cryptographic verification -> authentication_unknown (OSNMA_EXTERNALLY_REPORTED_UNVERIFIED).",
                "Missing, stale, or unavailable-at-decision-time evidence -> insufficient_evidence.",
            ],
            thresholds={"max_age_hours": max_age_hours},
            possible_outcomes=[
                "authenticated",
                "authentication_failed",
                "authentication_pending",
                "authentication_unavailable",
                "authentication_unknown",
                "evidence_unsuitable",
                "insufficient_evidence",
            ],
            reason_explanations={
                "OSNMA_LOCALLY_VERIFIED": (
                    "Galileo I/NAV ADKD=0 navigation data bits were locally verified via GSC Merkle proof, ECDSA DSM-KROOT signature, TESLA SHA-256 chain, and HMAC-SHA-256 Tag0."
                ),
                "AUTHENTICATION_FAILED": (
                    "Cryptographic OSNMA verification failed (Merkle proof, ECDSA signature, TESLA chain, or MAC tag mismatch)."
                ),
                "OSNMA_AUTHENTICATION_PENDING": (
                    "Navigation data received, but OSNMA cryptographic verification is pending delayed TESLA key disclosure or full DSM-KROOT assembly."
                ),
                "OSNMA_AUTHENTICATION_UNAVAILABLE": (
                    "OSNMA authentication data was absent or unavailable in the recorded Galileo broadcast."
                ),
                "OSNMA_EXTERNALLY_REPORTED_UNVERIFIED": (
                    "An external receiver/source reported authentication without local cryptographic re-verification; treated as unverified (unknown)."
                ),
                "OSNMA_AUTHENTICATION_UNKNOWN": (
                    "Authentication status of the navigation message could not be verified locally."
                ),
                "NAV_AUTH_INSUFFICIENT_FOR_POSITIONING": (
                    "Galileo OSNMA authenticates broadcast satellite navigation data bits only; it cannot establish user positioning accuracy, pseudorange integrity, receiver trustworthiness, or defense against meaconing/relay spoofing."
                ),
                "SVID_NOT_PRESENT": (
                    "The requested Galileo satellite PRN/SVID was not among the authenticated satellites in this evidence record."
                ),
                "OBSERVATION_STALE": (
                    f"Time difference between OSNMA observation and claimed_at exceeds {max_age_hours:g} hour(s)."
                ),
                "OBSERVATION_TIME_UNKNOWN": (
                    "OSNMA evidence record has no documented observation timestamp (observed_at is null)."
                ),
                "NO_EVIDENCE": "No gnss_osnma_auth evidence records were available.",
                "NOT_AVAILABLE_AT_DECISION_TIME": (
                    "OSNMA evidence was observed or became available after decision_time."
                ),
                "AVAILABILITY_TIME_UNKNOWN": (
                    "OSNMA evidence lacks a documented available_at timestamp for decision-time verification."
                ),
            },
            known_limitations=[
                "Galileo OSNMA authenticates broadcast navigation-message bits (ephemeris/clock/iono/health) ONLY; it never proves accurate user positioning, trustworthy receiver hardware/firmware, or protection against all spoofing techniques (such as signal replay/meaconing).",
                "Offline verification of recorded SBF files does not verify real-time loose time synchronisation against Galileo System Time (GST).",
            ],
        )

    @property
    def spec(self) -> PolicySpec:
        return self._spec

    def validate_claim(self, claim: ClaimRequest) -> None:
        svid = claim.attributes.get("svid")
        if svid is not None:
            if isinstance(svid, bool) or not isinstance(svid, int) or not (1 <= svid <= 36):
                raise ClaimValidationError(
                    "Optional attributes.svid must be a Galileo PRN/SVID integer between 1 and 36.",
                    field_path="attributes.svid",
                )

    def is_evidence_relevant(self, claim: ClaimRequest, evidence: Evidence) -> bool:
        return evidence.kind == "gnss_osnma_auth"

    def evaluate_evidence(
        self,
        claim: ClaimRequest,
        evidence: Evidence,
        context: EvidenceContext,
    ) -> EvidenceFinding:
        age_hours = context.temporal.age_hours

        # Explicitly reject positioning-accuracy claims: nav-message auth is unsuitable!
        if claim.claim_type == "gnss_position_accurate":
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="evidence_unsuitable",
                age_hours=age_hours,
                reasons=["NAV_AUTH_INSUFFICIENT_FOR_POSITIONING"],
            )

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

        attrs = evidence.attributes
        outcome = str(attrs.get("osnma_outcome", "")).lower()
        locally_verified = attrs.get("locally_verified") is True
        method = str(attrs.get("verification_method", "")).lower()

        if outcome == "failed":
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="authentication_failed",
                age_hours=age_hours,
                reasons=["AUTHENTICATION_FAILED"],
            )

        if outcome == "pending":
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="authentication_pending",
                age_hours=age_hours,
                reasons=["OSNMA_AUTHENTICATION_PENDING"],
            )

        if outcome == "unavailable":
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="authentication_unavailable",
                age_hours=age_hours,
                reasons=["OSNMA_AUTHENTICATION_UNAVAILABLE"],
            )

        # Externally reported authentication MUST NOT be equated with local cryptographic verification
        if method == "externally_reported" or (
            outcome == "authenticated" and not locally_verified
        ):
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="authentication_unknown",
                age_hours=age_hours,
                reasons=["OSNMA_EXTERNALLY_REPORTED_UNVERIFIED"],
            )

        if (
            evidence.authentication == "verified"
            and locally_verified
            and method == "local_osnma_cryptographic"
            and outcome == "authenticated"
        ):
            req_svid = claim.attributes.get("svid")
            auth_svids = attrs.get("authenticated_svids")
            if req_svid is not None and isinstance(auth_svids, list):
                if req_svid not in auth_svids:
                    return EvidenceFinding(
                        evidence_id=evidence.id,
                        status="insufficient_evidence",
                        age_hours=age_hours,
                        reasons=["SVID_NOT_PRESENT"],
                    )
            return EvidenceFinding(
                evidence_id=evidence.id,
                status="authenticated",
                age_hours=age_hours,
                reasons=["OSNMA_LOCALLY_VERIFIED"],
            )

        return EvidenceFinding(
            evidence_id=evidence.id,
            status="authentication_unknown",
            age_hours=age_hours,
            reasons=["OSNMA_AUTHENTICATION_UNKNOWN"],
        )

    def aggregate(
        self,
        claim: ClaimRequest,
        findings: list[EvidenceFinding],
        evidence_items: list[Evidence],
        independence: IndependenceSummary,
        context: AssessmentContext,
    ) -> PolicyDecision:
        if claim.claim_type == "gnss_position_accurate":
            return PolicyDecision(
                status="evidence_unsuitable",
                reasons=["NAV_AUTH_INSUFFICIENT_FOR_POSITIONING"],
                limitations=[
                    "Galileo OSNMA authenticates broadcast satellite navigation data bits (ephemeris/clock) ONLY.",
                    "Navigation-message authentication does NOT establish user positioning accuracy, pseudorange validity, receiver trustworthiness, or protection against meaconing/relay spoofing.",
                ],
            )

        # Failed authentication takes strict precedence over all positive findings
        has_failed = any(
            f.status == "authentication_failed" or "AUTHENTICATION_FAILED" in f.reasons
            for f in findings
        )
        if has_failed:
            overall_status = "authentication_failed"
        elif any(f.status == "authenticated" for f in findings):
            overall_status = "authenticated"
        elif any(f.status == "authentication_pending" for f in findings):
            overall_status = "authentication_pending"
        elif any(f.status == "authentication_unavailable" for f in findings):
            overall_status = "authentication_unavailable"
        elif any(f.status == "authentication_unknown" for f in findings):
            overall_status = "authentication_unknown"
        else:
            overall_status = "insufficient_evidence"

        primary_reasons: list[str] = []
        secondary_reasons: list[str] = []
        for f in findings:
            is_primary = f.status == overall_status or (
                overall_status == "authentication_failed"
                and "AUTHENTICATION_FAILED" in f.reasons
            )
            target = primary_reasons if is_primary else secondary_reasons
            target.extend(f.reasons)

        ordered_reasons: list[str] = []
        for r in primary_reasons + secondary_reasons:
            if r not in ordered_reasons:
                ordered_reasons.append(r)

        limitations = list(self._spec.known_limitations)
        if overall_status == "authenticated":
            limitations.insert(
                0,
                "Authenticated scope: Galileo E1-B I/NAV ADKD=0 navigation data (Word Types 1-5: ephemeris, clock, iono/BGD, health/DVS) verified locally against GSC Merkle Root and ECDSA P-256 public key.",
            )
        elif overall_status == "authentication_failed":
            limitations.insert(
                0,
                "Cryptographic verification failure indicates tampered, corrupted, or mismatched navigation/OSNMA data and must not be trusted.",
            )
        elif overall_status == "authentication_unknown":
            limitations.insert(
                0,
                "Externally reported or unverified authentication claims are NOT treated as locally cryptographically verified.",
            )

        return PolicyDecision(
            status=overall_status,
            reasons=ordered_reasons,
            limitations=limitations,
        )
