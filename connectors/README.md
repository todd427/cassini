# EIP Data Connectors & Provenance (`connectors/` and `sample_data/`)

All connectors implement `connectors.base.EvidenceConnector` (`metadata`, `load_evidence() -> list[Evidence]`) without requiring changes to `core/`.

---

## Integrated Genuine Evidence Sources (Lough Funshinagh — 15 April 2024)

| Connector | Source & Product | Observed (UTC) | Available (UTC) | Role (`road_passable`) | Raw Artifact & SHA-256 | Licence |
|---|---|---|---|---|---|---|
| `connectors/cems_rapid_mapping.py` | Copernicus EMS `EMSR718_AOI02_DEL_MONIT01_v2` (COSMO-SkyMed 3.0 m SAR) | `2024-04-15T06:02:08Z` | `null` (unknown) | **Direct** (`flood_extent`, 103 polygons) | `sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip`<br>`2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947` | Copernicus EMS Rapid Mapping (© EU, 2024) |
| `connectors/gsi_gwlevel.py` | Geological Survey Ireland `GSI_11` Lough Funshinagh (in-situ pressure transducer, `69.37 mAOD`) | `2024-04-15T06:00:00Z` | `null` (unknown; uploaded daily) | **Indirect contextual** (`hydrometric_water_level`) | `sample_data/raw/GSI_11_Lough_Funshinagh.csv`<br>`89a136da9802d7ee055431d6e4e63d0298715785de11e2ddbf4e365419cfa3d3` | CC BY 4.0 (GSI / Govt. of Ireland) |
| `connectors/met_eireann.py` | Met Éireann Station `1975` Mount Dillon (`6.1 mm`/day, `26.7 mm` 5-day) | `2024-04-15T00:00:00Z` | `null` (unknown) | **Indirect contextual** (`meteorological_rainfall`) | `sample_data/raw/MetEireann_MtDillon_dly1975.csv`<br>`8318023567c25839d291cc5291060f340b453cb612236f64fc6324edb1591744` | CC BY 4.0 (Met Éireann) |

See `docs/EVIDENCE-SOURCES.md` for full source research, rejected/blocked candidates, and independence analysis.

---

## Exact Retrieval & Offline Regeneration Commands

1. Download the three public raw artifacts (no credentials required):
   ```bash
   curl -fSL -o sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip \
     "https://rapidmapping.emergency.copernicus.eu/backend/EMSR718/AOI02/DEL_MONIT01/EMSR718_AOI02_DEL_MONIT01_v2.zip"

   curl -fSL -o sample_data/raw/GSI_11_Lough_Funshinagh.csv \
     "https://gwlevel.ie/api/download?locNum=00011&clusNum=001&dataType=tl&dataSrc=gs&name=Lough+Funshinagh"

   curl -fSL -o sample_data/raw/MetEireann_MtDillon_dly1975.csv \
     "https://clidata.met.ie/cli/climate_data/webdata/dly1975.csv"
   ```
2. Verify all three raw SHA-256 checksums:
   ```bash
   sha256sum sample_data/raw/*
   ```
3. Regenerate `sample_data/evidence.json`, `sample_data/example_claims.json`, and `sample_data/scenarios/*.json` completely offline:
   ```bash
   ~/dev/venvs/cassini/bin/python -m connectors.build_evidence_bundle
   ```
4. Regenerate v0.1 deterministic synthetic fixtures under `sample_data/fixtures/`:
   ```bash
   ~/dev/venvs/cassini/bin/python -m connectors.fixtures
   ```
5. Run data provenance & multi-source tests:
   ```bash
   ~/dev/venvs/cassini/bin/pytest -v tests/data/ tests/core/test_v03_multisource.py
   ```
