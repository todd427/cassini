"""Domain-independent temporal integrity evaluation (retrospective vs decision-time).

Explicitly distinguishes six timestamps:
- observed_at   (Evidence): when the physical observation/measurement occurred.
- available_at  (Evidence): when the evidence was published / became available.
- retrieved_at  (Evidence): when EIP ingested/retrieved the artifact.
- claimed_at    (Claim):    when the claimed state pertains to.
- decision_time (Claim):    when a decision was made (required in decision_time mode).
- assessed_at   (Run):      when EIP executed the assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.models import AssessmentMode, Evidence

AvailabilityStatus = Literal[
    "available_retrospective",
    "available_at_decision",
    "future_observation",
    "not_available_at_decision",
    "availability_unknown",
]


@dataclass(frozen=True)
class TemporalEvaluation:
    """Generic temporal evaluation for one evidence record against a claim."""

    age_hours: float | None
    signed_delta_hours: float | None
    availability_status: AvailabilityStatus
    eligible: bool
    exclusion_reason: str | None = None


def evaluate_temporal_eligibility(
    evidence: Evidence,
    claimed_at: datetime,
    assessment_mode: AssessmentMode,
    decision_time: datetime | None = None,
) -> TemporalEvaluation:
    """Compute temporal offset and check retrospective vs decision-time eligibility."""
    age_hours: float | None = None
    signed_delta_hours: float | None = None
    if evidence.observed_at is not None:
        raw_delta_sec = (claimed_at - evidence.observed_at).total_seconds()
        signed_delta_hours = round(raw_delta_sec / 3600.0, 6)
        age_hours = round(abs(raw_delta_sec) / 3600.0, 6)

    if assessment_mode == "retrospective":
        return TemporalEvaluation(
            age_hours=age_hours,
            signed_delta_hours=signed_delta_hours,
            availability_status="available_retrospective",
            eligible=True,
            exclusion_reason=None,
        )

    # decision_time mode: strictly prevent future observations or post-decision publications
    if decision_time is None:
        raise ValueError("decision_time is required when assessment_mode is 'decision_time'.")

    if evidence.observed_at is not None and evidence.observed_at > decision_time:
        return TemporalEvaluation(
            age_hours=age_hours,
            signed_delta_hours=signed_delta_hours,
            availability_status="future_observation",
            eligible=False,
            exclusion_reason="NOT_AVAILABLE_AT_DECISION_TIME",
        )

    if evidence.available_at is None:
        return TemporalEvaluation(
            age_hours=age_hours,
            signed_delta_hours=signed_delta_hours,
            availability_status="availability_unknown",
            eligible=False,
            exclusion_reason="AVAILABILITY_TIME_UNKNOWN",
        )

    if evidence.available_at > decision_time:
        return TemporalEvaluation(
            age_hours=age_hours,
            signed_delta_hours=signed_delta_hours,
            availability_status="not_available_at_decision",
            eligible=False,
            exclusion_reason="NOT_AVAILABLE_AT_DECISION_TIME",
        )

    return TemporalEvaluation(
        age_hours=age_hours,
        signed_delta_hours=signed_delta_hours,
        availability_status="available_at_decision",
        eligible=True,
        exclusion_reason=None,
    )
