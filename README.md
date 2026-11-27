# Evidence Integrity Platform (EIP) — v0.2.0

An extensible, domain-independent evidence assessment platform with a deterministic REST API (Contract `v0.1` compatible + `v0.2` discovery, temporal integrity, and source independence) and one reference web application (**Evidence Inspector**).

> **Disclaimer:** EIP is an evidence-consistency tool, **not** a truth oracle, safety certification, or emergency routing service. No LLM and no arbitrary numerical truth score are used.

---

## Architecture Overview

```
Connectors (connectors/)             ──► Storage & Normalisation (core/store.py)
  • CemsRapidMappingConnector              • EvidenceStore protocol
  • EvidenceConnector protocol             • FileEvidenceStore / InMemoryEvidenceStore
                                                     │
                                                     ▼
Domain Policies (policies/)          ──► Generic Evidence Engine (core/engine.py)
  • PolicyRegistry & PolicySpec            • Integrity & SHA-256 checks (core/integrity.py)
  • FloodRoadPolicy (flood-road-0.1)       • 6 Timestamps & Temporal Modes (core/temporal.py)
  • Custom Enterprise Policies             • Source Independence Analysis (core/independence.py)
                                           • Optional WGS84 Spatial Primitives (core/spatial.py)
                                                     │
                                                     ▼
                                         REST API (api/main.py — 127.0.0.1:8000)
                                           • GET  /health, /v1/evidence, /openapi.json
                                           • GET  /v1/capabilities, /v1/policies  (v0.2)
                                           • POST /v1/assess (retrospective & decision_time)
                                                     │
                                                     ▼
                                         External Consumers & Reference UI (dashboard/ — :5173)
```

### Key Documentation
- **[CONTRACT.md](CONTRACT.md):** Authoritative Contract `v0.2` interface (backward-compatible with `v0.1`).
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md):** Full architectural specification, Mermaid diagram, temporal integrity model, source independence model, and enterprise extension pattern.
- **[docs/POLICY-DEVELOPMENT.md](docs/POLICY-DEVELOPMENT.md):** Step-by-step developer guide for implementing and registering a new domain policy without modifying `core/` or `api/`.
- **[docs/ACCEPTANCE-v0.2.md](docs/ACCEPTANCE-v0.2.md):** Verified v0.2 acceptance audit (and [docs/ACCEPTANCE-v0.1.md](docs/ACCEPTANCE-v0.1.md) for the v0.1 baseline).
- **[connectors/README.md](connectors/README.md):** Genuine Copernicus `EMSR718` Lough Funshinagh provenance, SHA-256 verification, and fixture generation.

---

## Real Copernicus Data Included

- **Event:** Copernicus EMS Rapid Mapping Activation **`EMSR718`** — *Flood in Ireland*, AOI02 **Lough Funshinagh** (Co. Roscommon, April 2024).
- **Product:** `EMSR718_AOI02_DEL_MONIT01_v2` (COSMO-SkyMed Second Generation 3.0 m SAR, acquired `2024-04-15T06:02:08Z`, 103 flood extent polygons + documented AOI/footprint coverage).
- **Raw Archive:** `sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip`
- **SHA-256:** `2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947` (verifies local byte integrity; `authentication` remains `unknown`).
- **Attribution:** © European Union, Copernicus Emergency Management Service (2024).

---

## Installation

### Prerequisites
- Python `3.12`
- Node.js `20 LTS` (or `22 LTS`) and `npm`

### 1. Python Environment (`~/dev/venvs/cassini`)

```bash
mkdir -p ~/dev/venvs
python3 -m venv ~/dev/venvs/cassini

# Reproducible install using pinned lockfile + editable local package
~/dev/venvs/cassini/bin/pip install -r requirements.lock.txt
~/dev/venvs/cassini/bin/pip install --no-deps -e .
```

### 2. Dashboard Dependencies (`dashboard/`)

```bash
cd dashboard
npm ci
# Optional (needed only for Playwright browser tests):
npx playwright install chromium
```

---

## Startup

### Recommended: Single-Command Launcher

```bash
./start.sh
```

Launches both services on localhost and shuts both down cleanly on `Ctrl+C`:
- **API:** `http://127.0.0.1:8000` (OpenAPI: `http://127.0.0.1:8000/docs`, Policies: `http://127.0.0.1:8000/v1/policies`, Capabilities: `http://127.0.0.1:8000/v1/capabilities`)
- **Dashboard:** `http://127.0.0.1:5173`

### Manual Startup (Two Terminals)

```bash
# Terminal 1 — FastAPI backend (127.0.0.1:8000)
~/dev/venvs/cassini/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Evidence Inspector dashboard (127.0.0.1:5173)
cd dashboard && npm run dev -- --host 127.0.0.1
```

Everything operates completely offline with zero external network requests once local dependencies are installed.

---

## Testing & Verification

```bash
# 1. Python regression + v0.2 architecture + data provenance tests
~/dev/venvs/cassini/bin/pytest -v tests/

# 2. Dashboard TypeScript & production build
cd dashboard && npm run build

# 3. Playwright E2E browser tests (while ./start.sh or both servers are running)
cd dashboard && npx playwright test
```
