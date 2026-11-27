# EIP v0.5.0 Acceptance Audit

**Release:** `v0.5.0` (Unified Evidence Graph, Temporal Visualisation, and Presentation Interface)  
**Baseline:** `v0.4.0` (`124784f`)  
**Audit Date:** 2026-11-27  
**Workspace:** `/home/todd/dev/cassini` (`main`) · Python venv: `/home/todd/dev/venvs/cassini`

---

## 1. Acceptance Criteria Verification

| Area | Requirement | Verification Result | Evidence |
|---|---|---|---|
| **1. Presentation & Technical Modes** | Non-technical viewer understands within 5 seconds: claim, available evidence, what it establishes, what it does NOT establish, why trust/treat with caution; retain Technical Inspection mode | **PASS** | Full-width 5-column Executive Summary Hero (`data-testid="executive-summary"`) auto-populated on live connect; Presentation (default) vs Technical Inspection toggle (`view-presentation` / `view-technical`) exposes raw GeoJSON LineString editor, `input_fingerprint` SHA-256, raw API JSON, and full file provenance. |
| **2. Domain-Independent Evidence Graph** | Interactive graph driven strictly by API provenance/assessment data (`core/graph.py`), supporting claim, evidence, original sources, publishers, shared dependencies, independence groups, missing evidence, freshness/auth, clickable inspector; works for both Environmental and Galileo policies | **PASS** | `core/graph.py` contains zero domain-specific rules/literals (`test_core_graph_contains_no_domain_specific_rules`); `POST /v1/assess/graph` serves backend-derived nodes & edges (`test_assess_graph_environmental_multi_source_and_missing_evidence`, `test_assess_graph_highlights_shared_upstream_dependencies`); clickable `EvidenceGraphView` + Node Inspector verified in E2E Tests 6 & 7. |
| **3. Temporal Evidence Visualisation** | Interactive 6-timestamp timeline showing observed, available, retrieved, claim, decision, and assessment times, policy relevance window, explicit unknown `available_at` distinction, Retrospective vs Decision-Time live controls, demo-policy disclaimer | **PASS** | `EvidenceTimeline` displays shaded policy window with explicit disclaimer (*24-hour flood observation relevance window — demonstration policy, NOT a validated safety threshold*), highlights `3 source(s) with unknown availability time (available_at = null)`, and live-switches to `Decision-Time Audit` returning `Insufficient evidence` + `AVAILABILITY_TIME_UNKNOWN` (E2E Test 6). |
| **4. Enhanced Environmental Mode** | Actual flood extent, documented coverage, local offline baseline water & landmarks (zero external tile fetches), claimed road geometry + interactive 2-click map road selector, GSI & Met Éireann hydrological/regional context strip | **PASS** | `GET /v1/context/lough-funshinagh` serves offline display-only baseline water & 5 locality/gauge landmarks extracted from licensed CEMS `EMSR718`; `EvidenceMap` adds `Draw Road (2 clicks)` interactive selector and Direct vs Indirect telemetry strip (`69.37 mAOD >p99`, `6.1 mm/day · 26.7 mm 5d`). |
| **5. Enhanced Galileo Mode & Tamper Demo** | 4-stage backend-driven cryptographic pipeline, controlled offline 1-bit tampering comparison (explicitly labelled synthetic/tampered), explicit 5-point scope & trust disclosures | **PASS** | `POST /v1/galileo/tamper-demo` runs real local 4-layer OSNMA verifier on preserved SBF (`188/188` tags → `authenticated`) and synthetic 1-bit ephemeris-flipped SBF copy (`0x4743462a → 0x4743422a` on E27 Word Type 1 with recomputed SBF CRC-16 → `authentication_failed`, `1 FAILED (HMAC mismatch detected)`); all 5 scope disclosures displayed & verified in E2E Test 7. |
| **6. Offline Operation & Clean Launcher** | Zero external network requests in default mode; `./start.sh` launches API + UI cleanly and terminates cleanly on `SIGTERM` | **PASS** | Chromium offline audit across Environmental, Graph, Decision-Time Audit, and Galileo Tamper Demo logged **`EXTERNAL_REQUESTS_COUNT=0`**. `./start.sh` started both services and exited cleanly on `SIGTERM` with zero leftover listeners on `:8000` or `:5173`. |
| **7. Backward Compatibility & Architectural Discipline** | All v0.1–v0.4 API contracts, `core/` domain independence, no LLM, no numerical truth score, no green "safe" verdicts | **PASS** | All 43 prior Python tests + 4 new v0.5 tests (**47 passed**); all 5 prior Playwright tests + 2 new v0.5 tests (**7 passed**). |

---

## 2. Verified Test & Build Results

