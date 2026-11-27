# Independent Evidence Sources Investigation — Lough Funshinagh (April 2024)

This document records the live research, retrieval attempts, licensing, temporal/geographical relevance, measurement limitations, and source-independence analysis for candidate evidence sources covering the **Lough Funshinagh, County Roscommon** flood event around the existing Copernicus `EMSR718` observation (**15 April 2024, 06:02:08 UTC**).

---

## 1. Existing Baseline Evidence

| Field | Value |
|---|---|
| **Evidence ID** | `cems-emsr718-aoi02-del-monit01-v2` |
| **Original Sensor** | COSMO-SkyMed Second Generation (3.0 m X-band SAR) |
| **Publisher** | Copernicus EMS Rapid Mapping (© European Union, 2024) |
| **Observation Time** | `2024-04-15T06:02:08Z` |
| **Availability Time** | Unknown (`null` — raw ZIP XML contains only date-level Creation `2024-04-16`) |
| **Epistemic Role for `road_passable`** | **Direct** spatial observation of mapped surface water (`flood_extent`, 103 polygons) |
| **Local Raw Artifact & SHA-256** | `sample_data/raw/EMSR718_AOI02_DEL_MONIT01_v2.zip` (`2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947`) |

---

## 2. Candidate Independent Sources Investigated

### A. Geological Survey Ireland (GSI) — Turlough Hydrometric Monitoring (`gwlevel.ie`) — **ACQUIRED & INTEGRATED**
- **Investigated URLs:**
  - Portal & disclaimers: `https://gwlevel.ie/` (`HTTP 200`)
  - Station time-series CSV API: `https://gwlevel.ie/api/download?locNum=00011&clusNum=001&dataType=tl&dataSrc=gs&name=Lough+Funshinagh` (`HTTP 200`, `4,943,962` bytes)
  - Station DataSheet reference: `https://gsi.geodata.gov.ie/downloads/Groundwater/Reports/Turloughs/DataSheet_26171_Lough_Funshinagh_012FUNSGH.pdf`
- **Actual Data Retrieved:**
  - Station **`GSI_11` (`Lough Funshinagh`)**, located directly on Lough Funshinagh at WGS84 `(-8.08494347, 53.49813653)` (inside `EMSR718` AOI02, ~2 km from the eastern flooded basin).
  - Contains **89,451 valid hourly readings** (`2016-08-16` to `2026-11-27`) in documented **UTC** (`[UTC time on x-axis]`, verified continuous across the `2024-03-31` DST boundary).
  - Historical baseline (`mAOD` Malin Head): min `65.30`, median `67.22`, p95 `68.91`, p99 `69.29`, all-time max `69.38` (2024-04-20).
  - Reading at **`2024-04-15T06:00:00Z`** (2 minutes before the COSMO-SkyMed overpass): **`69.37 mAOD`** (`+2.15 m` above median, above the 99th percentile, within `0.01 m` of the 10-year peak).
- **Licensing & Attribution:** Open data licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**, Copyright Government of Ireland / Geological Survey Ireland (verified verbatim on `gwlevel.ie`).
- **Independence from `EMSR718`:** **Fully independent.** Different physical instrument (submerged in-situ pressure transducer at `63.5 mAOD`), different operator/publisher (Geological Survey Ireland), zero shared satellite/SAR pipelines or upstream datasets.
- **Epistemic Role & Limitations:**
  - **Direct** observation of Lough Funshinagh water stage (`hydrometric_water_level`); **indirect contextual evidence** for any specific road segment (`road_passable`) — cannot prove a particular road was flooded.
  - GSI explicitly classifies `gwlevel.ie` readings as **provisional and unchecked** (subject to sensor drift, silt/debris, or telemetry delays).
  - Uploaded online once daily; exact historical `available_at` timestamp is **unknown (`null`)**.
- **Preserved Artifact:** `sample_data/raw/GSI_11_Lough_Funshinagh.csv`
  - **SHA-256:** `89a136da9802d7ee055431d6e4e63d0298715785de11e2ddbf4e365419cfa3d3`
  - **Authentication:** `unknown` (unverified; SHA-256 confirms local byte integrity only).

