# EIP Core & FastAPI Service (`core/` and `api/`)

Implements EIP shared contract `v0.1` (`policy_version: flood-road-0.1`) with deterministic Shapely spatial/temporal assessment and zero external network calls during evaluation.

## Endpoints

- `GET /health` → `{"status": "ok", "contract_version": "0.1"}`
- `GET /v1/evidence` → `{"items": [Evidence, ...]}`
- `POST /v1/assess` → deterministic `AssessmentResponse` (`potential_conflict` | `no_mapped_overlap` | `insufficient_evidence`)
- `GET /openapi.json` and `GET /docs` → auto-generated OpenAPI schema

## Setup & Run

```bash
# Install into external virtualenv (~/dev/venvs/cassini)
python3 -m venv ~/dev/venvs/cassini
~/dev/venvs/cassini/bin/pip install -r requirements.lock.txt
~/dev/venvs/cassini/bin/pip install --no-deps -e .

# Run API on localhost:8000 (reads EIP_EVIDENCE_PATH, default sample_data/evidence.json)
~/dev/venvs/cassini/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## Testing

```bash
~/dev/venvs/cassini/bin/pytest -v tests/core/
```
