# Evidence Integrity Platform (EIP) — v0.6.0

An extensible, domain-independent evidence assessment platform with a deterministic REST API (Contract `v0.1` compatible + `v0.2`–`v0.6` discovery, temporal integrity, source independence, genuine multi-source corroboration, local Galileo OSNMA cryptographic verification, and backend-derived provenance/evidence graphs), a reusable **Python Client SDK & CLI (`eip_sdk`)**, and one reference web application (**Evidence Inspector**).

> **Disclaimer:** EIP is an evidence-consistency and cryptographic navigation-message verification tool, **not** a truth oracle, safety certification, positioning-accuracy guarantee, or automated final decision-maker. No LLM and no arbitrary numerical truth score are used.

---

## Architecture Overview

```
Connectors (connectors/)             ──► Storage & Normalisation (core/store.py)
  • CemsRapidMappingConnector (SAR)        • EvidenceStore protocol
  • GsiGwlevelConnector (in-situ stage)    • FileEvidenceStore / InMemoryEvidenceStore
  • MetEireannDailyConnector (rainfall)              │
  • GalileoOsnmaConnector (local crypto)             ▼
  • EvidenceConnector protocol           Generic Evidence Engine (core/engine.py)
                                           • Integrity & SHA-256 checks (core/integrity.py)
Domain Policies (policies/)          ──►   • 6 Timestamps & Temporal Modes (core/temporal.py)
  • PolicyRegistry & PolicySpec            • Source Independence Analysis (core/independence.py)
  • FloodRoadPolicy (flood-road-0.1)       • Domain-Independent Evidence Graph (core/graph.py)
  • GalileoOsnmaPolicy (galileo-osnma-0.1) • Optional WGS84 Spatial Primitives (core/spatial.py)
                                                     │
                                                     ▼
                                         REST API (api/main.py — 127.0.0.1:8000)
                                           • GET  /health, /v1/evidence, /openapi.json
                                           • GET  /v1/capabilities, /v1/policies
                                           • POST /v1/assess & POST /v1/assess/graph
                                           • POST /v1/galileo/tamper-demo
                                           • GET  /v1/context/lough-funshinagh
                                                     │
                   ┌─────────────────────────────────┴─────────────────────────────────┐
                   ▼                                                                   ▼
      External Enterprise Consumers                                      Reference UI (:5173)
        • Python Client SDK (eip_sdk.EIPClient, REST-only)                 • Evidence Inspector
        • Automated CLI (eip-cli / python -m eip_sdk)                      • Presentation & Technical
        • Claims Triage CLI (examples/enterprise_insurance_workflow.py)    • Evidence Graph & Timeline
        • Language-Agnostic HTTP / curl (examples/curl_examples.sh)        • Galileo Tamper Comparison
```

### Key Documentation
- **[docs/DEVELOPER-QUICKSTART.md](docs/DEVELOPER-QUICKSTART.md):** 5-minute Python SDK, CLI, and `curl` quickstart.
- **[eip_sdk/README.md](eip_sdk/README.md):** Python Client SDK & CLI reference (`eip_sdk`).
- **[docs/ENTERPRISE-INTEGRATION.md](docs/ENTERPRISE-INTEGRATION.md):** Architecture diagram, 7-step extension guide, and OpenAPI/GeoJSON/STAC/W3C PROV interoperability review.
- **[docs/PRODUCTION-READINESS.md](docs/PRODUCTION-READINESS.md):** Explicit production enterprise readiness boundaries and gaps.
- **[CONTRACT.md](CONTRACT.md):** Authoritative Contract interface (`v0.1` compatible + `v0.2`–`v0.6` extensions).
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md):** Core architecture specification, temporal integrity, and source independence.
- **[docs/EVIDENCE-SOURCES.md](docs/EVIDENCE-SOURCES.md):** Genuine Lough Funshinagh evidence research, provenance, and independence analysis.
- **[docs/GALILEO-INTEGRATION.md](docs/GALILEO-INTEGRATION.md):** Galileo OSNMA 4-layer local cryptographic verification and scope limitations.
- **[docs/POLICY-DEVELOPMENT.md](docs/POLICY-DEVELOPMENT.md):** Step-by-step guide for adding a domain policy without modifying `core/` or `api/`.
- **[docs/ACCEPTANCE-v0.6.md](docs/ACCEPTANCE-v0.6.md):** Verified v0.6 acceptance audit (see also `v0.5`–`v0.1`).

---

## Genuine Evidence Sources Included (`synthetic: false`)

Four genuinely independent, openly licensed provider datasets are preserved locally under `sample_data/raw/` and loaded into `sample_data/evidence.json`:

1. **Copernicus EMS Rapid Mapping (`EMSR718_AOI02_DEL_MONIT01_v2`)** — **Direct** flood extent (`flood_extent`, 103 polygons, COSMO-SkyMed 3.0 m SAR acquired `2024-04-15T06:02:08Z`, SHA-256 `2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947`, © European Union).
2. **Geological Survey Ireland (`GSI_11` Lough Funshinagh)** — **Indirect contextual** in-situ pressure transducer stage (`hydrometric_water_level`, **`69.37 mAOD`** at `2024-04-15T06:00:00Z`, SHA-256 `89a136da9802d7ee055431d6e4e63d0298715785de11e2ddbf4e365419cfa3d3`, CC BY 4.0).
3. **Met Éireann (`Station 1975` Mount Dillon)** — **Indirect contextual** synoptic daily rainfall (`meteorological_rainfall`, `6.1 mm` on 15 Apr 2024, `26.7 mm` 5-day cumulative, SHA-256 `8318023567c25839d291cc5291060f340b453cb612236f64fc6324edb1591744`, CC BY 4.0).
4. **Galileo OSNMA (`OSNMA_SBF_WN1253_PKID1`)** — **Locally cryptographically verified** Galileo E1-B I/NAV ADKD=0 navigation data recorded on a Septentrio `mosaic-X5` (`2023-08-27`, `188/188` HMAC-SHA-256 tags, `73` TESLA subframes, ECDSA P-256 DSM-KROOT, GSC Merkle Tree SHA-256 proof, `authentication: "verified"`, SHA-256 `c68444c7395c346753cea5d280c6beafa2fff2b42fbd023b05add2e25a88cb56`, EUPL-1.2 & © EU GSC).

---

## Installation & Startup

### 1. Python Environment (`~/dev/venvs/cassini`)

```bash
mkdir -p ~/dev/venvs
python3 -m venv ~/dev/venvs/cassini
~/dev/venvs/cassini/bin/pip install -r requirements.lock.txt
~/dev/venvs/cassini/bin/pip install --no-deps -e .
```

### 2. Dashboard Dependencies (`dashboard/`)

```bash
cd dashboard && npm ci
```

### 3. Launch Both Services (Offline-Ready)

```bash
./start.sh
```

- **API:** `http://127.0.0.1:8000` (OpenAPI: `/docs`, Policies: `/v1/policies`, Capabilities: `/v1/capabilities`)
- **Dashboard:** `http://127.0.0.1:5173`

---

## Testing & Verification

```bash
# 1. Full Python regression, v0.2 architecture, v0.3 multi-source, and provenance tests
~/dev/venvs/cassini/bin/pytest -v tests/

# 2. Dashboard TypeScript & production build
cd dashboard && npm run build

# 3. Playwright E2E browser tests (while ./start.sh is running)
cd dashboard && npx playwright test
```
