# Galileo OSNMA Integration — Research, Verification & Limitations (EIP v0.4.0)

This document records the research, genuine recorded data acquisition, local cryptographic verification, policy semantics, and strict epistemic boundaries for **Galileo Open Service Navigation Message Authentication (OSNMA)** in EIP `v0.4.0`.

---

## 1. Research Summary & Evaluated Sources

| Resource | URL | Licence | Live Probe Result | Disposition |
|---|---|---|---|---|
| **Galileo OSNMA SIS ICD v1.1 & Receiver Guidelines** | `https://www.gsc-europa.eu/galileo/services/galileo-open-service-navigation-message-authentication-osnma`<br>`https://www.gsc-europa.eu/electronic-library/programme-reference-documents` | European Union / EUSPA public technical docs | `HTTP 200` | Authoritative specification used for 4-layer local verification |
| **GSC Public Key & Merkle Tree Material** | Official GSC XMLs (`OSNMA_MerkleTree.xml`, `OSNMA_PublicKey.xml`) distributed via GSC IDD & bundled with `Algafix/OSNMA` | Official GSC cryptographic material (© European Union) | Direct GSC portal IDD requires user registration; verified GSC XMLs (`UID: MT-AA1AC9A4...`, `PK-9202CB2A...`, `issueDate: 2023-08-03T10:59:53Z`) retrieved from `Algafix/OSNMA` | Preserved locally & cryptographically verified (`Merkle Root: 0e63f552...`) |
| **OSNMAlib (`Algafix/OSNMA`)** | `https://github.com/Algafix/OSNMA` | **EUPL-1.2** (copyleft) | `HTTP 200` (active through Oct 2026); includes real Septentrio SBF, u-blox UBX, and corner-case recordings (`osnma_outage`, `real_crev`, `real_eoc`) | Used genuine 212 KB Septentrio `mosaic-X5` SBF recording (`tests/scenarios/new_live_config/osnma_new_config.sbf`) + GSC XMLs. Did NOT bundle full OSNMAlib runtime (`pandas`/`protobuf`/`pyserial`/`ntplib`) to keep EIP lightweight and isolated. |
| **galileo-osnma (`daniestevez/galileo-osnma`)** | `https://github.com/daniestevez/galileo-osnma` | **MIT / Apache-2.0** | `HTTP 200` (Rust crate, pushed Mar 2026) | Cross-referenced SIS ICD v1.1 ADKD=0 bit slicing & MACK header layout (`Tag0` at bits `0..TS`). |
| **FGI-OSNMA (`nlsfi/fgi-osnma`)** | `https://github.com/nlsfi/fgi-osnma` | **GPL-3.0** | `HTTP 200` (last updated Nov 2023) | Reviewed; not adopted due to GPL-3.0 and older update date. |
| **Zenodo API Search** | `https://zenodo.org/api/records?q=galileo+osnma+inav` | N/A | Connection failed / timeout from research probe | Documented unsuccessful probe; `Algafix/OSNMA` Septentrio recording provided genuine data. |

---

## 2. Genuine Recorded Galileo Evidence Acquired & Preserved

Stored offline under `sample_data/raw/galileo/`:

| File | Size | SHA-256 | Provenance |
|---|---|---|---|
| `sample_data/raw/galileo/osnma_new_config.sbf` | 212 KB | `c68444c7395c346753cea5d280c6beafa2fff2b42fbd023b05add2e25a88cb56` | Genuine Septentrio **`mosaic-X5`** (firmware `4.14.x`, extracted from SBF Block `5902`) recording of `4,135` `GALRawINAV` (Block `4023`) frames across 4 Galileo satellites (**E07, E18, E21, E27**), `2023-08-27T20:03:51Z` – `2023-08-27T20:40:59Z` (GST Week `1253`, TOW `72249`–`74477`). Source: `Algafix/OSNMA` (`tests/scenarios/new_live_config/`, EUPL-1.2). |
| `sample_data/raw/galileo/OSNMA_MerkleTree.xml` | 1.7 KB | `123c8db2c157de8ca6cbf573e6589a5ec58451ece5e3864548df1d741ed664b6` | Official GSC Merkle Tree XML (`UID: MT-AA1AC9A4FFA41F00DC5BA63B0CD30129A9E1E9BCBC3FB7731B41F7EB63208BAE`, `issueDate: 2023-08-03T10:59:53Z`, `N=16`, `SHA-256`, Root `0e63f552c8021709043c239032effe941bf22c8389032f5f2701e0fbc80148b8`). |
| `sample_data/raw/galileo/OSNMA_PublicKey.xml` | 1.0 KB | `ba2e95034dd188bf9d6205f6577615b8b1f905b92f440f636f5244dc2532ec4c` | Official GSC Public Key XML (`UID: PK-9202CB2A8A0AA4A40E032B454718498FB08C78D1EFE53149A4E2DE78CAA196F3`, `PKID=1`, `ECDSA P-256/SHA-256`). |

