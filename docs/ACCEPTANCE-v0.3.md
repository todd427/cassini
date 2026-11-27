# EIP Acceptance Audit — v0.3.0

Audited against EIP v0.3.0 multi-source requirements, `CONTRACT.md`, and the `v0.1.0`/`v0.2.0` baselines on **27 November 2026** via automated test execution.

---

## 1. Acceptance Criteria Checklist

| # | Criterion | Status | Verification Evidence |
|---|---|---|---|
| 1 | At least one additional genuine independent evidence source integrated | **PASS (2 integrated)** | Integrated genuine GSI `gwlevel.ie` Lough Funshinagh (`GSI_11`, `69.37 mAOD` at `2024-04-15T06:00:00Z`, CC BY 4.0) AND Met Éireann Mount Dillon (`dly1975.csv`, `6.1 mm` / `26.7 mm` 5d, CC BY 4.0) with preserved raw CSVs and verified SHA-256 digests |
| 2 | Existing Copernicus evidence remains operational | **PASS** | `EMSR718_AOI02_DEL_MONIT01_v2` verified by `test_real_copernicus_evidence_provenance_and_checksum` and live API/UI |
| 3 | New connector uses v0.2 `EvidenceConnector` with zero changes to generic engine (`core/`) | **PASS** | `GsiGwlevelConnector` (`connectors/gsi_gwlevel.py`) and `MetEireannDailyConnector` (`connectors/met_eireann.py`) implement `EvidenceConnector`; zero files modified under `core/` (`git diff v0.2.0 -- core/` is empty) |
| 4 | Source independence explicitly represented | **PASS** | `AssessmentResponse.independence` reports `distinct_declared_sources` (`3` groups) for Copernicus + GSI + Met Éireann and renders in Dashboard (`independence-summary`) |
| 5 | Shared upstream observations not counted as independent corroboration | **PASS** | `shared_upstream_derived` scenario collapses different-publisher COSMO-SkyMed derivatives into 1 correlated group (`shared_dependencies_detected`, `independent_group_count = 1`) |
| 6 | Direct and indirect evidence distinguished | **PASS** | `indirect_only_insufficient` scenario proves extreme lake stage (`69.37 mAOD`) + rainfall alone NEVER yield `potential_conflict` or `no_mapped_overlap` — strictly `insufficient_evidence` (`INDIRECT_EVIDENCE_ONLY`); UI displays `Direct` vs `Indirect contextual` badges |
| 7 | Decision-time filtering remains correct | **PASS** | `decision_time_unavailable` scenario blocks post-decision publication (`NOT_AVAILABLE_AT_DECISION_TIME`) and flags unknown `available_at` (`AVAILABILITY_TIME_UNKNOWN`) |
| 8 | All existing regression tests pass | **PASS** | All 22 v0.1 core/API tests + all 8 v0.2 architecture tests + Copernicus/fixture tests pass |
| 9 | New connector & multi-source assessment tests pass | **PASS** | `tests/core/test_v03_multisource.py` (4 passed) + `test_real_independent_gsi_and_met_eireann_provenance_and_checksums` (passed) + Playwright multi-source E2E test (4/4 passed) |
| 10 | Production dashboard build passes & offline demo functional | **PASS** | `cd dashboard && npm run build` (0 errors); Playwright E2E + Chromium offline audit confirms **0 external network requests**; `./start.sh` verified |

---

## 2. Genuine vs Synthetic Evidence Distinction

- **Genuine Provider Evidence (`synthetic: false`, stored in `sample_data/evidence.json`):**
  1. `cems-emsr718-aoi02-del-monit01-v2` — Copernicus EMS Rapid Mapping (`sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip`, SHA-256 `2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947`)
  2. `gsi-gwlevel-gsi-11-20240415t0600z` — Geological Survey Ireland (`sample_data/raw/GSI_11_Lough_Funshinagh.csv`, SHA-256 `89a136da9802d7ee055431d6e4e63d0298715785de11e2ddbf4e365419cfa3d3`)
  3. `met-eireann-1975-20240415` — Met Éireann (`sample_data/raw/MetEireann_MtDillon_dly1975.csv`, SHA-256 `8318023567c25839d291cc5291060f340b453cb612236f64fc6324edb1591744`)
- **Explicitly Synthetic Data (`synthetic: true`):**
  - Road passability claims in `sample_data/example_claims.json` and dashboard presets (no structured open road-closure GeoJSON feed existed from Roscommon County Council for April 2024).
  - Direct-vs-direct disagreement (`direct_disagreement_synthetic`), derived-product (`shared_upstream_derived`), and post-decision publication (`decision_time_unavailable`) synthetic test fixtures under `sample_data/scenarios/` and `sample_data/fixtures/`.

---

## 3. Documented Unsuccessful / Non-Selected Source Attempts & Remaining Limitations

- **OPW `waterlevel.ie`:** No station on Lough Funshinagh itself; historical archive zip returned HTTP 404.
- **Roscommon County Council (`roscommoncoco.ie`):** Historical April 2024 update URL returned HTTP 404; road closures page contains unstructured current HTML rather than machine-readable April 2024 GeoJSON.
- **CDSE STAC Sentinel-1 / Sentinel-2:** Sentinel-2 scenes had `98.3%–100%` cloud cover; Sentinel-1 GRD raster downloads require CDSE authentication and flood-extraction processing (catalogue footprints are not flood extents).
- **Unknown availability timestamps (`available_at: null`):** None of the 3 genuine raw provider archives embeds an exact UTC publication timestamp per record, so all 3 honestly report `available_at: null` and yield `AVAILABILITY_TIME_UNKNOWN` in `decision_time` mode.
- **Authentication:** Remains `"unknown"` across all 3 sources; SHA-256 verifies local byte integrity only (Galileo OSNMA / cryptographic provenance is deferred to a later phase).
