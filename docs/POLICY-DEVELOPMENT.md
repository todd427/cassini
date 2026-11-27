# Assessment Policy Development Guide (EIP v0.2)

This guide explains how an external developer implements, registers, exposes, and tests a new domain assessment policy in EIP **without modifying `core/` or `api/`**.

---

## 1. Policy Interface Contract

Every policy implements the structural `AssessmentPolicy` protocol defined in `core/policy.py` (no base-class inheritance required):

```python
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
```

A policy provides one property and four methods:

1. **`spec -> PolicySpec`**: Declarative metadata surfaced automatically by `GET /v1/policies` and `GET /v1/capabilities`:
   - `policy_id` (unique stable identifier, e.g. `"cold-chain"`)
   - `policy_version` (immutable rule version, e.g. `"cold-chain-0.1"`)
   - `name`, `description`
   - `supported_claim_types` (e.g. `["cold_chain_within_limits"]`)
   - `required_evidence_kinds`, `optional_evidence_kinds`
   - `evidence_relevance_criteria`, `assessment_rules_summary`
   - `thresholds` (explicit machine-readable parameters)
   - `possible_outcomes` (avoid truth-oracle or "safe" labels)
   - `reason_explanations` (human-readable text per reason code)
   - `known_limitations`
2. **`validate_claim(claim: ClaimRequest) -> None`**:
   - Validate domain-specific requirements (e.g., required geometry type for spatial policies, or required `claim.attributes` keys for non-geographical policies).
   - Raise `ClaimValidationError(message, field_path=...)` for invalid claims; the API translates this automatically to HTTP `422`.
3. **`is_evidence_relevant(claim: ClaimRequest, evidence: Evidence) -> bool`**:
   - Filter stored evidence records (e.g., `evidence.kind == "temperature_telemetry"`).
4. **`evaluate_evidence(claim, evidence, context: EvidenceContext) -> EvidenceFinding`**:
   - Invoked **only** for evidence that passed generic authentication (`authentication != "failed"`) and generic temporal eligibility (retrospective vs decision-time).
   - Receives pre-computed `context.temporal.age_hours` and `context.temporal.signed_delta_hours`.
   - Returns an `EvidenceFinding(evidence_id, status, age_hours, reasons)`.
5. **`aggregate(claim, findings, evidence_items, independence, context) -> PolicyDecision`**:
   - Combines per-evidence findings (including any generic engine exclusions like `AUTHENTICATION_FAILED`, `NOT_AVAILABLE_AT_DECISION_TIME`, or `AVAILABILITY_TIME_UNKNOWN`) into an overall `PolicyDecision(status, reasons, limitations)`.
   - Receives `independence: IndependenceSummary` so policies never overcount correlated derived sources.

---

## 2. Step-by-Step Walkthrough (Non-Geographical Example)

See the working test-only reference implementation in `tests/fixtures/cold_chain_policy.py`:

### Step 1 — Create Your Policy Module
Define a class implementing `spec`, `validate_claim`, `is_evidence_relevant`, `evaluate_evidence`, and `aggregate`.
- For non-geographical domains, leave `geometry=None` on both `ClaimRequest` and `Evidence`, and read structured measurements from `evidence.attributes` and claim thresholds from `claim.attributes`.
- For spatial domains, reuse `core.spatial.to_shapely` and `core.spatial.evaluate_spatial_relation` (see `policies/flood_road.py` as reference).

### Step 2 — Register Without Modifying `core/`
Register your policy in a `PolicyRegistry`:

```python
from api.main import create_app
from core.engine import AssessmentEngine
from core.store import FileEvidenceStore
from policies import build_default_registry
from my_org.policies.cold_chain import ColdChainPolicy

registry = build_default_registry()
registry.register(ColdChainPolicy(max_age_hours=6.0))

# Option A: Embed directly in Python
engine = AssessmentEngine(registry)

# Option B: Expose via REST API (automatically updates /v1/capabilities and /v1/policies)
app = create_app(registry=registry, store=FileEvidenceStore("path/to/evidence.json"))
```

### Step 3 — Verify Discovery & Dispatch
- `GET /v1/capabilities` will list your new `claim_type`, `evidence_kind`, and `policy_id`.
- `GET /v1/policies` will expose your complete `PolicySpec`.
- `POST /v1/assess` with `"claim_type": "cold_chain_within_limits"` routes directly to your policy.

### Step 4 — Required Policy Test Checklist
Every new policy should include automated tests covering:
1. Valid conflict and non-conflict outcomes with deterministic replay.
2. Stale and missing-timestamp (`observed_at=None`) evidence.
3. `decision_time` mode blocking future observations (`observed_at > decision_time`), post-decision publications (`available_at > decision_time`), and unknown availability (`available_at=None`).
4. Failed authentication exclusion (`AUTHENTICATION_FAILED`).
5. Shared upstream dependency detection (`independence.status == "shared_dependencies_detected"`).
6. Invalid claim attributes/geometry returning `ClaimValidationError` (HTTP `422`).
7. Explicit non-oracle limitations and `synthetic` flag propagation.