---

## 3. Local 4-Layer Cryptographic Verification Performed (`connectors/galileo_osnma.py`)

Specialist cryptographic dependency `ecdsa` (`>=0.19.0,<1.0.0`) is isolated in `[project.optional-dependencies] osnma` in `pyproject.toml` and imported lazily inside `connectors/galileo_osnma.py`, keeping `core/` completely free of GNSS dependencies.

Every run of `GalileoOsnmaConnector.load_evidence()` executes four genuine SIS ICD v1.1 cryptographic verifications locally offline:

1. **GSC Merkle Tree Proof (`SHA-256`):** Hashes `((NPKT << 4 | PKID) || PK_point)` and walks all 4 tree levels (`j=0..3`) to match GSC Merkle Root `0e63f552c8021709043c239032effe941bf22c8389032f5f2701e0fbc80148b8` → **Verified (`True`)**.
2. **DSM-KROOT Digital Signature (`ECDSA P-256/SHA-256`):** Reassembles 8 HKROOT DSM-KROOT blocks (`DSM_ID=10`, `NB_DK=2`) from genuine SBF subframes and verifies the 512-bit ECDSA signature over `NMA_Header || DSM-KROOT[8:232]` using the Merkle-verified GSC Public Key (`PKID=1`) → **Verified (`True`)** (`CIDKR=3`, `KS=128`, `TS=40`, `MACLT=33`, `WN_K=1253`, `TOWH_K=20`, `NMAS=1 [test]`).
3. **TESLA One-Way Key Chain (`SHA-256`):** Extracts disclosed 128-bit TESLA keys from `MACK` (bytes `42..58`) across complete 30-second subframes and iteratively computes `SHA-256(K || GST_SF || alpha)[:16]` back to `KROOT` → **73 distinct subframes cryptographically chained to KROOT**.
4. **Navigation Data Tag0 Authentication (`HMAC-SHA-256`, `ADKD=0`):** Computes `HMAC-SHA-256(K_sf, PRN_A || GST_SF || CTR=1 || NMAS || nav_bits_549)[:40]` over genuine Galileo I/NAV Word Types 1–5 (ephemeris, clock, ionospheric/BGD, health/DVS) and constant-time compares against broadcast 40-bit `Tag0` → **188 / 188 subframes verified** (`E07: 44`, `E18: 71`, `E21: 2`, `E27: 71`, `0` failures).

**Tamper Verification Test:** Flipping **1 single bit** inside a genuine Galileo Word Type 1 ephemeris word (and updating the SBF block CRC) immediately fails local HMAC-SHA-256 verification (`outcome: "failed"`, `authentication: "failed"`, `MAC_TAG_VERIFICATION_FAILED`), verified by `test_tampering_one_bit_in_real_galileo_nav_message_fails_osnma_cryptographically`.

---

## 4. Local vs. Externally Reported Authentication & Strict Scope Boundaries

- **Local vs. External Distinction:** Only records with `verification_method == "local_osnma_cryptographic"` and `locally_verified == True` receive `authentication == "verified"` and policy status `authenticated`. An externally reported receiver flag (`verification_method == "externally_reported"`, `locally_verified == False`) is explicitly classified as **`authentication_unknown`** (`OSNMA_EXTERNALLY_REPORTED_UNVERIFIED`).
- **What OSNMA Authenticates:** Broadcast Galileo E1-B I/NAV ADKD=0 navigation message bits (Word Types 1–5: ephemeris, clock corrections, ionospheric/BGD, health/DVS).
- **What OSNMA Does NOT Authenticate:**
  - User positioning accuracy or pseudorange integrity.
  - Receiver hardware, antenna, or firmware trustworthiness.
  - Protection against signal replay / meaconing spoofing (especially offline without live Galileo System Time loose time-sync verification).
- Consequently, submitting a `gnss_position_accurate` claim against verified OSNMA evidence returns **`evidence_unsuitable`** (`NAV_AUTH_INSUFFICIENT_FOR_POSITIONING`).
- **Public Test-Phase Signal Caveat:** The genuine 27 Aug 2023 recording broadcasts `NMAS=1` (`test`, Galileo OSNMA public test phase), which is explicitly surfaced in `attributes.nma_status` and `limitations` rather than disguised as `NMAS=2` (`operational`).
- **Availability Timestamp:** The SBF recording does not embed an archive publication UTC timestamp, so `available_at` remains honestly `null`.