1. **Python Test Suite (`/home/todd/dev/venvs/cassini/bin/pytest -v tests/`):**
   - Result: **`47 passed`** (0 failed; 1 benign upstream `StarletteDeprecationWarning` from `fastapi.testclient`).
   - Includes `tests/core/test_v05_graph_and_tamper.py` (4 new tests verifying `core/graph.py` domain isolation, `/v1/assess/graph` multi-source/missing/shared-dependency graphs, `/v1/galileo/tamper-demo`, and `/v1/context/lough-funshinagh`).
2. **Dashboard Production Build (`cd dashboard && npm run build`):**
   - Result: **`tsc -b && vite build` succeeded with 0 errors** (`dist/assets/index-*.js` built in 2.86s).
3. **Playwright E2E Suite (`cd dashboard && npx playwright test` against live `./start.sh`):**
   - Result: **`7 passed` in 9.9s** (5 regression tests from v0.1–v0.4 + 2 new v0.5 tests).
   - Visual screenshots captured and visually inspected:
     - `dashboard/test-results/evidence-inspector-v05-env.png` (Environmental Presentation Mode: Executive Hero, offline Lough Funshinagh map, 3-group Provenance & Evidence Graph, Selected Node Inspector, and 6-timestamp Timeline).
     - `dashboard/test-results/evidence-inspector-v05-galileo.png` (Galileo OSNMA Mode: 4-stage crypto pipeline, side-by-side Original vs 1-Bit Tampered SBF comparison, 5-point disclosures, Graph, and Timeline).
4. **Offline Network Audit (Chromium Playwright Request Listener):**
   - Result: **`EXTERNAL_REQUESTS_COUNT=0`** across initial load, Evidence Graph rendering, Decision-Time Audit, and Galileo Tamper Comparison.
5. **Lifecycle Shutdown Verification (`./start.sh` + `kill -TERM`):**
   - Result: **`CLEAN_SHUTDOWN_OK`** (no lingering listeners on TCP `:8000` or `:5173`).

---

## 3. Data Provenance & Synthetic Labelling Summary

- **Genuine Recorded Evidence (`synthetic: false`):**
  - Copernicus EMS `EMSR718_AOI02_DEL_MONIT01_v2` (`flood_extent`, SHA-256 `2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947`, `authentication: "unknown"`, `available_at: null`).
  - Geological Survey Ireland `GSI_11_Lough_Funshinagh` (`hydrometric_water_level`, `69.37 mAOD`, SHA-256 `89a136da9802d7ee055431d6e4e63d0298715785de11e2ddbf4e365419cfa3d3`, `authentication: "unknown"`, `available_at: null`).
  - Met Éireann `MET_EIREANN_DLY_1975_MT_DILLON` (`meteorological_rainfall`, `6.1 mm/day`, SHA-256 `8318023567c25839d291cc5291060f340b453cb612236f64fc6324edb1591744`, `authentication: "unknown"`, `available_at: null`).
  - Galileo OSNMA `OSNMA_SBF_WN1253_PKID1` (`gnss_osnma_auth`, Septentrio `mosaic-X5`, `188/188` locally verified ADKD=0 tags, SHA-256 `c68444c7395c346753cea5d280c6beafa2fff2b42fbd023b05add2e25a88cb56`, `authentication: "verified"`, `available_at: null`).
- **Display-Only Offline Map Context (`sample_data/context/lough_funshinagh_context.json`):**
  - Derived strictly from licensed Copernicus EMS `EMSR718` archive (`waterExtentA` simplified + 5 locality/gauge reference points); explicitly marked `display_only: true` and never used by the assessment engine.
- **Explicitly Synthetic Inputs (`synthetic: true`):**
  - Historical replay road/navigation claims (`SYNTHETIC INPUT` badge).
  - Controlled offline 1-bit tampered SBF copy (`SYNTHETIC TAMPER TEST` badge, `synthetic: true` in API response and graph).
  - Browser-only `Mock Mode` simplified fixtures (opt-in only, never auto-enabled).

---

## 4. Known Limitations (Unchanged & Explicitly Disclosed)

1. `available_at` is genuinely unknown (`null`) for all four archived provider datasets; switching to `Decision-Time Audit` therefore conservatively returns `insufficient_evidence` with `AVAILABILITY_TIME_UNKNOWN`.
2. The 24-hour flood relevance window and 1-hour Galileo navigation freshness window are demonstration policy parameters, not validated operational safety thresholds.
3. Galileo OSNMA verification uses a 2023 public test-phase recording (`NMAS=1`), is performed offline retrospectively, depends on trusted GSC public-key/Merkle-root material, does not establish user positioning accuracy, and does not demonstrate live real-time replay/meaconing protection.
4. No live operational feeds, real-time GNSS receiver integration, or road-safety certification are claimed.
