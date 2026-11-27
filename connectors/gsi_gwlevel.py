"""Geological Survey Ireland (GSI) gwlevel.ie hydrometric connector for EIP.

Processes a genuine downloaded GSI groundwater/turlough hourly stage CSV
(e.g. sample_data/raw/GSI_11_Lough_Funshinagh.csv) into a validated EIP
Evidence object implementing `connectors.base.EvidenceConnector`.

Provenance & integrity rules:
- SHA-256 hashes the raw downloaded CSV file (local byte integrity only).
- Timestamps in gwlevel.ie CSVs are documented as UTC (`[UTC time on x-axis]`).
- Historical stage percentiles (min, median, p95, p99, max) are computed directly
  from the genuine CSV archive — never invented.
- `available_at` remains `None` because gwlevel.ie states data are uploaded
  once daily without recording exact per-row publication UTC timestamps.
- `authentication` remains `"unknown"`.
- A point turlough water-level reading is a DIRECT observation of lake stage
  and an INDIRECT contextual indicator for road-segment passability.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from connectors.base import ConnectorMetadata
from core.integrity import compute_file_sha256
from core.models import Evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GSI_RAW_CSV = REPO_ROOT / "sample_data" / "raw" / "GSI_11_Lough_Funshinagh.csv"
DEFAULT_GSI_SOURCE_URL = (
    "https://gwlevel.ie/api/download"
    "?locNum=00011&clusNum=001&dataType=tl&dataSrc=gs&name=Lough+Funshinagh"
)
DEFAULT_GSI_DATASHEET_URL = (
    "https://gsi.geodata.gov.ie/downloads/Groundwater/Reports/Turloughs/"
    "DataSheet_26171_Lough_Funshinagh_012FUNSGH.pdf"
)
# Official WGS84 station coordinates from gwlevel.ie station registry (GSI-11)
LOUGH_FUNSHINAGH_LON = -8.08494347
LOUGH_FUNSHINAGH_LAT = 53.49813653


def _parse_gsi_utc(raw_dt: str) -> datetime:
    return datetime.strptime(raw_dt.strip(), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        raise ValueError("Cannot compute percentile of empty series.")
    idx = min(int(len(sorted_vals) * pct), len(sorted_vals) - 1)
    return sorted_vals[idx]


def extract_gsi_stage_evidence(
    raw_csv_path: Path = DEFAULT_GSI_RAW_CSV,
    target_utc: str = "2024-04-15T06:00:00Z",
    source_url: str = DEFAULT_GSI_SOURCE_URL,
    retrieved_at: str = "2026-11-27T16:44:00Z",
    station_lon: float = LOUGH_FUNSHINAGH_LON,
    station_lat: float = LOUGH_FUNSHINAGH_LAT,
) -> dict[str, Any]:
    """Parse a GSI gwlevel.ie hourly CSV and extract one validated Evidence dict."""
    resolved = raw_csv_path.resolve()
    sha256_hex = compute_file_sha256(resolved)
    rel_raw_path = resolved.relative_to(REPO_ROOT).as_posix()

    target_dt = datetime.fromisoformat(target_utc.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )

    all_stages: list[float] = []
    matched_row: dict[str, Any] | None = None
    station_name = ""
    station_code = ""

    with resolved.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            dt_raw = (row.get("Date/Time") or "").strip()
            stage_raw = (row.get("Stage (mAOD)") or "").strip()
            elev_raw = (row.get("log_elev (mAOD)") or "").strip()
            if not station_name and row.get("name"):
                station_name = row["name"].strip()
            if not station_code and row.get("code"):
                station_code = row["code"].strip()
            if not dt_raw or not stage_raw or stage_raw.lower() == "nan":
                continue
            try:
                stage_val = float(stage_raw)
            except ValueError:
                continue
            if stage_val != stage_val:  # NaN guard
                continue
            all_stages.append(stage_val)
            dt = _parse_gsi_utc(dt_raw)
            if dt == target_dt:
                try:
                    log_elev = float(elev_raw)
                except ValueError:
                    log_elev = None
                matched_row = {
                    "observed_at": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "stage_maod": stage_val,
                    "logger_elevation_maod": log_elev,
                }

    if matched_row is None:
        raise ValueError(
            f"Target UTC timestamp {target_utc} not found with valid stage in {raw_csv_path}."
        )
    if not all_stages:
        raise ValueError(f"No valid stage values found in {raw_csv_path}.")

    all_stages.sort()
    hist_min = all_stages[0]
    hist_median = _percentile(all_stages, 0.50)
    hist_p95 = _percentile(all_stages, 0.95)
    hist_p99 = _percentile(all_stages, 0.99)
    hist_max = all_stages[-1]
    stage_val = float(matched_row["stage_maod"])

    slug_time = target_dt.strftime("%Y%m%dt%H%Mz")
    slug_code = (station_code or "gsi").lower().replace("_", "-")
    evidence_dict: dict[str, Any] = {
        "id": f"gsi-gwlevel-{slug_code}-{slug_time}",
        "source": "gsi_gwlevel",
        "product_id": f"{station_code}_{station_name.replace(' ', '_')}",
        "source_url": source_url,
        "observed_at": matched_row["observed_at"],
        "available_at": None,
        "retrieved_at": retrieved_at,
        "kind": "hydrometric_water_level",
        "geometry": {
            "type": "Point",
            "coordinates": [station_lon, station_lat],
        },
        "coverage": None,
        "attributes": {
            "evidence_role": "indirect_contextual",
            "station_code": station_code,
            "station_name": station_name,
            "stage_maod": stage_val,
            "datum": "Malin Head (mAOD)",
            "logger_elevation_maod": matched_row["logger_elevation_maod"],
            "historical_reading_count": len(all_stages),
            "historical_min_maod": hist_min,
            "historical_median_maod": hist_median,
            "historical_p95_maod": hist_p95,
            "historical_p99_maod": hist_p99,
            "historical_max_maod": hist_max,
            "above_historical_p95": stage_val >= hist_p95,
            "above_historical_p99": stage_val >= hist_p99,
            "datasheet_url": DEFAULT_GSI_DATASHEET_URL,
        },
        "provenance": {
            "original_source": f"{station_code} Submerged Pressure Transducer ({station_name})",
            "publishing_organisation": "Geological Survey Ireland",
            "upstream_datasets": [f"{station_code}_{station_name.replace(' ', '_')}_hourly_stage"],
            "derived_from": [],
            "measurement_method": "In-situ submerged pressure transducer (hourly stage in mAOD Malin Head)",
            "shared_dependencies": [],
        },
        "authentication": "unknown",
        "sha256": sha256_hex,
        "raw_path": rel_raw_path,
        "licence": (
            "Creative Commons Attribution 4.0 International (CC BY 4.0) — "
            "Geological Survey Ireland, Government of Ireland (https://gwlevel.ie/)"
        ),
        "limitations": [
            "Point water-level gauge directly measures Lough Funshinagh stage (mAOD), which is indirect contextual evidence for road passability and cannot establish whether a specific road segment was inundated.",
            "GSI gwlevel.ie data are published as provisional and unchecked; instrument drift, debris/silt, or telemetry delays may occur.",
            "Data are recorded hourly in UTC and uploaded online once daily; exact publication timestamp (available_at) for this historical reading is unknown (null).",
            "Raw CSV SHA-256 confirms local byte integrity only; source cryptographic authentication is unknown (unverified).",
        ],
        "synthetic": False,
    }

    validated = Evidence.model_validate(evidence_dict)
    return validated.model_dump(mode="json")


class GsiGwlevelConnector:
    """EvidenceConnector implementation for GSI gwlevel.ie hourly stage CSVs."""

    def __init__(
        self,
        raw_csv_path: Path = DEFAULT_GSI_RAW_CSV,
        target_utc: str = "2024-04-15T06:00:00Z",
        source_url: str = DEFAULT_GSI_SOURCE_URL,
        retrieved_at: str = "2026-11-27T16:44:00Z",
    ) -> None:
        self._raw_csv_path = raw_csv_path
        self._target_utc = target_utc
        self._source_url = source_url
        self._retrieved_at = retrieved_at
        self._metadata = ConnectorMetadata(
            connector_id="gsi-gwlevel",
            source_name="gsi_gwlevel",
            publishing_organisation="Geological Survey Ireland",
            produced_evidence_kinds=["hydrometric_water_level"],
            supports_authentication=False,
            notes=[
                "In-situ submerged pressure transducer stage measurements (mAOD Malin Head, UTC).",
                "Independent of Copernicus satellite observations.",
                "Licensed under CC BY 4.0.",
            ],
        )

    @property
    def metadata(self) -> ConnectorMetadata:
        return self._metadata

    def load_evidence(self) -> list[Evidence]:
        raw = extract_gsi_stage_evidence(
            raw_csv_path=self._raw_csv_path,
            target_utc=self._target_utc,
            source_url=self._source_url,
            retrieved_at=self._retrieved_at,
        )
        return [Evidence.model_validate(raw)]
