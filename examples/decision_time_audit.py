"""Decision-time evidence auditing example using EIPClient.

Compares retrospective replay against strict decision-time auditing for the same claim.
Because the archived Copernicus EMS, GSI, and Met Eireann datasets honestly record
`available_at: null`, decision-time auditing refuses to assume they were published
before decision_time and returns `insufficient_evidence` (`AVAILABILITY_TIME_UNKNOWN`).
"""

from __future__ import annotations

import json
import os

from eip_sdk import ClaimInput, EIPClient


def main() -> None:
    base_url = os.environ.get("EIP_API_URL", "http://127.0.0.1:8000")
    client = EIPClient(base_url, timeout=5.0)

    claim = ClaimInput.road_passable(
        claim_id="audit-ballagh-20240415",
        coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
        claimed_at="2024-04-15T08:00:00Z",
        source_label="Synthetic road dispatch claim for decision-time audit",
        synthetic=True,
    )

    retro = client.assess(claim)
    dec_time = client.assess_decision_time(claim, decision_time="2024-04-15T08:00:00Z")

    output = {
        "example": "decision_time_audit",
        "api_base_url": base_url,
        "retrospective": {
            "status": retro.status,
            "reasons": retro.reasons,
            "assessment_mode": retro.assessment_mode,
        },
        "decision_time": {
            "decision_time": (
                dec_time.temporal_context.decision_time
                if dec_time.temporal_context
                else None
            ),
            "status": dec_time.status,
            "reasons": dec_time.reasons,
            "unknown_availability_ids": (
                dec_time.temporal_context.unknown_availability_ids
                if dec_time.temporal_context
                else []
            ),
            "limitations": dec_time.limitations,
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
