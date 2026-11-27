# EIP shared contract v0.1
Freeze before parallel work. JSON UTF-8, UTC ISO 8601 timestamps (nullable when unknown), WGS84 GeoJSON longitude/latitude. No untyped free-text assessment. Data connector writes `sample_data/evidence.json` as an array of Evidence objects; fixtures under `sample_data/fixtures/`. All IDs unique; path references local relative paths only, no arbitrary URL fetching. Geometry embedded for weekend demo; simplify only for display, not evaluation.

## Evidence example (synthetic geometry and metadata)
```json
{
  "id": "fixture-flood-1",
  "source": "fixture",
  "product_id": null,
  "source_url": null,
  "observed_at": "2026-01-01T10:00:00Z",
  "retrieved_at": "2026-01-02T10:00:00Z",
  "kind": "flood_extent",
  "geometry": {"type":"Polygon","coordinates":[[[-7.74,54.95],[-7.73,54.95],[-7.73,54.96],[-7.74,54.96],[-7.74,54.95]]]},
  "coverage": null,
  "authentication": "unknown",
  "sha256": null,
  "raw_path": null,
  "licence": null,
  "limitations": ["Synthetic fixture, not an actual flood"],
  "synthetic": true
}
```
`coverage` is a Polygon/MultiPolygon indicating documented valid observation coverage, or null; never infer from bounding box. `geometry` Polygon/MultiPolygon for flood extent. Authentication enum unknown/verified/failed; only mark verified with documented method. SHA-256 hashes raw file, not JSON geometry. Unknown licence, product ID or source URL may be null; real demo requires documented provenance and permission.

## Endpoints
`GET /health` → `{ "status":"ok", "contract_version":"0.1" }`
`GET /v1/evidence` → `{ "items": [Evidence, ...] }`
`POST /v1/assess` accepts:
```json
{
  "claim_id":"road-1",
  "claim_type":"road_passable",
  "geometry":{"type":"LineString","coordinates":[[-7.745,54.955],[-7.725,54.955]]},
  "claimed_at":"2026-01-01T12:00:00Z",
  "source_label":"Synthetic road report",
  "synthetic":true
}
```
Returns HTTP 200 with:
```json
{
  "claim_id":"road-1",
  "status":"potential_conflict",
  "policy_version":"flood-road-0.1",
  "reasons":["FLOOD_EXTENT_INTERSECTS"],
  "evidence_ids":["fixture-flood-1"],
  "findings":[{"evidence_id":"fixture-flood-1","status":"potential_conflict","age_hours":2.0,"reasons":["FLOOD_EXTENT_INTERSECTS"]}],
  "limitations":["Mapped flood overlap does not establish road impassability."],
  "synthetic":true
}
```
Statuses: potential_conflict, no_mapped_overlap, insufficient_evidence. No safe/true/false status. `age_hours` absolute difference between acquisition and claim timestamp, null if unknown; sign/dates visible in UI. Historical replay accepts observations before or after claim within 24h; no claim of contemporaneous knowledge. For overlap, require valid observation geometry and known time within 24h; if known coverage excludes claim entirely, insufficient. For no overlap, require entire road covered by documented coverage and fresh observation. If multiple observations: potential_conflict takes precedence; otherwise no_mapped_overlap only if at least one qualifying covered observation; otherwise insufficient. Report per-source findings and stale/unknown sources; never call correlated sources independent. `synthetic` true if claim or any assessed evidence synthetic. Failed-auth evidence excluded with reason. Unknown auth remains explicitly unverified.

Reason codes: FLOOD_EXTENT_INTERSECTS, NO_MAPPED_OVERLAP, OBSERVATION_STALE, OBSERVATION_TIME_UNKNOWN, COVERAGE_UNKNOWN, OUTSIDE_COVERAGE, NO_EVIDENCE, AUTHENTICATION_FAILED. Additional codes require contract agreement. Geometry invalid/unsupported, naive timestamps or malformed payload → HTTP 422. Empty dataset → insufficient_evidence. Core supplies OpenAPI automatically. CORS restricted to localhost dev UI port 5173. API port 8000, UI 5173. Frontend uses `VITE_API_BASE_URL` default `http://localhost:8000`. Backend reads `EIP_EVIDENCE_PATH` default `sample_data/evidence.json` relative to repo root. No live network needed during assessment.
