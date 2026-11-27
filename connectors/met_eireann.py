"""Met Éireann historical daily station CSV connector for EIP.

Processes a genuine downloaded Met Éireann daily climate CSV
(e.g. sample_data/raw/MetEireann_MtDillon_dly1975.csv, Station 1975 Mount Dillon,
Co. Roscommon) into a validated EIP Evidence object implementing
`connectors.base.EvidenceConnector`.

Provenance & integrity rules:
- Strictly an INDIRECT environmental indicator (regional daily rainfall).
  Never treated as direct proof of flooding on a specific road segment.
- SHA-256 hashes the raw downloaded CSV file (local byte integrity only).
- Daily rows span 00:00–24:00 UTC as documented in the Met Éireann file header.
- Exact publication timestamp (`available_at`) for a historical daily record is
  not embedded per-row in the CSV and therefore remains `None`.
- Licensed under Creative Commons Attribution 4.0 (CC BY 4.0) by Met Éireann.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from connectors.base import ConnectorMetadata
from core.integrity import compute_file_sha256
from core.models import Evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MET_RAW_CSV = REPO_ROOT / "sample_data" / "raw" / "MetEireann_MtDillon_dly1975.csv"
DEFAULT_MET_SOURCE_URL = "https://clidata.met.ie/cli/climate_data/webdata/dly1975.csv"


def _parse_met_date(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), "%d-%b-%Y").replace(tzinfo=timezone.utc)


def extract_met_eireann_daily_evidence(
    raw_csv_path: Path = DEFAULT_MET_RAW_CSV,
    target_date_utc: str = "2024-04-15",
    source_url: str = DEFAULT_MET_SOURCE_URL,
    retrieved_at: str = "2026-11-27T16:44:00Z",
) -> dict[str, Any]:
    """Parse a Met Éireann daily CSV and extract one validated Evidence dict."""
    resolved = raw_csv_path.resolve()
    sha256_hex = compute_file_sha256(resolved)
    rel_raw_path = resolved.relative_to(REPO_ROOT).as_posix()

    target_dt = datetime.strptime(target_date_utc, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    station_name = "UNKNOWN"
    station_lat: float | None = None
    station_lon: float | None = None
    station_height_m: float | None = None
    lines = resolved.read_text(encoding="utf-8").splitlines()

    header_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith("Station Name:"):
            station_name = line.split(":", 1)[1].strip()
        elif line.startswith("Station Height:"):
            m = re.search(r"(-?\d+(?:\.\d+)?)", line)
            if m:
                station_height_m = float(m.group(1))
        elif line.startswith("Latitude:"):
            m_lat = re.search(r"Latitude:\s*(-?\d+(?:\.\d+)?)", line)
            m_lon = re.search(r"Longitude:\s*(-?\d+(?:\.\d+)?)", line)
            if m_lat and m_lon:
                station_lat = float(m_lat.group(1))
                station_lon = float(m_lon.group(1))
        elif line.startswith("date,"):
            header_idx = idx
            break

    if header_idx is None or station_lat is None or station_lon is None:
        raise ValueError(f"Could not parse Met Éireann station metadata/header in {raw_csv_path}.")

    daily_rain_by_date: dict[datetime, float] = {}
    target_row: dict[str, str] | None = None
    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        raw_d = (row.get("date") or "").strip()
        if not raw_d:
            continue
        try:
            dt = _parse_met_date(raw_d)
        except ValueError:
            continue
        rain_str = (row.get("rain") or "").strip()
        if rain_str:
            try:
                daily_rain_by_date[dt] = float(rain_str)
            except ValueError:
                pass
        if dt == target_dt:
            target_row = row

    if target_row is None or target_dt not in daily_rain_by_date:
        raise ValueError(f"Date {target_date_utc} not found with valid rainfall in {raw_csv_path}.")

    rain_mm = daily_rain_by_date[target_dt]
    rain_5d = round(
        sum(
            daily_rain_by_date.get(target_dt - timedelta(days=offset), 0.0)
            for offset in range(5)
        ),
        2,
    )
    rain_15d = round(
        sum(
            daily_rain_by_date.get(target_dt - timedelta(days=offset), 0.0)
            for offset in range(15)
        ),
        2,
    )

    station_num_match = re.search(r"dly(\d+)", resolved.stem)
    station_code = station_num_match.group(1) if station_num_match else resolved.stem
    slug_date = target_dt.strftime("%Y%m%d")

    evidence_dict: dict[str, Any] = {
        "id": f"met-eireann-{station_code}-{slug_date}",
        "source": "met_eireann_daily",
        "product_id": f"MET_EIREANN_DLY_{station_code}_{station_name.replace(' ', '_')}",
        "source_url": source_url,
        "observed_at": target_dt.strftime("%Y-%m-%dT00:00:00Z"),
        "available_at": None,
        "retrieved_at": retrieved_at,
        "kind": "meteorological_rainfall",
        "geometry": {
            "type": "Point",
            "coordinates": [station_lon, station_lat],
        },
        "coverage": None,
        "attributes": {
            "evidence_role": "indirect_contextual",
            "station_code": station_code,
            "station_name": station_name,
            "station_height_m": station_height_m,
            "rain_mm": rain_mm,
            "cumulative_5day_rain_mm": rain_5d,
            "cumulative_15day_rain_mm": rain_15d,
            "observation_window_utc": f"{target_date_utc}T00:00:00Z/24h",
        },
        "provenance": {
            "original_source": f"Met Éireann Synoptic Station {station_code} ({station_name})",
            "publishing_organisation": "Met Éireann",
            "upstream_datasets": [f"met_eireann_dly{station_code}"],
            "derived_from": [],
            "measurement_method": "Automated synoptic rain gauge (daily 00–24 UTC precipitation in mm)",
            "shared_dependencies": [],
        },
        "authentication": "unknown",
        "sha256": sha256_hex,
        "raw_path": rel_raw_path,
        "licence": (
            "Creative Commons Attribution 4.0 International (CC BY 4.0) — "
            "Met Éireann (https://www.met.ie/)"
        ),
        "limitations": [
            "Regional synoptic weather station (~27 km NNE of Lough Funshinagh) measures daily precipitation only; rainfall is an indirect environmental indicator and cannot prove road flooding.",
            "Daily aggregated precipitation (00–24 UTC) does not capture localized cloudburst timing or karst groundwater lag.",
            "Exact historical publication timestamp (available_at) is not recorded per row in the CSV archive and remains unknown (null).",
            "Raw CSV SHA-256 confirms local byte integrity only; source cryptographic authentication is unknown (unverified).",
        ],
        "synthetic": False,
    }

    validated = Evidence.model_validate(evidence_dict)
    return validated.model_dump(mode="json")


class MetEireannDailyConnector:
    """EvidenceConnector implementation for Met Éireann historical daily CSVs."""

    def __init__(
        self,
        raw_csv_path: Path = DEFAULT_MET_RAW_CSV,
        target_date_utc: str = "2024-04-15",
        source_url: str = DEFAULT_MET_SOURCE_URL,
        retrieved_at: str = "2026-11-27T16:44:00Z",
    ) -> None:
        self._raw_csv_path = raw_csv_path
        self._target_date_utc = target_date_utc
        self._source_url = source_url
        self._retrieved_at = retrieved_at
        self._metadata = ConnectorMetadata(
            connector_id="met-eireann-daily",
            source_name="met_eireann_daily",
            publishing_organisation="Met Éireann",
            produced_evidence_kinds=["meteorological_rainfall"],
            supports_authentication=False,
            notes=[
                "Synoptic station daily precipitation archive (00–24 UTC, mm).",
                "Independent of Copernicus satellite observations and GSI hydrometric gauges.",
                "Licensed under CC BY 4.0.",
            ],
        )

    @property
    def metadata(self) -> ConnectorMetadata:
        return self._metadata

    def load_evidence(self) -> list[Evidence]:
        raw = extract_met_eireann_daily_evidence(
            raw_csv_path=self._raw_csv_path,
            target_date_utc=self._target_date_utc,
            source_url=self._source_url,
            retrieved_at=self._retrieved_at,
        )
        return [Evidence.model_validate(raw)]
