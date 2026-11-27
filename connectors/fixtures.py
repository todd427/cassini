"""Deterministic synthetic fixtures covering all EIP contract v0.1 assessment scenarios.

Every record produced here is explicitly marked synthetic=True and must NEVER
be presented as a genuine Copernicus observation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "sample_data" / "fixtures"

# Deterministic synthetic box in Co. Donegal / NW Ireland (matching CONTRACT.md example)
_FLOOD_POLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [-7.74, 54.95],
            [-7.73, 54.95],
            [-7.73, 54.96],
            [-7.74, 54.96],
            [-7.74, 54.95],
        ]
    ],
}

_COVERAGE_POLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [-7.76, 54.94],
            [-7.71, 54.94],
            [-7.71, 54.97],
            [-7.76, 54.97],
            [-7.76, 54.94],
        ]
    ],
}


def build_synthetic_fixtures() -> dict[str, dict[str, Any]]:
    """Return deterministic fixture bundles (evidence + claim + expected status/reasons)."""
    base_evidence = {
        "id": "fixture-flood-1",
        "source": "fixture",
        "product_id": None,
        "source_url": None,
        "observed_at": "2026-01-01T10:00:00Z",
        "retrieved_at": "2026-01-02T10:00:00Z",
        "kind": "flood_extent",
        "geometry": _FLOOD_POLY,
        "coverage": _COVERAGE_POLY,
        "authentication": "unknown",
        "sha256": None,
        "raw_path": None,
        "licence": None,
        "limitations": ["Synthetic fixture, not an actual flood."],
        "synthetic": True,
    }

    return {
        "fresh_intersection": {
            "description": "Synthetic road intersecting a fresh (2h) flood extent polygon.",
            "evidence": [base_evidence],
            "claim": {
                "claim_id": "fixture-claim-intersect",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.745, 54.955], [-7.725, 54.955]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (intersecting flood)",
                "synthetic": True,
            },
            "expected_status": "potential_conflict",
            "expected_reasons": ["FLOOD_EXTENT_INTERSECTS"],
        },
        "covered_non_intersection": {
            "description": "Synthetic road fully within documented coverage with no mapped flood overlap.",
            "evidence": [base_evidence],
            "claim": {
                "claim_id": "fixture-claim-clear-covered",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.75, 54.945], [-7.72, 54.945]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (covered clear road)",
                "synthetic": True,
            },
            "expected_status": "no_mapped_overlap",
            "expected_reasons": ["NO_MAPPED_OVERLAP"],
        },
        "stale_observation": {
            "description": "Intersecting flood observation older than 24-hour demo policy window (48h).",
            "evidence": [
                {
                    **base_evidence,
                    "id": "fixture-flood-stale",
                    "observed_at": "2025-12-30T12:00:00Z",
                }
            ],
            "claim": {
                "claim_id": "fixture-claim-stale",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.745, 54.955], [-7.725, 54.955]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (stale evidence)",
                "synthetic": True,
            },
            "expected_status": "insufficient_evidence",
            "expected_reasons": ["OBSERVATION_STALE"],
        },
        "unknown_observation_time": {
            "description": "Flood evidence missing acquisition timestamp (observed_at=null).",
            "evidence": [
                {
                    **base_evidence,
                    "id": "fixture-flood-unknown-time",
                    "observed_at": None,
                }
            ],
            "claim": {
                "claim_id": "fixture-claim-unknown-time",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.745, 54.955], [-7.725, 54.955]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (unknown observation time)",
                "synthetic": True,
            },
            "expected_status": "insufficient_evidence",
            "expected_reasons": ["OBSERVATION_TIME_UNKNOWN"],
        },
        "outside_coverage": {
            "description": "Road segment lies outside documented observation coverage.",
            "evidence": [base_evidence],
            "claim": {
                "claim_id": "fixture-claim-outside",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.90, 54.955], [-7.86, 54.955]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (outside coverage)",
                "synthetic": True,
            },
            "expected_status": "insufficient_evidence",
            "expected_reasons": ["OUTSIDE_COVERAGE"],
        },
        "unknown_coverage": {
            "description": "Non-overlapping road where coverage polygon is undocumented (null).",
            "evidence": [
                {
                    **base_evidence,
                    "id": "fixture-flood-unknown-cov",
                    "coverage": None,
                }
            ],
            "claim": {
                "claim_id": "fixture-claim-unknown-cov",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.75, 54.945], [-7.72, 54.945]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (unknown coverage)",
                "synthetic": True,
            },
            "expected_status": "insufficient_evidence",
            "expected_reasons": ["COVERAGE_UNKNOWN"],
        },
        "missing_evidence": {
            "description": "Empty evidence dataset yields NO_EVIDENCE.",
            "evidence": [],
            "claim": {
                "claim_id": "fixture-claim-no-evidence",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-7.745, 54.955], [-7.725, 54.955]],
                },
                "claimed_at": "2026-01-01T12:00:00Z",
                "source_label": "Synthetic road report (no evidence)",
                "synthetic": True,
            },
            "expected_status": "insufficient_evidence",
            "expected_reasons": ["NO_EVIDENCE"],
        },
    }


def write_fixtures(output_dir: Path = FIXTURES_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, bundle in build_synthetic_fixtures().items():
        path = output_dir / f"{name}.json"
        path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    paths = write_fixtures()
    for p in paths:
        print(f"Wrote fixture: {p}")
