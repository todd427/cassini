"""Minimal EIP enterprise integration example (~15 lines of integration code).

Run against a running local EIP API (`./start.sh` or `uvicorn api.main:app`):
    ~/dev/venvs/cassini/bin/python examples/minimal_quickstart.py
"""

from __future__ import annotations

import os

from eip_sdk import ClaimInput, EIPClient

BASE_URL = os.environ.get("EIP_API_URL", "http://127.0.0.1:8000")

client = EIPClient(BASE_URL, timeout=5.0)
caps = client.check_compatibility()
print("Connected to EIP API:", caps.registered_policy_ids)

claim = ClaimInput.road_passable(
    claim_id="quickstart-ballagh-east",
    coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
    claimed_at="2024-04-15T08:00:00Z",
    source_label="Synthetic quickstart road claim (Lough Funshinagh East)",
    synthetic=True,
)
result = client.assess(claim)
print(f"Status:  {result.status} (policy={result.policy_version})")
print(f"Reasons: {', '.join(result.reasons)}")
print(f"Caution: {result.limitations[0]}")
