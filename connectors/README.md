# EIP Data Connectors & Provenance (`connectors/` and `sample_data/`)

## Genuine Copernicus Event Selection Rationale

We selected **Copernicus EMS Rapid Mapping Activation `EMSR718`** (*Flood in Ireland*, County Roscommon — **AOI02: Lough Funshinagh**, Delineation Monitoring 01, product `EMSR718_AOI02_DEL_MONIT01_v2`):

- **Why this event:** On 11 April 2024, Lough Funshinagh expanded beyond historical records, threatening homes and **causing documented road closures** in County Roscommon. The activation was triggered by Ireland's National Directorate for Fire and Emergency Management.
- **Actual flood extent (not catalogue footprint):** The vector archive contains 103 delineated flood polygons in `observedEventA_v2.json` (`event_type: 5-Flood`, `notation: Flooded area`), plus documented area-of-interest coverage (`areaOfInterestA_v2.json`) and post-event satellite footprint (`imageFootprintA_v2.json`).
- **Sensor & acquisition timestamp:** Extracted directly from `EMSR718_AOI02_DEL_MONIT01_source_v2.dbf` (`src_id = 4`): **COSMO-SkyMed Second Generation SAR** (`3.0 m` resolution), acquired **`2024-04-15T06:02:08Z`**.
- **Attribution & licence:** Copernicus EMS Rapid Mapping (© European Union, 2024). See https://emergency.copernicus.eu/mapping/ems/cite-copernicus-ems-mapping-portal.

## Exact Retrieval & Reproduction Commands

1. Download the public CEMS vector archive (no credentials required):
   ```bash
   curl -fSL -o sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip \
     "https://rapidmapping.emergency.copernicus.eu/backend/EMSR718/AOI02/DEL_MONIT01/EMSR718_AOI02_DEL_MONIT01_v2.zip"
   ```
2. Verify SHA-256 of the raw ZIP artifact:
   ```bash
   sha256sum sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip
   # Expected: 2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947
   ```
3. Regenerate `sample_data/evidence.json` and `sample_data/example_claims.json` offline from the local raw ZIP:
   ```bash
   ~/dev/venvs/cassini/bin/python -m connectors.cems_rapid_mapping \
     --retrieved-at 2026-11-27T16:00:00Z
   ```
4. Regenerate deterministic synthetic fixtures under `sample_data/fixtures/`:
   ```bash
   ~/dev/venvs/cassini/bin/python -m connectors.fixtures
   ```
5. Run data provenance & integrity tests:
   ```bash
   ~/dev/venvs/cassini/bin/pytest -v tests/data/
   ```

## Synthetic vs. Genuine Distinction & Limitations

- `sample_data/evidence.json` contains genuine Copernicus EMS flood extent (`synthetic: false`).
- `sample_data/example_claims.json` contains **explicitly synthetic** road passability reports (`synthetic: true`) scoped to Lough Funshinagh for historical replay demonstration because no licensed historical road-passability report feed is bundled.
- `sample_data/fixtures/*.json` contains 7 deterministic synthetic fixtures (`synthetic: true`) testing every rule boundary (`fresh_intersection`, `covered_non_intersection`, `stale_observation`, `unknown_observation_time`, `outside_coverage`, `unknown_coverage`, `missing_evidence`).
- **Limitations:** SAR delineation may omit water under tree canopy, bridges, or radar shadow; flood extent does not prove road impassability or water depth; absence of mapped overlap does not prove road safety; SHA-256 proves local byte integrity only and `authentication` remains `"unknown"` (unverified).
