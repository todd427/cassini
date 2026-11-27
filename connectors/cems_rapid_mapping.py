"""Copernicus EMS Rapid Mapping (CEMS) vector package connector for EIP.

Processes a genuine downloaded CEMS Rapid Mapping delineation vector ZIP archive
(e.g. EMSR718_AOI02_DEL_MONIT01_v2.zip) into EIP contract v0.1 Evidence JSON.

Provenance & integrity rules:
- SHA-256 hashes the raw downloaded ZIP artifact (proves local byte integrity only).
- Acquisition timestamp is extracted directly from the archive's `source*.dbf`
  record matching `dmg_src_id` in `observedEventA` (never invented).
- Flood extent uses actual `observedEventA` flood polygons (never catalogue footprint).
- Documented valid coverage uses `areaOfInterestA` intersected with the post-event
  `imageFootprintA` when present (never inferred from a bounding box).
- Authentication remains `"unknown"` unless independently verified by a documented
  cryptographic provenance mechanism.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import shapefile
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from connectors.base import ConnectorMetadata
from core.integrity import compute_file_sha256
from core.models import Evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_ZIP = REPO_ROOT / "sample_data" / "raw" / "EMSR718_AOI02_DEL_MONIT01_v2.zip"
DEFAULT_SOURCE_URL = (
    "https://rapidmapping.emergency.copernicus.eu/backend/"
    "EMSR718/AOI02/DEL_MONIT01/EMSR718_AOI02_DEL_MONIT01_v2.zip"
)
DEFAULT_EVIDENCE_OUT = REPO_ROOT / "sample_data" / "evidence.json"
DEFAULT_EXAMPLES_OUT = REPO_ROOT / "sample_data" / "example_claims.json"


def compute_sha256(path: Path) -> str:
    return compute_file_sha256(path)


def _find_zip_member(z: zipfile.ZipFile, substring: str, suffix: str) -> str | None:
    matches = [
        name
        for name in z.namelist()
        if substring.lower() in name.lower() and name.lower().endswith(suffix.lower())
    ]
    return sorted(matches)[0] if matches else None


def _extract_polygons(geom) -> Polygon | MultiPolygon:
    """Normalize a validated Shapely geometry to Polygon or MultiPolygon."""
    if not geom.is_valid:
        geom = make_valid(geom)
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    polys: list[Polygon] = []
    if hasattr(geom, "geoms"):
        for part in geom.geoms:
            if isinstance(part, Polygon) and not part.is_empty and part.area > 0:
                polys.append(part)
            elif isinstance(part, MultiPolygon):
                polys.extend(p for p in part.geoms if not p.is_empty and p.area > 0)
    if not polys:
        raise ValueError("No valid polygonal flood geometry found in archive.")
    if len(polys) == 1:
        return polys[0]
    return MultiPolygon(polys)


def _to_json_coords(obj: Any) -> Any:
    if isinstance(obj, (list, tuple)):
        return [_to_json_coords(x) for x in obj]
    return obj


def _to_geojson_poly(geom: Polygon | MultiPolygon) -> dict[str, Any]:
    raw = mapping(geom)
    return {
        "type": raw["type"],
        "coordinates": _to_json_coords(raw["coordinates"]),
    }


def _parse_source_dbf_timestamp(
    z: zipfile.ZipFile, target_src_ids: set[int]
) -> tuple[str | None, str | None, str | None]:
    """Return (observed_at_iso_utc, sensor_name, sensor_res) from source DBF."""
    dbf_member = _find_zip_member(z, "_source_", ".dbf")
    if not dbf_member:
        return None, None, None
    sf = shapefile.Reader(dbf=io.BytesIO(z.read(dbf_member)))
    for rec in sf.records():
        row = rec.as_dict()
        src_id = row.get("src_id")
        if target_src_ids and src_id not in target_src_ids:
            continue
        if not target_src_ids and str(row.get("eventphase", "")).lower() != "post-event":
            continue
        src_date = str(row.get("src_date", "")).strip()
        src_tm = str(row.get("source_tm", "")).strip()
        sensor_name = str(row.get("source_nam", "")).strip() or None
        sensor_res = str(row.get("sensor_res", "")).strip() or None
        if src_date and src_tm and src_tm.lower() != "not applicable":
            # CEMS source DBF uses DD/MM/YYYY and T06:02:08Z
            dt_str = f"{src_date}{src_tm}"
            parsed = datetime.strptime(dt_str, "%d/%m/%YT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ"), sensor_name, sensor_res
    return None, None, None


def extract_cems_evidence(
    raw_zip_path: Path,
    source_url: str,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Parse a CEMS Rapid Mapping vector ZIP into a validated EIP Evidence dict."""
    resolved_zip = raw_zip_path.resolve()
    sha256_hex = compute_sha256(resolved_zip)
    rel_raw_path = resolved_zip.relative_to(REPO_ROOT).as_posix()
    product_id = resolved_zip.stem

    with zipfile.ZipFile(resolved_zip, "r") as z:
        obs_member = _find_zip_member(z, "observedEventA", ".json")
        if not obs_member:
            raise ValueError(
                f"Archive {raw_zip_path} does not contain an observedEventA GeoJSON layer."
            )
        obs_fc = json.loads(z.read(obs_member).decode("utf-8"))
        flood_geoms = []
        src_ids: set[int] = set()
        for feat in obs_fc.get("features", []):
            props = feat.get("properties") or {}
            if props.get("dmg_src_id") is not None:
                try:
                    src_ids.add(int(props["dmg_src_id"]))
                except (TypeError, ValueError):
                    pass
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = make_valid(g)
            flood_geoms.append(g)

        if not flood_geoms:
            raise ValueError("observedEventA layer contains no flood features.")

        flood_union = _extract_polygons(unary_union(flood_geoms))

        # Documented coverage: AOI intersected with post-event image footprint (if present)
        aoi_member = _find_zip_member(z, "areaOfInterestA", ".json")
        fp_member = _find_zip_member(z, "imageFootprintA", ".json")
        coverage_geom: Polygon | MultiPolygon | None = None
        locality = ""
        if aoi_member:
            aoi_fc = json.loads(z.read(aoi_member).decode("utf-8"))
            aoi_polys = []
            for feat in aoi_fc.get("features", []):
                props = feat.get("properties") or {}
                if props.get("locality"):
                    locality = str(props["locality"])
                g = shape(feat["geometry"])
                if not g.is_valid:
                    g = make_valid(g)
                aoi_polys.append(g)
            if aoi_polys:
                aoi_union = unary_union(aoi_polys)
                if fp_member and src_ids:
                    fp_fc = json.loads(z.read(fp_member).decode("utf-8"))
                    matching_fp = [
                        make_valid(shape(f["geometry"]))
                        for f in fp_fc.get("features", [])
                        if (f.get("properties") or {}).get("or_src_id") in src_ids
                    ]
                    if matching_fp:
                        cov = aoi_union.intersection(unary_union(matching_fp))
                        coverage_geom = _extract_polygons(cov)
                    else:
                        coverage_geom = _extract_polygons(aoi_union)
                else:
                    coverage_geom = _extract_polygons(aoi_union)

        observed_at, sensor_name, sensor_res = _parse_source_dbf_timestamp(z, src_ids)

    retrieved_iso = retrieved_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    sensor_note = (
        f"Derived from {sensor_name} ({sensor_res} resolution) SAR imagery via CEMS Rapid Mapping semi-automatic flood extraction"
        if sensor_name
        else "Derived from CEMS Rapid Mapping semi-automatic flood extraction"
    )
    loc_note = f" for {locality}" if locality else ""

    evidence_dict: dict[str, Any] = {
        "id": f"cems-{product_id.lower().replace('_', '-')}",
        "source": "copernicus_ems_rapid_mapping",
        "product_id": product_id,
        "source_url": source_url,
        "observed_at": observed_at,
        "available_at": None,
        "retrieved_at": retrieved_iso,
        "kind": "flood_extent",
        "geometry": _to_geojson_poly(flood_union),
        "coverage": _to_geojson_poly(coverage_geom) if coverage_geom is not None else None,
        "attributes": {
            "locality": locality or None,
            "sensor_name": sensor_name,
            "sensor_resolution": sensor_res,
            "feature_count": len(flood_geoms),
        },
        "provenance": {
            "original_source": sensor_name,
            "publishing_organisation": "Copernicus EMS Rapid Mapping",
            "upstream_datasets": [product_id],
            "derived_from": [],
            "measurement_method": "SAR semi-automatic flood extraction",
            "shared_dependencies": [],
        },
        "authentication": "unknown",
        "sha256": sha256_hex,
        "raw_path": rel_raw_path,
        "licence": (
            "Copernicus EMS Rapid Mapping (© European Union, 2024); "
            "https://emergency.copernicus.eu/mapping/ems/cite-copernicus-ems-mapping-portal"
        ),
        "limitations": [
            f"{sensor_note}{loc_note}.",
            "SAR flood delineation may miss standing water beneath dense tree canopy, bridges, or urban radar shadow.",
            "Observed flood polygon indicates surface water extent at acquisition time, not water depth or road structural integrity.",
            "Raw archive SHA-256 confirms local file integrity only; source cryptographic authentication is unverified (unknown).",
        ],
        "synthetic": False,
    }

    # Validate strictly against EIP schema before returning
    validated = Evidence.model_validate(evidence_dict)
    return validated.model_dump(mode="json")


