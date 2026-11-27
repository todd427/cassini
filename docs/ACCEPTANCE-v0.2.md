# EIP Acceptance Audit — v0.2.0

Audited against the EIP v0.2 architectural requirements, `CONTRACT.md` (v0.2), and `cassini-briefs/PRD.md` (v0.1 baseline) on **27 November 2026** via automated test execution.

---

## 1. Acceptance Criteria Checklist

| # | Criterion | Status | Verification Evidence |
|---|---|---|---|
| 1 | All existing `v0.1.0` tests continue to pass | **PASS** | `tests/core/test_assessment_api.py` (22 passed) + `tests/data/test_data_integrity.py` (3 passed) |
| 2 | Existing historical flood assessment outcomes remain unchanged | **PASS** | All 4 `EMSR718` Lough Funshinagh replay claims & all 7 synthetic fixtures match exact v0.1 outcomes/reasons |
| 3 | Generic engine contains no flood-road-specific assessment rules | **PASS** | Verified by `test_generic_core_engine_contains_no_flood_road_rules` scanning all 8 generic `core/` modules |
| 4 | New policy can be registered without modifying generic engine | **PASS** | `ColdChainTestPolicy` (`tests/fixtures/cold_chain_policy.py`) registered and invoked via API with zero edits to `core/` or `api/` |
| 5 | Unsupported claim types handled explicitly | **PASS** | Returns structured HTTP `422` (`unsupported_claim_type` + `supported_claim_types`); verified in `test_discovery_endpoints_and_unsupported_claim_type` |
| 6 | Retrospective and decision-time assessments correctly distinguished | **PASS** | Verified in `test_decision_time_blocks_future_observations_and_post_decision_publication` & `test_cems_connector_protocol_and_real_emsr718_decision_time_uncertainty` |
| 7 | Future evidence cannot leak into decision-time assessments | **PASS** | Both `observed_at > decision_time` and `available_at > decision_time` are excluded with `NOT_AVAILABLE_AT_DECISION_TIME` |
| 8 | Unknown evidence availability explicitly represented | **PASS** | `available_at=None` in `decision_time` mode returns `AVAILABILITY_TIME_UNKNOWN`, recorded in `temporal_context.unknown_availability_ids` and `limitations` |
| 9 | Shared upstream sources cannot masquerade as independent corroboration | **PASS** | Connected-component lineage analysis collapses shared `original_source` / `upstream_datasets` / `derived_from` / `shared_dependencies` into `correlated_groups` (`shared_dependencies_detected`); missing provenance stays `"unknown"` |
| 10 | Existing dashboard remains operational | **PASS** | `cd dashboard && npm run build` (0 errors) + `npx playwright test` (3 passed against live v0.2 API) |
| 11 | Offline operation preserved | **PASS** | Zero external network requests during default Evidence Inspector load and live assessment |
| 12 | Existing `start.sh` launcher continues to work | **PASS** | Verified startup, `/health`, Playwright E2E suite, and clean `SIGTERM` shutdown with zero leftover listeners on `:8000`/`:5173` |

---

## 2. Genuine vs Synthetic Data Status

- **Genuine Copernicus Evidence (`synthetic: false`):** `sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip` (SHA-256 `2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947`), normalised into `sample_data/evidence.json` with structured `provenance` (`original_source: "COSMO-SkyMed"`, `publishing_organisation: "Copernicus EMS Rapid Mapping"`) and honest `available_at: null` (raw ZIP lacks exact UTC publication time). `authentication` remains `"unknown"`.
- **Synthetic Data (`synthetic: true`):** `sample_data/example_claims.json`, `sample_data/fixtures/*.json`, dashboard Mock Mode fixtures, and `ColdChainTestPolicy` test telemetry.

---

## 3. Remaining Limitations & External Blockers

- **Additional connectors not implemented in v0.2 (by design):** Copernicus STAC discovery, Galileo OSNMA authentication, terrestrial sensors, and structured human-report connectors remain prepared via `connectors/base.py` for subsequent phases.
- **Dashboard v0.2 UI controls not added (by design):** Evidence Inspector remains compatible with Contract v0.1/v0.2 without redesign; exposing `decision_time` selection and policy discovery visually in the UI is deferred to a later UI phase.
- **Non-technical hackathon items:** Pitch deck/script, demo recording, and organiser rule confirmations remain human tasks outside code scope.