---

### B. Met Éireann — Historical Daily Synoptic Weather (`clidata.met.ie`) — **ACQUIRED & INTEGRATED**
- **Investigated URL:** `https://clidata.met.ie/cli/climate_data/webdata/dly1975.csv` (`HTTP 200`, `741,508` bytes; `Last-Modified: Sat, 14 Nov 2026 15:46:35 GMT`)
- **Actual Data Retrieved:**
  - Station **`1975` (`MT DILLON`)**, County Roscommon (`53.727°N, -7.981°W`, elevation `39 m`, ~27 km NNE of Lough Funshinagh).
  - Explicitly documented as daily `00 to 00 UTC` observations in the CSV header.
  - Precipitation around 15 April 2024: `10.6 mm` (11 Apr), `3.8 mm` (12 Apr), `1.7 mm` (13 Apr), `4.5 mm` (14 Apr), **`6.1 mm` (15 Apr 2024)** → **`26.7 mm`** 5-day cumulative rainfall.
- **Licensing & Attribution:** Open data licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**, Met Éireann.
- **Independence from `EMSR718` & `GSI_11`:** **Fully independent** meteorological rain gauge operated by Met Éireann; zero shared upstream sensors or publishers.
- **Epistemic Role & Limitations:**
  - Strictly **indirect environmental indicator** (`meteorological_rainfall`); regional daily precipitation ~27 km away cannot prove flooding on a specific road segment and does not capture karst groundwater lag.
  - Exact historical per-row `available_at` timestamp is not embedded in the CSV and remains **unknown (`null`)**.
- **Preserved Artifact:** `sample_data/raw/MetEireann_MtDillon_dly1975.csv`
  - **SHA-256:** `8318023567c25839d291cc5291060f340b453cb612236f64fc6324edb1591744`
  - **Authentication:** `unknown`.

---

### C. OPW Hydrometric & Historical Flood Portals (`waterlevel.ie`, `floodinfo.ie`) — **INVESTIGATED, NOT SELECTED**
- **Investigated URLs & Live Results:**
  - `https://waterlevel.ie/geojson/latest/` (`HTTP 200`, `742,978` bytes) — inspected all stations within `[-8.5..-7.8, 53.3..53.7]`.
  - Nearest OPW stations are on the River Suck / surrounding catchments (`0000026005` Derrycahill `[-8.2628, 53.4318]`, `0000026002` Rookwood `[-8.2927, 53.5637]`, `0000026001` Ballinamore `[-8.3660, 53.4898]`, `0000026007` Bellagill `[-8.2386, 53.3617]`), **not** on Lough Funshinagh itself (because karstic turlough monitoring at Lough Funshinagh is operated by GSI on `gwlevel.ie`).
  - `https://waterlevel.ie/data/day/26005_0001.csv` (`HTTP 200`) returns only recent rolling 24h telemetry (`2026-11-26`), while `https://waterlevel.ie/hydro-data/stations/26005/Parameter/S/complete.zip` returned **`HTTP 404`**.
- **Conclusion:** OPW `waterlevel.ie` lacks a gauge on Lough Funshinagh itself and did not provide a direct unauthenticated April 2024 historical archive URL for nearby stations. GSI `gwlevel.ie` (`GSI_11`) directly monitors Lough Funshinagh with full April 2024 hourly data and is therefore strictly superior.

---

### D. Roscommon County Council Road Closure Notices (`roscommoncoco.ie`) — **INVESTIGATED, UNSTRUCTURED / NOT AUTOMATED**
- **Investigated URLs & Live Results:**
  - `https://www.roscommoncoco.ie/en/news-events/latest-news/lough-funshinagh-update.html` → **`HTTP 404`**.
  - `https://www.roscommoncoco.ie/en/services/roads/road-closures/` → `HTTP 200` (`85,865` bytes, current active HTML notices rather than structured historical April 2024 GeoJSON/CSV archive).
  - Public news & council archives confirm local road **L-2005 (Ballagh)** was closed from 19 February 2024 and regional road **R362 (Coolnageer, Curraghboy)** was closed from 12 April 2024 due to Lough Funshinagh flooding, but no machine-readable, georeferenced, openly licensed historical road-closure dataset was available from the council portal for automated ingestion.
