# EIP Developer Quickstart (v0.6.0)

Integrate deterministic evidence assessment into an external Python application, CLI pipeline, or language-agnostic HTTP consumer in under five minutes—without importing EIP internals, satellite geometry libraries, or cryptographic verification code.

---

## 1. Start a Local EIP Service

```bash
# Option A: Full local stack (API on :8000 + Evidence Inspector UI on :5173)
./start.sh

# Option B: Headless REST API only (suitable for backend integration & CI)
~/dev/venvs/cassini/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

---

## 2. Minimal Python SDK Integration (~15 Lines)

Run [examples/minimal_quickstart.py](../examples/minimal_quickstart.py):

```python
from eip_sdk import ClaimInput, EIPClient

client = EIPClient("http://127.0.0.1:8000", timeout=5.0)
caps = client.check_compatibility()
print("Connected to EIP API:", caps.registered_policy_ids)

claim = ClaimInput.road_passable(
    claim_id="quickstart-ballagh-east",
    coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
    claimed_at="2024-04-15T08:00:00Z",
    source_label="Synthetic quickstart road claim (Lough Funshinagh East)",
    synthetic=True,
)
result = client.assess(claim)
print(f"Status:  {result.status} (policy={result.policy_version})")
print(f"Reasons: {', '.join(result.reasons)}")
```

Execute it:
```bash
~/dev/venvs/cassini/bin/python examples/minimal_quickstart.py
```

---

## 3. Domain-Specific Executable Examples

All examples consume the **exact same `EIPClient`** over HTTP:

| Example | Command | Demonstrates |
|---|---|---|
| Minimal Quickstart | `~/dev/venvs/cassini/bin/python examples/minimal_quickstart.py` | Compatibility check + road claim assessment |
| Environmental | `~/dev/venvs/cassini/bin/python examples/environmental_assessment.py` | Potential conflict + covered non-overlap across 3 genuine sources |
| Galileo OSNMA | `~/dev/venvs/cassini/bin/python examples/galileo_nav_auth.py` | Locally verified E27 nav auth + positioning-accuracy scope rejection |
| Decision-Time Audit | `~/dev/venvs/cassini/bin/python examples/decision_time_audit.py` | Retrospective replay vs. strict `decision_time` (`AVAILABILITY_TIME_UNKNOWN`) |
| Provenance & Graph | `~/dev/venvs/cassini/bin/python examples/provenance_graph_inspection.py --export /tmp/graph_report.json` | API-derived evidence graph, independence groups, JSON report export |
| Hypothetical Enterprise Triage CLI | `~/dev/venvs/cassini/bin/python examples/enterprise_insurance_workflow.py --case-id CASE-RF-2024-001` | Independent enterprise CLI producing a human-review dossier (never auto-rejects) |

---

## 4. Command-Line Client (`eip-cli` / `python -m eip_sdk`)

Emits clean JSON to `stdout` and structured JSON errors to `stderr` with deterministic exit codes (`0` OK, `1` input error, `2` connection/timeout error, `3` validation/unsupported claim error, `4` other API error):

```bash
# Check health & contract compatibility
~/dev/venvs/cassini/bin/python -m eip_sdk health

# Discover supported claim types, evidence kinds, and registered policies
~/dev/venvs/cassini/bin/python -m eip_sdk capabilities
~/dev/venvs/cassini/bin/python -m eip_sdk policies

# Inspect loaded evidence provenance (compact summary without bulky polygon rings)
~/dev/venvs/cassini/bin/python -m eip_sdk evidence --summary

# Assess a JSON claim from stdin and export an auditable report with graph
~/dev/venvs/cassini/bin/python -m eip_sdk assess --claim-file - --graph --report-out /tmp/eip-report.json <<'EOF'
{
  "claim_id": "cli-ballagh-east",
  "claim_type": "road_passable",
  "geometry": {"type": "LineString", "coordinates": [[-8.1165, 53.4916], [-8.1075, 53.4916]]},
  "claimed_at": "2024-04-15T08:00:00Z",
  "source_label": "Synthetic CLI road report",
  "synthetic": true
}
EOF
```

---

## 5. Language-Agnostic `curl` Examples

Run [examples/curl_examples.sh](../examples/curl_examples.sh) or invoke endpoints directly:

```bash
# 1. Discover capabilities
curl -sS http://127.0.0.1:8000/v1/capabilities

# 2. Assess an environmental road claim
curl -sS -X POST http://127.0.0.1:8000/v1/assess \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "curl-road-1",
    "claim_type": "road_passable",
    "geometry": {"type": "LineString", "coordinates": [[-8.1165, 53.4916], [-8.1075, 53.4916]]},
    "claimed_at": "2024-04-15T08:00:00Z",
    "source_label": "Synthetic curl road claim",
    "synthetic": true
  }'

# 3. Assess Galileo E27 navigation-message authentication
curl -sS -X POST http://127.0.0.1:8000/v1/assess \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "curl-galileo-e27",
    "claim_type": "gnss_nav_message_authenticated",
    "geometry": null,
    "claimed_at": "2023-08-27T20:10:00Z",
    "source_label": "Synthetic curl Galileo claim",
    "synthetic": true,
    "attributes": {"svid": 27}
  }'
```
