# EIP Shared Contract v0.2 (Backward Compatible with v0.1)

Authoritative interface for Evidence Integrity Platform (EIP) `v0.2.0`. Preserves full wire compatibility with Contract `v0.1` (archived at `cassini-briefs/CONTRACT.md`) while generalizing Evidence, Claim, Assessment, and Discovery for domain-independent assessment policies.

All JSON payloads are UTF-8. All timestamps are timezone-aware UTC ISO 8601 (`Z` or explicit offset; naive timestamps are rejected with HTTP `422`). Spatial geometries use WGS84 GeoJSON `[longitude, latitude]` when present; non-geographical domains may set `geometry: null`.

---

## 1. Endpoints

| Method | Path | Contract | Purpose |
|---|---|---|---|
| `GET` | `/health` | v0.1 / v0.2 | Health check: `{"status": "ok", "contract_version": "0.1"}` (retained for v0.1 client compatibility) |
| `GET` | `/v1/capabilities` | **v0.2 (new)** | Discover contract versions (`["0.1", "0.2"]`), `supported_claim_types`, `supported_evidence_kinds`, `registered_policy_ids`, and `assessment_modes` |
| `GET` | `/v1/policies` | **v0.2 (new)** | List full `PolicySpec` definitions for all registered assessment policies |
| `GET` | `/v1/evidence` | v0.1 / v0.2 | Return `{"items": [Evidence, ...]}` from the configured `EvidenceStore` (`EIP_EVIDENCE_PATH`, default `sample_data/evidence.json`) |
| `POST` | `/v1/assess` | v0.1 / v0.2 | Dispatch a `ClaimRequest` to the matching registered policy and return deterministic `AssessmentResponse` (plus `X-EIP-Assessed-At` UTC response header) |
| `GET` | `/openapi.json` | v0.1 / v0.2 | Auto-generated OpenAPI schema |

CORS is restricted to `http://localhost:5173` and `http://127.0.0.1:5173`. No live external network calls occur during assessment.

---

## 2. Six Explicit Timestamps & Temporal Modes

EIP v0.2 explicitly separates six timestamps:

| Timestamp | Location | Meaning |
|---|---|---|
| `observed_at` | `Evidence` (nullable) | When the physical observation or measurement occurred |
| `available_at` | `Evidence` (nullable, **new v0.2**) | When the evidence was published or became demonstrably available to decision-makers |
| `retrieved_at` | `Evidence` (nullable) | When EIP ingested/retrieved the artefact |
| `claimed_at` | `ClaimRequest` (required) | The timestamp the claim pertains to |
| `decision_time` | `ClaimRequest` (nullable, **new v0.2**) | Required when `assessment_mode == "decision_time"`; the time of the decision under review |
| `assessed_at` | `ClaimRequest` / `traceability` / `X-EIP-Assessed-At` (**new v0.2**) | When EIP ran the assessment (`assessed_at` in JSON is caller-supplied for deterministic replay; `X-EIP-Assessed-At` header records server execution UTC time) |

### Assessment Modes
- **`retrospective` (default — preserves v0.1):** Evaluates historical claims using subsequently available evidence within the policy's temporal window.
- **`decision_time`:** Evaluates a claim using **only** evidence demonstrably observed (`observed_at <= decision_time`) AND available (`available_at <= decision_time`) at `decision_time`.
  - Evidence observed or published after `decision_time` is excluded with reason `NOT_AVAILABLE_AT_DECISION_TIME`.
  - Evidence with `available_at: null` is excluded with reason `AVAILABILITY_TIME_UNKNOWN` and explicitly flagged in `temporal_context.unknown_availability_ids` and `limitations`.
  - Omitting `decision_time` when `assessment_mode == "decision_time"` returns HTTP `422`.

---

## 3. Evidence Schema (v0.2, Superset of v0.1)

All v0.1 Evidence objects remain valid unchanged. New v0.2 fields are optional with safe defaults:

```json
{
  "id": "cems-emsr718-aoi02-del-monit01-v2",
  "source": "copernicus_ems_rapid_mapping",
  "product_id": "EMSR718_AOI02_DEL_MONIT01_v2",
  "source_url": "https://rapidmapping.emergency.copernicus.eu/...",
  "observed_at": "2024-04-15T06:02:08Z",
  "available_at": null,
  "retrieved_at": "2026-11-27T16:00:00Z",
  "kind": "flood_extent",
  "geometry": { "type": "MultiPolygon", "coordinates": [...] },
  "coverage": { "type": "Polygon", "coordinates": [...] },
  "attributes": { "sensor_name": "COSMO-SkyMed" },
  "provenance": {
    "original_source": "COSMO-SkyMed",
    "publishing_organisation": "Copernicus EMS Rapid Mapping",
    "upstream_datasets": ["EMSR718_AOI02_DEL_MONIT01_v2"],
    "derived_from": [],
    "measurement_method": "SAR semi-automatic flood extraction",
    "shared_dependencies": []
  },
  "authentication": "unknown",
  "sha256": "2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947",
  "raw_path": "sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip",
  "licence": "Copernicus EMS Rapid Mapping (© European Union, 2024); ...",
  "limitations": ["..."],
  "synthetic": false
}
```

- `kind` is an open non-empty string (dispatched via registered policy relevance rules).
- `geometry` is optional (`Point`, `LineString`, `Polygon`, `MultiPolygon`, or `null` for non-geographical domains). When present, it is strictly validated in WGS84.
- `authentication` enum: `"unknown" | "verified" | "failed"`. Failed-auth items are excluded with `AUTHENTICATION_FAILED`.
- `sha256` hashes raw artefact bytes (local byte integrity only, never source authenticity).
- `raw_path` must be a safe local relative path (no URLs or `..` traversal).

