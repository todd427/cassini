"""Backward-compatible convenience wrapper delegating to AssessmentEngine.

All domain-specific assessment rules live under `policies/`. This shim preserves
direct `from core.assessment import assess_claim` imports from v0.1 tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from core.engine import AssessmentEngine
from core.models import AssessmentResponse, ClaimRequest, Evidence
from core.policy import PolicyRegistry


def assess_claim(
    claim: ClaimRequest,
    evidence_items: Sequence[Evidence],
    registry: PolicyRegistry | None = None,
    assessed_at: datetime | None = None,
) -> AssessmentResponse:
    """Assess a claim via AssessmentEngine using the provided or default policy registry."""
    if registry is None:
        from policies import build_default_registry

        registry = build_default_registry()
    engine = AssessmentEngine(registry)
    return engine.assess(claim, evidence_items, assessed_at=assessed_at)
