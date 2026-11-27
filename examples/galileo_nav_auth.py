"""Galileo OSNMA navigation-message authentication example using the same EIPClient.

Demonstrates:
1. Assessing genuine locally verified Galileo E27 I/NAV navigation data.
2. Submitting a user positioning-accuracy claim (`gnss_position_accurate`) to show
   explicit scope rejection (`evidence_unsuitable`).
"""

from __future__ import annotations

import json
import os

from eip_sdk import ClaimInput, EIPClient


def main() -> None:
    base_url = os.environ.get("EIP_API_URL", "http://127.0.0.1:8000")
    client = EIPClient(base_url, timeout=5.0)

    nav_claim = ClaimInput.galileo_nav_auth(
        claim_id="galileo-demo-e27",
        claimed_at="2023-08-27T20:10:00Z",
        source_label="Synthetic navigation auth claim against genuine 2023 SBF recording",
        svid=27,
        synthetic=True,
    )
    position_claim = ClaimInput.custom(
        claim_id="galileo-demo-position-scope",
        claim_type="gnss_position_accurate",
        claimed_at="2023-08-27T20:10:00Z",
        source_label="Synthetic positioning-accuracy claim (scope boundary demonstration)",
        synthetic=True,
    )

    nav_res = client.assess(nav_claim)
    pos_res = client.assess(position_claim)

    output = {
        "example": "galileo_nav_auth",
        "api_base_url": base_url,
        "scenarios": [
            {
                "claim_id": nav_res.claim_id,
                "policy_version": nav_res.policy_version,
                "status": nav_res.status,
                "reasons": nav_res.reasons,
                "limitations": nav_res.limitations,
            },
            {
                "claim_id": pos_res.claim_id,
                "policy_version": pos_res.policy_version,
                "status": pos_res.status,
                "reasons": pos_res.reasons,
                "limitations": pos_res.limitations,
            },
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