class CemsRapidMappingConnector:
    """EvidenceConnector implementation wrapping a local CEMS Rapid Mapping ZIP."""

    def __init__(
        self,
        raw_zip_path: Path = DEFAULT_RAW_ZIP,
        source_url: str = DEFAULT_SOURCE_URL,
        retrieved_at: str | None = None,
    ) -> None:
        self._raw_zip_path = raw_zip_path
        self._source_url = source_url
        self._retrieved_at = retrieved_at
        self._metadata = ConnectorMetadata(
            connector_id="cems-rapid-mapping",
            source_name="copernicus_ems_rapid_mapping",
            publishing_organisation="Copernicus EMS Rapid Mapping",
            produced_evidence_kinds=["flood_extent"],
            supports_authentication=False,
            notes=[
                "Offline ZIP archive connector extracting observedEventA and areaOfInterestA layers.",
                "SHA-256 verifies local byte integrity only; authentication remains unknown.",
            ],
        )

    @property
    def metadata(self) -> ConnectorMetadata:
        return self._metadata

    def load_evidence(self) -> list[Evidence]:
        raw = extract_cems_evidence(
            raw_zip_path=self._raw_zip_path,
            source_url=self._source_url,
            retrieved_at=self._retrieved_at,
        )
        return [Evidence.model_validate(raw)]


