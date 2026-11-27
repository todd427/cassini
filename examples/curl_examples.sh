#!/usr/bin/env bash
# Language-agnostic curl examples for integrating with the EIP REST API.
# Requires a running local EIP server (default: http://127.0.0.1:8000).
set -euo pipefail

BASE_URL="${EIP_API_URL:-http://127.0.0.1:8000}"

echo "=== 1. Health check (GET /health) ==="
curl -sS "${BASE_URL}/health"
echo ""

echo "=== 2. Capabilities discovery (GET /v1/capabilities) ==="
curl -sS "${BASE_URL}/v1/capabilities"
echo ""

echo "=== 3. Registered policies (GET /v1/policies) ==="
POLICIES_JSON="$(curl -sS "${BASE_URL}/v1/policies")"
echo "${POLICIES_JSON:0:450}... (truncated)"

echo "=== 4. Environmental claim assessment (POST /v1/assess) ==="
curl -sS -X POST "${BASE_URL}/v1/assess" \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "curl-env-ballagh-east",
    "claim_type": "road_passable",
    "geometry": {
      "type": "LineString",
      "coordinates": [[-8.1165, 53.4916], [-8.1075, 53.4916]]
    },
    "claimed_at": "2024-04-15T08:00:00Z",
    "source_label": "Synthetic curl road claim (Lough Funshinagh East)",
    "synthetic": true
  }'
echo ""

echo "=== 5. Galileo OSNMA navigation auth assessment (POST /v1/assess) ==="
curl -sS -X POST "${BASE_URL}/v1/assess" \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "curl-galileo-e27",
    "claim_type": "gnss_nav_message_authenticated",
    "geometry": null,
    "claimed_at": "2023-08-27T20:10:00Z",
    "source_label": "Synthetic curl Galileo E27 navigation auth claim",
    "synthetic": true,
    "attributes": {"svid": 27}
  }'
echo ""

echo "=== 6. Decision-time audit (POST /v1/assess, mode=decision_time) ==="
curl -sS -X POST "${BASE_URL}/v1/assess" \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "curl-decision-time-audit",
    "claim_type": "road_passable",
    "geometry": {
      "type": "LineString",
      "coordinates": [[-8.1165, 53.4916], [-8.1075, 53.4916]]
    },
    "claimed_at": "2024-04-15T08:00:00Z",
    "decision_time": "2024-04-15T08:00:00Z",
    "assessment_mode": "decision_time",
    "source_label": "Synthetic curl decision-time audit claim",
    "synthetic": true
  }'
echo ""

echo "=== 7. Assessment with API-derived evidence graph (POST /v1/assess/graph) ==="
GRAPH_JSON="$(curl -sS -X POST "${BASE_URL}/v1/assess/graph" \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "curl-graph-demo",
    "claim_type": "road_passable",
    "geometry": {
      "type": "LineString",
      "coordinates": [[-8.1165, 53.4916], [-8.1075, 53.4916]]
    },
    "claimed_at": "2024-04-15T08:00:00Z",
    "source_label": "Synthetic curl graph claim",
    "synthetic": true
  }')"
echo "${GRAPH_JSON:0:450}... (truncated)"