- **Conclusion:** Documented as historical context only; not fabricated into synthetic "council" evidence. Road passability claims remain explicitly marked `synthetic: true`.

---

### E. Copernicus Data Space Ecosystem (CDSE) STAC — Sentinel-1 / Sentinel-2 — **INVESTIGATED, NOT PROCESSED FLOOD EXTENT**
- **Investigated URL & Live Result:**
  - `POST https://stac.dataspace.copernicus.eu/v1/search` (`bbox: [-8.24, 53.45, -8.05, 53.54]`, `2024-04-12` to `2024-04-18`) → **`HTTP 200`**.
  - Discovered real acquisitions:
    - `S1A_IW_GRDH_1SDV_20240415T181522_20240415T181547_053448_067BF6_C31E_COG` (**Sentinel-1A** C-band SAR, `2024-04-15T18:15:22Z`)
    - `S1A_IW_GRDH_1SDV_20240417T064737_...` (Sentinel-1A, `2024-04-17T06:47:37Z`)
    - `S2A_MSIL2A_20240414T114351_...` (`100.0%` cloud cover), `S2A_MSIL2A_20240417T115401_...` (`98.26%` cloud cover), `S2B_MSIL2A_20240412T115359_...` (`99.96%` cloud cover)
- **Why Not Ingested as Flood Extent:**
  1. Sentinel-2 optical acquisitions over Lough Funshinagh during 12–17 April 2024 had `98.3%–100%` cloud cover (unusable for optical water delineation).
  2. CDSE STAC search is unauthenticated for catalogue metadata only; downloading raw Sentinel-1 GRD rasters requires CDSE credentials, and raw SAR backscatter requires calibrated flood-delineation processing. Per EIP rules, catalogue footprints are **never** equated with flood extent.

---

### F. Copernicus EMS `EMSR718_AOI02_DEL_PRODUCT_v2.zip` (14 April 2024) — **INVESTIGATED (NON-INDEPENDENT PUBLISHER/PIPELINE)**
- **Investigated URL & Live Result:** `https://rapidmapping.emergency.copernicus.eu/backend/EMSR718/AOI02/DEL_PRODUCT/EMSR718_AOI02_DEL_PRODUCT_v2.zip` (`HTTP 200`).
- **Actual Metadata Inspected:** Contains `92` flood features derived from `COSMO-SkyMed` (`2024-04-14T05:55:58Z`, `src_id=2`) and `PAZ-1` (`2024-04-14T06:51:33Z`, `src_id=3`), published by the **same organisation** (`Copernicus EMS Rapid Mapping`) using the **same** semi-automatic extraction pipeline and overlapping `COSMO-SkyMed` constellation.
- **Conclusion:** Not treated as independent from `EMSR718_AOI02_DEL_MONIT01_v2`; illustrates why distinct product files from the same activation/publisher must not be mistaken for independent corroboration.

---

## 3. Summary Independence Matrix (Integrated Genuine Sources)

| Evidence ID | Publisher | Original Sensor | Kind | Epistemic Role (`road_passable`) | Shared Upstream Dependencies |
|---|---|---|---|---|---|
| `cems-emsr718-aoi02-del-monit01-v2` | Copernicus EMS Rapid Mapping | COSMO-SkyMed 2nd Gen (3 m SAR) | `flood_extent` | **Direct** | None with GSI / Met Éireann |
| `gsi-gwlevel-gsi-11-20240415t0600z` | Geological Survey Ireland | GSI-11 Submerged Pressure Transducer | `hydrometric_water_level` | **Indirect contextual** | None with CEMS / Met Éireann |
| `met-eireann-1975-20240415` | Met Éireann | Synoptic Station 1975 (Mt Dillon) Rain Gauge | `meteorological_rainfall` | **Indirect contextual** | None with CEMS / GSI |

Together, these form **`3` distinct declared independent source groups** (`distinct_declared_sources`, `independent_group_count = 3`), with **1 direct** spatial flood observation and **2 independent indirect** ground-level environmental observations.