def build_emsr718_example_claims() -> list[dict[str, Any]]:
    """Return clearly labeled synthetic road reports scoped to EMSR718 Lough Funshinagh.

    All claims here are explicitly marked synthetic=True and evaluated against
    the genuine historical Copernicus EMSR718 flood product (2024-04-15T06:02:08Z).
    """
    return [
        {
            "label": "Lough Funshinagh — Intersecting flooded road (Potential Conflict)",
            "description": (
                "Synthetic road passability report crossing the eastern flooded basin "
                "of Lough Funshinagh (Co. Roscommon) ~2 hours after COSMO-SkyMed SAR acquisition."
            ),
            "expected_status": "potential_conflict",
            "claim": {
                "claim_id": "emsr718-road-ballagh-east",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-8.1165, 53.4916],
                        [-8.1113, 53.4916],
                        [-8.1075, 53.4916],
                    ],
                },
                "claimed_at": "2024-04-15T08:00:00Z",
                "source_label": "Synthetic historical replay road report (Lough Funshinagh East)",
                "synthetic": True,
            },
        },
        {
            "label": "Lough Funshinagh — Covered road without mapped flood (No Mapped Overlap)",
            "description": (
                "Synthetic road report inside EMSR718 AOI02 documented coverage south-west "
                "of Lough Funshinagh with no mapped flood overlap (~2h from acquisition). "
                "Not proof of road safety."
            ),
            "expected_status": "no_mapped_overlap",
            "claim": {
                "claim_id": "emsr718-road-rahara-south",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-8.1750, 53.4620],
                        [-8.1550, 53.4620],
                    ],
                },
                "claimed_at": "2024-04-15T08:00:00Z",
                "source_label": "Synthetic historical replay road report (Rahara South, inside AOI02)",
                "synthetic": True,
            },
        },
        {
            "label": "Lough Funshinagh — Stale observation (>24h) (Insufficient Evidence)",
            "description": (
                "Same flooded road segment queried 72 hours after satellite acquisition, "
                "exceeding the 24-hour demo policy window."
            ),
            "expected_status": "insufficient_evidence",
            "claim": {
                "claim_id": "emsr718-road-stale-72h",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-8.1165, 53.4916],
                        [-8.1075, 53.4916],
                    ],
                },
                "claimed_at": "2024-04-18T06:02:08Z",
                "source_label": "Synthetic historical replay road report (72h post-acquisition)",
                "synthetic": True,
            },
        },
        {
            "label": "Athlone approach — Outside documented AOI coverage (Insufficient Evidence)",
            "description": (
                "Synthetic road segment east of EMSR718 AOI02 boundary; documented "
                "observation coverage excludes this road."
            ),
            "expected_status": "insufficient_evidence",
            "claim": {
                "claim_id": "emsr718-road-outside-aoi",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-7.9800, 53.4300],
                        [-7.9500, 53.4300],
                    ],
                },
                "claimed_at": "2024-04-15T08:00:00Z",
                "source_label": "Synthetic historical replay road report (Outside AOI02 coverage)",
                "synthetic": True,
            },
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a CEMS Rapid Mapping vector ZIP into EIP evidence.json."
    )
    parser.add_argument("--raw-zip", type=Path, default=DEFAULT_RAW_ZIP)
    parser.add_argument("--source-url", type=str, default=DEFAULT_SOURCE_URL)
    parser.add_argument("--retrieved-at", type=str, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--examples-out", type=Path, default=DEFAULT_EXAMPLES_OUT)
    args = parser.parse_args()

    evidence = extract_cems_evidence(
        raw_zip_path=args.raw_zip,
        source_url=args.source_url,
        retrieved_at=args.retrieved_at,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([evidence], indent=2) + "\n", encoding="utf-8")
    print(f"Wrote genuine CEMS evidence to {args.out}")
    print(f"  id:          {evidence['id']}")
    print(f"  product_id:  {evidence['product_id']}")
    print(f"  observed_at: {evidence['observed_at']}")
    print(f"  sha256:      {evidence['sha256']}")

    examples = build_emsr718_example_claims()
    args.examples_out.write_text(json.dumps(examples, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(examples)} synthetic replay example claims to {args.examples_out}")


if __name__ == "__main__":
    main()
