"""Environmental claim assessment example using EIPClient.

Demonstrates both:
1. A synthetic road claim intersecting genuine Copernicus EMSR718 flood extent
   with independent GSI hydrometric and Met Eireann rainfall context.
2. A synthetic road claim inside documented AOI02 coverage with no mapped overlap
   (explicitly NOT proof of safety or passability).
"""

from __future__ import annotations

import json
import os

from eip_sdk import ClaimInput, EIPClient


def main() -> None:
    base_url = os.environ.get("EIP_API_URL", "http://127.0.0.1:8000")
    client = EIPClient(base_url, timeout=5.0)

    intersecting_claim = ClaimInput.road_passable(
        claim_id="env-demo-ballagh-east",
        coordinates=[[-8.1165, 53.4916], [-8.1113, 53.4916], [-8.1075, 53.4916]],
        claimed_at="2024-04-15T08:00:00Z",
        source_label="Synthetic historical replay road claim (Lough Funshinagh East)",
        synthetic=True,
    )
    covered_clear_claim = ClaimInput.road_passable(
        claim_id="env-demo-rahara-south",
        coordinates=[[-8.175, 53.462], [-8.155, 53.462]],
        claimed_at="2024-04-15T08:00:00Z",
        source_label="Synthetic historical replay road claim (Rahara South, inside AOI02)",
        synthetic=True,
    )

    conflict = client.assess(intersecting_claim)
    no_overlap = client.assess(covered_clear_claim)

    output = {
        "example": "environmental_assessment",
        "api_base_url": base_url,
        "scenarios": [
            {
                "claim_id": conflict.claim_id,
                "status": conflict.status,
                "reasons": conflict.reasons,
                "independent_groups": (
                    conflict.independence.independent_group_count
                    if conflict.independence
                    else None
                ),
                "evidence_checked": len(conflict.evidence_ids),
                "limitations": conflict.limitations,
            },
            {
                "claim_id": no_overlap.claim_id,
                "status": no_overlap.status,
                "reasons": no_overlap.reasons,
                "independent_groups": (
                    no_overlap.independence.independent_group_count
                    if no_overlap.independence
                    else None
                ),
                "evidence_checked": len(no_overlap.evidence_ids),
                "limitations": no_overlap.limitations,
            },
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
