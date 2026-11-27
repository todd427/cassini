# Evidence Integrity Platform (EIP) — v0.1.0

A reusable, deterministic geospatial and temporal evidence assessment API with one reference web application (**Evidence Inspector**), built for CASSINI 12 (Contract `v0.1`, policy `flood-road-0.1`).

> **Disclaimer:** EIP is an evidence-consistency tool, **not** a truth oracle, safety certification, or emergency routing service. An overlap is a potential conflict (not proof of impassability); absence of mapped flooding is not proof of road safety.

## Architecture

```
Copernicus EMS Rapid Mapping ZIP (EMSR718 Lough Funshinagh)
        │
        ▼  connectors/cems_rapid_mapping.py (SHA-256 + WGS84 validation)
sample_data/evidence.json (+ sample_data/fixtures/)
        │
        ▼  core/assessment.py (Shapely spatial/temporal rules, flood-road-0.1)
api/main.py (FastAPI REST API on 127.0.0.1:8000, Contract v0.1)
        │
        ▼  VITE_API_BASE_URL
dashboard/ (React + TypeScript + MapLibre GL JS on 127.0.0.1:5173)
```

## Real Copernicus Data Included

- **Event:** Copernicus EMS Rapid Mapping Activation **`EMSR718`** — *Flood in Ireland*, AOI02 **Lough Funshinagh** (Co. Roscommon, April 2024).
- **Product:** `EMSR718_AOI02_DEL_MONIT01_v2` (COSMO-SkyMed Second Generation 3.0 m SAR, acquired `2024-04-15T06:02:08Z`, 103 flood extent polygons + documented AOI/footprint coverage).
- **Raw Archive:** `sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip`
- **SHA-256:** `2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947` (verifies local byte integrity; `authentication` remains `unknown`).
- **Attribution:** © European Union, Copernicus Emergency Management Service (2024).

See `docs/ACCEPTANCE-v0.1.md` for the full v0.1 acceptance audit and `connectors/README.md` for data provenance and regeneration instructions.

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

*(Alternatively, install range-constrained dependencies directly from `pyproject.toml` with `~/dev/venvs/cassini/bin/pip install -e ".[dev]"`.)*

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

This starts both services on localhost and shuts both down cleanly on `Ctrl+C` (`SIGINT`/`SIGTERM`):
- **API:** `http://127.0.0.1:8000` (OpenAPI docs: `http://127.0.0.1:8000/docs`)
- **Dashboard:** `http://127.0.0.1:5173`

Optional environment overrides for `start.sh`: `EIP_VENV`, `EIP_API_HOST`, `EIP_API_PORT`, `EIP_UI_HOST`, `EIP_UI_PORT`, `EIP_EVIDENCE_PATH`, `VITE_API_BASE_URL`.

### Manual Startup (Two Terminals)

```bash
# Terminal 1 — FastAPI backend (127.0.0.1:8000)
~/dev/venvs/cassini/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Evidence Inspector dashboard (127.0.0.1:5173)
cd dashboard && npm run dev -- --host 127.0.0.1
```

Everything runs completely offline with zero external network requests once local dependencies are installed.

---

## Testing & Verification

### 1. Python Core, API & Data Provenance Tests (25 tests)

```bash
~/dev/venvs/cassini/bin/pytest -v tests/
```

### 2. Dashboard TypeScript & Production Build

```bash
cd dashboard && npm run build
```

### 3. Playwright End-to-End Browser Tests (3 specs)

With `./start.sh` (or both API on `:8000` and Vite on `:5173`) running:

```bash
cd dashboard && npx playwright test
```

### 4. Raw Artifact Integrity Check

```bash
sha256sum sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip
# Expected: 2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947
```