---

## 4. ClaimRequest Schema (v0.2, Superset of v0.1)

```json
{
  "claim_id": "road-1",
  "claim_type": "road_passable",
  "geometry": { "type": "LineString", "coordinates": [[-7.745, 54.955], [-7.725, 54.955]] },
  "claimed_at": "2026-01-01T12:00:00Z",
  "source_label": "Synthetic road report",
  "synthetic": true,
  "attributes": {},
  "assessment_mode": "retrospective",
  "decision_time": null,
  "assessed_at": null,
  "policy_id": null
}
```

- All v0.1 request payloads omit the 5 optional v0.2 fields (`attributes`, `assessment_mode`, `decision_time`, `assessed_at`, `policy_id`) and behave identically.
- Unknown extra fields are rejected (`extra="forbid"`, HTTP `422`).
- Unsupported `claim_type` returns HTTP `422` with `detail.error == "unsupported_claim_type"` and `detail.supported_claim_types`.
- Unknown `policy_id` returns HTTP `422` with `detail.error == "unknown_policy"` and `detail.registered_policy_ids`.
- Policy-specific validation errors (e.g., non-`LineString` geometry for `road_passable`) return HTTP `422` with `detail.error == "claim_validation_error"`.

---

## 5. AssessmentResponse Schema (v0.2, Superset of v0.1)

All v0.1 response fields are preserved verbatim (including exact 4-key `findings` entries):

```json
{
  "claim_id": "road-1",
  "status": "potential_conflict",
  "policy_version": "flood-road-0.1",
  "reasons": ["FLOOD_EXTENT_INTERSECTS"],
  "evidence_ids": ["fixture-flood-1"],
  "findings": [
    {
      "evidence_id": "fixture-flood-1",
      "status": "potential_conflict",
      "age_hours": 2.0,
      "reasons": ["FLOOD_EXTENT_INTERSECTS"]
    }
  ],
  "limitations": ["..."],
  "synthetic": true,
  "assessment_mode": "retrospective",
  "temporal_context": {
    "assessment_mode": "retrospective",
    "claimed_at": "2026-01-01T12:00:00Z",
    "decision_time": null,
    "assessed_at": null,
    "excluded_not_available_ids": [],
    "unknown_availability_ids": []
  },
  "independence": {
    "status": "single_source",
    "assessed_source_count": 1,
    "independent_group_count": 1,
    "correlated_groups": [["fixture-flood-1"]],
    "shared_dependencies": [],
    "notes": ["..."]
  },
  "traceability": {
    "policy_id": "flood-road",
    "policy_version": "flood-road-0.1",
    "input_fingerprint": "<64-char sha256>",
    "assessed_at": null
  }
}
```

### Core Engine Reason Codes
In addition to policy-defined reason codes (such as `FLOOD_EXTENT_INTERSECTS`, `NO_MAPPED_OVERLAP`, `OBSERVATION_STALE`, `OBSERVATION_TIME_UNKNOWN`, `COVERAGE_UNKNOWN`, `OUTSIDE_COVERAGE`, and optional indirect contextual codes `CONTEXTUAL_WATER_LEVEL_ELEVATED`, `CONTEXTUAL_WATER_LEVEL_NORMAL`, `CONTEXTUAL_RAINFALL_OBSERVED`, `CONTEXTUAL_RAINFALL_LOW`, `INDIRECT_EVIDENCE_ONLY` in `flood-road-0.1`), the generic engine may emit:
- `NO_EVIDENCE`
- `AUTHENTICATION_FAILED`
- `NOT_AVAILABLE_AT_DECISION_TIME`
- `AVAILABILITY_TIME_UNKNOWN`

### Direct vs. Indirect Contextual Evidence (v0.3)
- Policies declare `required_evidence_kinds` (direct observations) separately from `optional_evidence_kinds` (indirect contextual observations, e.g. `hydrometric_water_level` and `meteorological_rainfall` in `flood-road`).
- Per-source findings for indirect contextual observations use statuses `contextual_support` or `contextual_neutral` and **never** alone produce `potential_conflict` or `no_mapped_overlap` for a specific road segment. If only indirect observations qualify, the overall status remains `insufficient_evidence` with `INDIRECT_EVIDENCE_ONLY`.

### Source Independence Statuses
- `single_source` — 1 evidence source evaluated.
- `shared_dependencies_detected` — 2+ sources share an `original_source`, `upstream_datasets`, `derived_from` lineage, `shared_dependencies`, or `product_id`; grouped into `correlated_groups` so derived products never count as independent corroboration.
- `distinct_declared_sources` — all sources declare lineage with zero detected overlap (still notes undeclared correlations cannot be ruled out).
- `unknown` — 0 sources, or 2+ sources where at least one lacks declared provenance (`independent_group_count: null`).

---

## 6. Summary of v0.1 → v0.2 Changes

- **Additive & backward-compatible:** Every v0.1 request and Evidence JSON remains valid. Existing `flood-road-0.1` outcomes, reason codes, and dashboard behaviour are unchanged.
- **New discovery routes:** `GET /v1/capabilities` and `GET /v1/policies`.
- **New optional fields:** `Evidence.available_at`, `Evidence.attributes`, `Evidence.provenance`; `ClaimRequest.attributes`, `assessment_mode`, `decision_time`, `assessed_at`, `policy_id`; `AssessmentResponse.assessment_mode`, `temporal_context`, `independence`, `traceability`.
- **New header:** `X-EIP-Assessed-At` on `POST /v1/assess` responses.
