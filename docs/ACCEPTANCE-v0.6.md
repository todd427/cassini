# EIP v0.6.0 Acceptance Audit

**Release:** `v0.6.0` (Enterprise Developer Integration & Reusable Client SDK)  
**Baseline:** `v0.5.0` (`2f79435`)  
**Audit Date:** 2026-11-27  
**Workspace:** `/home/todd/dev/cassini` (`main`) · Python venv: `/home/todd/dev/venvs/cassini`

---

## 1. Acceptance Criteria Verification

| Acceptance Criterion | Status | Verified Evidence |
|---|---|---|
| SDK communicates only through the public REST API | **PASS** | AST import check (`test_sdk_and_examples_never_import_internal_eip_modules`) confirms zero imports of `core`, `policies`, `connectors`, or `api` anywhere in `eip_sdk/` or `examples/`. |
| Environmental and Galileo assessments work through the same SDK | **PASS** | `test_sdk_discovery_provenance_environmental_galileo_decision_time_and_graph` verifies `road_passable` (`potential_conflict`, `no_mapped_overlap`), `gnss_nav_message_authenticated` (`authenticated`), and `gnss_position_accurate` (`evidence_unsuitable`) via a single `EIPClient`. |
| Evidence graphs and provenance are accessible | **PASS** | `client.list_evidence()`, `client.assess_with_graph()`, and `client.export_report()` verified against live `uvicorn` HTTP server (`3` evidence nodes, `3` independent groups, `>= 6` upstream nodes). |
| Decision-time assessments are supported | **PASS** | `client.assess_decision_time()` verified returning `insufficient_evidence` + `AVAILABILITY_TIME_UNKNOWN` when `available_at` is `null` and `potential_conflict` when `available_at <= decision_time` on cold-chain test server. |
| Unsupported claims and unavailable services generate explicit errors | **PASS** | `test_sdk_explicit_errors_without_silent_mock_fallback` verifies `EIPUnsupportedClaimError`, `EIPUnknownPolicyError`, `EIPValidationError`, `EIPConnectionError` (closed port, zero silent mock fallback), and `EIPTimeoutError`. |
| A newly registered policy can be consumed without modifying the SDK | **PASS** | `test_unchanged_sdk_discovers_and_consumes_newly_registered_policy` registers `ColdChainTestPolicy` (`cold_chain_within_limits` / `temperature_telemetry`) on a live server and consumes it via unmodified `EIPClient` + `ClaimInput.custom()`. |
| Developer examples are reproducible | **PASS** | All 5 Python examples (`minimal_quickstart.py`, `environmental_assessment.py`, `galileo_nav_auth.py`, `decision_time_audit.py`, `provenance_graph_inspection.py`) and `examples/curl_examples.sh` executed cleanly against live local EIP API (`exit 0`). |
| Command-line client produces valid machine-readable reports | **PASS** | `eip-cli` (`python -m eip_sdk`) verified for `health --compact`, `capabilities`, `assess --graph --report-out`, and deterministic exit code `2` + JSON `connection_error` on unreachable server. |
| External enterprise workflow CLI consumes EIP exclusively via SDK | **PASS** | `examples/enterprise_insurance_workflow.py` emits auditable JSON dossier explicitly marked `hypothetical_workflow: true`, `synthetic_claim: true`, `automated_final_decision: false`, `human_signoff_required: true`. |
| Existing dashboard, offline operation, and `./start.sh` remain operational | **PASS** | `cd dashboard && npm run build` (`0` errors); all `7` Playwright E2E tests pass against live `./start.sh`; `SIGTERM` exits cleanly (`CLEAN_SHUTDOWN_OK`). |
| Zero unnecessary changes to `core/` | **PASS** | `git diff --stat core/` returned `0` modified lines. |

---

## 2. Verified Test & Build Results

1. **Python Test Suite (`/home/todd/dev/venvs/cassini/bin/pytest -v tests/`):**
   - Result: **`52 passed` in 5.34s** (47 prior regression tests + 5 new v0.6 SDK/CLI/extensibility/enterprise workflow tests in `tests/sdk/test_v06_sdk_and_integration.py`; 1 benign upstream `StarletteDeprecationWarning`).
2. **Dashboard Production Build (`cd dashboard && npm run build`):**
   - Result: **`tsc -b && vite build` succeeded with 0 errors** (2.83s).
3. **Playwright E2E Regression Suite (`cd dashboard && npx playwright test` against live `./start.sh`):**
   - Result: **`7 passed` in 9.7s**.
4. **Live Quickstart & CLI Verification against `./start.sh`:**
   - `examples/minimal_quickstart.py`: `Connected to EIP API: ['flood-road', 'galileo-osnma']`, `Status: potential_conflict (policy=flood-road-0.1)`, `Reasons: FLOOD_EXTENT_INTERSECTS, CONTEXTUAL_WATER_LEVEL_ELEVATED, CONTEXTUAL_RAINFALL_OBSERVED`.
   - `eip-cli health --compact`: valid single-line JSON confirming contract `0.1` / `0.2`, 3 claim types, 4 evidence kinds, 2 policies.
   - `examples/enterprise_insurance_workflow.py --case-id CASE-RF-2024-001`: emitted structured human-review JSON dossier (`status: potential_conflict`, `automated_final_decision: false`, `input_fingerprint: 274b7a44...`).
   - `./examples/curl_examples.sh`: **`CURL_EXIT_CODE=0`** across all 7 REST calls.
   - `./start.sh` shutdown via `SIGTERM`: **`CLEAN_SHUTDOWN_OK`** (zero lingering listeners on `:8000` or `:5173`).

---

## 3. API & Core Engine Delta

- **Generic engine (`core/`):** **0 changes** (`git diff --stat core/` empty).
- **API wire contract (`api/main.py`):** **No breaking or additive schema changes**; only FastAPI metadata `version` bumped from `0.5.0` to `0.6.0`. All v0.1–v0.5 endpoints remain backward-compatible.
- **Packaging (`pyproject.toml`):** Added `eip_sdk*` package inclusion and `eip-cli = "eip_sdk.cli:main"` console entry point; version bumped to `0.6.0`.

---

## 4. Remaining Limitations & Production Readiness Gaps

1. All 4 archived genuine evidence records retain `available_at: null`, so live `decision_time` audits honestly return `insufficient_evidence` (`AVAILABILITY_TIME_UNKNOWN`).
2. `eip_sdk` currently provides synchronous HTTP transport over `urllib.request` with no built-in retry/backoff or OAuth/mTLS token manager (documented for future production hardening).
3. Production enterprise requirements—API authentication/authorisation, tenant isolation, rate limiting, persistent tamper-evident audit logging, GDPR retention/deletion, automated licence enforcement, connector SLA monitoring, formal policy change governance, horizontal scaling/PostGIS persistence, third-party security audit, and domain scientific validation—remain **explicitly out of scope** for v0.6.0 and are documented in [docs/PRODUCTION-READINESS.md](PRODUCTION-READINESS.md).
