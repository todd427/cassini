# EIP Acceptance Audit — v0.4.0

Audited against EIP v0.4.0 Galileo OSNMA integration requirements, `CONTRACT.md`, and `v0.1.0`/`v0.2.0`/`v0.3.0` baselines on **27 November 2026** via automated test execution.

---

## 1. Acceptance Criteria Checklist

| # | Criterion | Status | Verification Evidence |
|---|---|---|---|
| 1 | Genuine Galileo evidence acquired (or blockers documented) | **PASS** | Acquired genuine Septentrio `mosaic-X5` Galileo E1-B SBF recording (`sample_data/raw/galileo/osnma_new_config.sbf`, 4,135 `GALRawINAV` frames, E07/E18/E21/E27, 27 Aug 2023) + official GSC `OSNMA_MerkleTree.xml` & `OSNMA_PublicKey.xml` with verified SHA-256 digests |
| 2 | Cryptographic verification is reproducible offline | **PASS** | `connectors/galileo_osnma.py` locally verifies GSC Merkle Tree SHA-256 proof, ECDSA P-256 DSM-KROOT signature, 73 TESLA SHA-256 subframes, and **188 / 188** HMAC-SHA-256 ADKD=0 tags offline; 1-bit ephemeris tamper test cryptographically fails (`MAC_TAG_VERIFICATION_FAILED`) |
| 3 | Externally reported authentication distinguished from locally verified authentication | **PASS** | `verification_method: "local_osnma_cryptographic"` (`locally_verified: true`) yields `authenticated`; `"externally_reported"` (`locally_verified: false`) yields `authentication_unknown` (`OSNMA_EXTERNALLY_REPORTED_UNVERIFIED`) |
| 4 | Galileo policy uses existing generic engine & policy registry with zero `core/` changes | **PASS** | `GalileoOsnmaPolicy` (`policies/galileo_osnma.py`) registered in `PolicyRegistry`; `git diff v0.2.0 -- core/` is **empty (0 lines changed)**; specialist `ecdsa` isolated in `[project.optional-dependencies] osnma` |
| 5 | All 6 authentication outcomes & positioning scope boundary distinguished | **PASS** | Verified via 7 scenarios in `tests/core/test_v04_galileo_osnma.py`: `authenticated`, `authentication_failed`, `authentication_pending`, `authentication_unavailable`, `authentication_unknown`, `insufficient_evidence`, and `evidence_unsuitable` (`gnss_position_accurate`) |
| 6 | Existing environmental assessments remain operational | **PASS** | All 3 Lough Funshinagh genuine environmental sources (Copernicus, GSI, Met Éireann) remain live & verified |
| 7 | All existing regression tests pass | **PASS** | All 22 v0.1 tests + 8 v0.2 tests + 4 v0.3 tests + 4 data provenance/fixture tests pass |
| 8 | New Galileo connector & policy tests pass | **PASS** | `tests/core/test_v04_galileo_osnma.py` (`5 passed`, total **`43 passed`**) |
| 9 | Browser tests & production dashboard build pass; offline preserved | **PASS** | `cd dashboard && npm run build` (0 errors); **`5/5` Playwright E2E tests** pass (4 environmental + 1 Galileo OSNMA mode); Chromium offline audit confirms **0 external network requests**; `./start.sh` verified |
| 10 | Any changes to `core/` explicitly justified | **PASS (0 changes)** | Zero modifications to `core/` were required |

---

## 2. Genuine vs. Synthetic Evidence Distinction

- **Genuine Locally Verified Galileo Evidence (`synthetic: false`):**
  - `galileo-osnma-sbf-wn1253-pkid1` (`sample_data/raw/galileo/osnma_new_config.sbf`, SHA-256 `c68444c7395c346753cea5d280c6beafa2fff2b42fbd023b05add2e25a88cb56`, `OSNMA_MerkleTree.xml` SHA-256 `123c8db2c157...`, `OSNMA_PublicKey.xml` SHA-256 `ba2e95034dd1...`).
- **Explicitly Synthetic Galileo Test Scenarios (`synthetic: true`):**
  - `galileo_tampered_failed.json` (also backed by a real 1-bit tamper test over raw SBF bytes in `test_tampering_one_bit_in_real_galileo_nav_message_fails_osnma_cryptographically`), `galileo_pending_tesla.json` (also tested by truncating raw SBF to 1 subframe), `galileo_unavailable_outage.json`, `galileo_externally_reported_unknown.json`, plus synthetic user claims (`synthetic: true`) against the genuine SBF evidence.

---

## 3. Remaining Limitations & Blockers Documented Honestly

- **Temporal/geographical independence from Lough Funshinagh:** The genuine recorded Galileo SBF (`2023-08-27`, `NMAS=1` public test phase) is an independent historical Galileo OSNMA demonstration recording, **not** a receiver recording captured at Lough Funshinagh on 15 April 2024 (no public raw Galileo I/NAV SBF recording from Co. Roscommon on 15 April 2024 was available). It is therefore exposed in a dedicated Galileo OSNMA assessment mode rather than falsely coupled to the April 2024 flood event.
- **Direct GSC IDD portal registration:** Downloading fresh cryptographic XMLs directly from GSC IDD requires a registered GSC account; v0.4.0 uses the authentic GSC XMLs preserved alongside the recorded SBF (`MT-AA1AC9A4...`, `PK-9202CB2A...`) and verifies the Merkle proof locally.
- **Offline time-sync limitation:** Verifying recorded SBF files offline cannot validate real-time receiver clock synchronisation against Galileo System Time (GST).
