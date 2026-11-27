# EIP Python Client SDK (`eip_sdk`)

Minimal, dependency-free Python client SDK and CLI for integrating the **Evidence Integrity Platform (EIP)** into external enterprise applications over the public REST API.

## Design Guarantees
- **REST-only boundary:** `eip_sdk` communicates exclusively via HTTP/JSON against the EIP REST API and never imports internal `core`, `policies`, `connectors`, or `api` modules.
- **No silent mock fallback:** If the EIP API is unreachable or times out, `EIPClient` raises `EIPConnectionError` / `EIPTimeoutError`. It never fabricates or substitutes synthetic evidence.
- **Zero mandatory runtime dependencies:** Built on Python 3.12 standard library (`urllib.request`, `dataclasses`, `json`, `argparse`).
- **Forward-compatible policy discovery:** Newly registered server policies and claim types are discovered via `client.capabilities()` and consumed via `ClaimInput.custom(...)` with zero SDK changes.

## Minimal Example

```python
from eip_sdk import ClaimInput, EIPClient

client = EIPClient("http://127.0.0.1:8000", timeout=5.0)
caps = client.check_compatibility()
print("Supported claims:", caps.supported_claim_types)

claim = ClaimInput.road_passable(
    claim_id="demo-road-1",
    coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
    claimed_at="2024-04-15T08:00:00Z",
    source_label="Synthetic replay road claim",
    synthetic=True,
)
result = client.assess(claim)
print(result.status, result.reasons)
```

## Core Methods (`EIPClient`)

| Method | Endpoint | Purpose |
|---|---|---|
| `health()` | `GET /health` | Service liveness & base contract version |
| `check_compatibility()` | `GET /health` + `GET /v1/capabilities` | Verify contract compatibility before submitting claims |
| `capabilities()` | `GET /v1/capabilities` | Discover claim types, evidence kinds, policies, and temporal modes |
| `list_policies()` / `get_policy(id)` | `GET /v1/policies` | Inspect declarative policy rules, thresholds, and limitations |
| `list_evidence(kind=...)` | `GET /v1/evidence` | Retrieve evidence records and provenance metadata |
| `assess(claim)` | `POST /v1/assess` | Run deterministic retrospective or decision-time assessment |
| `assess_decision_time(claim, ts)` | `POST /v1/assess` | Shorthand for strict `decision_time` audit |
| `assess_with_graph(claim)` | `POST /v1/assess/graph` | Retrieve assessment, evidence, and API-derived provenance graph |
| `build_report(claim)` / `export_report(claim, path)` | `POST /v1/assess/graph` | Assemble and write an auditable machine-readable JSON report |

## Predictable Error Classes

- `EIPConnectionError` / `EIPTimeoutError` — API unreachable or request timed out.
- `EIPCompatibilityError` — Unexpected server contract version or unhealthy status.
- `EIPUnsupportedClaimError` — Server does not support `claim_type` (includes `supported_claim_types`).
- `EIPUnknownPolicyError` — Explicit `policy_id` is not registered (includes `registered_policy_ids`).
- `EIPValidationError` — HTTP `422` payload or policy validation error (e.g., naive timestamp or missing required attributes).
- `EIPAPIError` — Any other non-2xx HTTP error.

## Command-Line Interface (`eip-cli` / `python -m eip_sdk`)

```bash
python -m eip_sdk health
python -m eip_sdk capabilities
python -m eip_sdk policies
python -m eip_sdk evidence --summary
python -m eip_sdk assess --claim-file claim.json --graph --report-out out/report.json
```

Exit codes: `0` success, `1` local input/JSON error, `2` connection/timeout error, `3` validation/unsupported claim/policy error, `4` other API error.
