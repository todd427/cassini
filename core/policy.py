"""Assessment policy interface (Protocol) and PolicyRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from core.models import (
    AssessmentMode,
    ClaimRequest,
    Evidence,
    EvidenceFinding,
    IndependenceSummary,
    PolicySpec,
)
from core.temporal import TemporalEvaluation


class PolicyError(Exception):
    """Base error for policy dispatch and validation failures."""


class UnsupportedClaimTypeError(PolicyError):
    """Raised when no registered policy supports the requested claim_type."""

    def __init__(self, claim_type: str, supported_claim_types: list[str]) -> None:
        self.claim_type = claim_type
        self.supported_claim_types = supported_claim_types
        super().__init__(
            f"Unsupported claim_type '{claim_type}'. Supported claim types: {supported_claim_types}"
        )


class UnknownPolicyError(PolicyError):
    """Raised when an explicitly requested policy_id is not registered or mismatched."""

    def __init__(self, policy_id: str, registered_policy_ids: list[str]) -> None:
        self.policy_id = policy_id
        self.registered_policy_ids = registered_policy_ids
        super().__init__(
            f"Unknown or incompatible policy_id '{policy_id}'. Registered policies: {registered_policy_ids}"
        )


class ClaimValidationError(PolicyError):
    """Raised when a claim fails domain-specific policy validation."""

    def __init__(self, message: str, field_path: str | None = None) -> None:
        self.message = message
        self.field_path = field_path
        super().__init__(message)


@dataclass(frozen=True)
class EvidenceContext:
    """Generic per-evidence context passed by the engine into a policy."""

    temporal: TemporalEvaluation
    assessment_mode: AssessmentMode
    decision_time: datetime | None


@dataclass(frozen=True)
class AssessmentContext:
    """Generic claim-level context passed by the engine into policy aggregation."""

    assessment_mode: AssessmentMode
    decision_time: datetime | None
    assessed_at: datetime | None


@dataclass(frozen=True)
class PolicyDecision:
    """Domain policy aggregation output returned to the generic engine."""

    status: str
    reasons: list[str]
    limitations: list[str] = field(default_factory=list)


@runtime_checkable
class AssessmentPolicy(Protocol):
    """Compositional interface implemented by each domain assessment policy."""

    @property
    def spec(self) -> PolicySpec:
        """Declarative metadata, rules summary, thresholds, and limitations."""
        ...

    def validate_claim(self, claim: ClaimRequest) -> None:
        """Validate domain-specific claim fields; raise ClaimValidationError if invalid."""
        ...

    def is_evidence_relevant(self, claim: ClaimRequest, evidence: Evidence) -> bool:
        """Return True if an evidence record is relevant to this policy and claim."""
        ...

    def evaluate_evidence(
        self,
        claim: ClaimRequest,
        evidence: Evidence,
        context: EvidenceContext,
    ) -> EvidenceFinding:
        """Evaluate one temporally and authentication-eligible evidence item."""
        ...

    def aggregate(
        self,
        claim: ClaimRequest,
        findings: list[EvidenceFinding],
        evidence_items: list[Evidence],
        independence: IndependenceSummary,
        context: AssessmentContext,
    ) -> PolicyDecision:
        """Aggregate per-evidence findings into a domain outcome, reasons, and limitations."""
        ...


class PolicyRegistry:
    """Registry mapping claim types and policy IDs to AssessmentPolicy instances."""

    def __init__(self) -> None:
        self._by_id: dict[str, AssessmentPolicy] = {}
        self._by_claim_type: dict[str, AssessmentPolicy] = {}

    def register(self, policy: AssessmentPolicy) -> None:
        spec = policy.spec
        if spec.policy_id in self._by_id:
            raise ValueError(f"Policy '{spec.policy_id}' is already registered.")
        for claim_type in spec.supported_claim_types:
            if claim_type in self._by_claim_type:
                existing = self._by_claim_type[claim_type].spec.policy_id
                raise ValueError(
                    f"Claim type '{claim_type}' is already registered to policy '{existing}'."
                )
        self._by_id[spec.policy_id] = policy
        for claim_type in spec.supported_claim_types:
            self._by_claim_type[claim_type] = policy

    def get_by_id(self, policy_id: str) -> AssessmentPolicy:
        if policy_id not in self._by_id:
            raise UnknownPolicyError(policy_id, sorted(self._by_id.keys()))
        return self._by_id[policy_id]

    def resolve(
        self,
        claim_type: str,
        policy_id: str | None = None,
    ) -> AssessmentPolicy:
        if policy_id is not None:
            policy = self.get_by_id(policy_id)
            if claim_type not in policy.spec.supported_claim_types:
                raise UnsupportedClaimTypeError(
                    claim_type, list(policy.spec.supported_claim_types)
                )
            return policy
        if claim_type not in self._by_claim_type:
            raise UnsupportedClaimTypeError(claim_type, self.supported_claim_types())
        return self._by_claim_type[claim_type]

    def list_specs(self) -> list[PolicySpec]:
        return [policy.spec for policy in self._by_id.values()]

    def supported_claim_types(self) -> list[str]:
        return sorted(self._by_claim_type.keys())

    def supported_evidence_kinds(self) -> list[str]:
        kinds: set[str] = set()
        for policy in self._by_id.values():
            kinds.update(policy.spec.required_evidence_kinds)
            kinds.update(policy.spec.optional_evidence_kinds)
        return sorted(kinds)

    def registered_policy_ids(self) -> list[str]:
        return sorted(self._by_id.keys())
