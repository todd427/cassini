"""Offline builder combining genuine independent Lough Funshinagh sources into
sample_data/evidence.json and generating reproducible v0.3 demonstration scenarios.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from connectors.cems_rapid_mapping import (
    CemsRapidMappingConnector,
    build_emsr718_example_claims,
)
from connectors.gsi_gwlevel import GsiGwlevelConnector
from connectors.met_eireann import MetEireannDailyConnector

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_OUT = REPO_ROOT / "sample_data" / "evidence.json"
EXAMPLES_OUT = REPO_ROOT / "sample_data" / "example_claims.json"
SCENARIOS_DIR = REPO_ROOT / "sample_data" / "scenarios"


def build_genuine_evidence_bundle() -> list[dict[str, Any]]:
    """Load all 3 genuine, independent Lough Funshinagh evidence sources offline."""
    connectors = [
        CemsRapidMappingConnector(retrieved_at="2026-11-27T16:00:00Z"),
        GsiGwlevelConnector(
            target_utc="2024-04-15T06:00:00Z",
            retrieved_at="2026-11-27T16:44:00Z",
        ),
        MetEireannDailyConnector(
            target_date_utc="2024-04-15",
            retrieved_at="2026-11-27T16:44:00Z",
        ),
    ]
    items: list[dict[str, Any]] = []
    for conn in connectors:
        for ev in conn.load_evidence():
            items.append(ev.model_dump(mode="json"))
    return items


def build_v03_scenarios(genuine_bundle: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build 5 reproducible v0.3 multi-source demonstration scenarios.

    Clearly distinguishes genuine evidence (synthetic=False) from explicitly
    labelled synthetic test records (synthetic=True).
    """
    cems_ev = genuine_bundle[0]
    gsi_ev = genuine_bundle[1]
    met_ev = genuine_bundle[2]

    examples = build_emsr718_example_claims()
    flooded_road_claim = examples[0]["claim"]
    covered_clear_claim = examples[1]["claim"]

    # Synthetic derived copy of CEMS product (different publisher, SAME upstream satellite pass!)
    derived_cems_partner = copy.deepcopy(cems_ev)
    derived_cems_partner["id"] = "synthetic-partner-derived-emsr718"
    derived_cems_partner["source"] = "synthetic_downstream_analytics"
    derived_cems_partner["product_id"] = "PARTNER_REPROCESS_EMSR718_V1"
    derived_cems_partner["source_url"] = None
    derived_cems_partner["raw_path"] = None
    derived_cems_partner["sha256"] = None
    derived_cems_partner["licence"] = "Synthetic test derivative (not a real product)"
    derived_cems_partner["synthetic"] = True
    derived_cems_partner["provenance"] = {
        "original_source": "COSMO-SkyMed",
        "publishing_organisation": "Synthetic Downstream Analytics Vendor",
        "upstream_datasets": ["EMSR718_AOI02_DEL_MONIT01_v2"],
        "derived_from": [cems_ev["id"]],
        "measurement_method": "Re-vectorised mask derived from CEMS EMSR718",
        "shared_dependencies": ["copernicus_ems_rapid_mapping_pipeline"],
    }
    derived_cems_partner["limitations"] = [
        "Synthetic derivative sharing upstream COSMO-SkyMed observation with EMSR718; must NOT count as independent corroboration."
    ]

    # Synthetic independent non-overlapping direct observation (for direct-vs-direct disagreement test)
    synth_independent_clear = {
        "id": "synthetic-independent-clear-direct",
        "source": "synthetic_aerial_survey",
        "product_id": "SYNTH_AERIAL_20240415",
        "source_url": None,
        "observed_at": "2024-04-15T07:30:00Z",
        "available_at": "2024-04-15T07:45:00Z",
        "retrieved_at": "2026-11-27T16:44:00Z",
        "kind": "flood_extent",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-8.160, 53.510],
                    [-8.155, 53.510],
                    [-8.155, 53.514],
                    [-8.160, 53.514],
                    [-8.160, 53.510],
                ]
            ],
        },
        "coverage": copy.deepcopy(cems_ev["coverage"]),
        "attributes": {"evidence_role": "direct"},
        "provenance": {
            "original_source": "Synthetic Aerial Ortho Camera",
            "publishing_organisation": "Synthetic Independent Survey",
            "upstream_datasets": ["SYNTH_AERIAL_FLIGHT_20240415"],
            "derived_from": [],
            "measurement_method": "Synthetic aerial photogrammetry",
            "shared_dependencies": [],
        },
        "authentication": "unknown",
        "sha256": None,
        "raw_path": None,
        "licence": "Synthetic test fixture",
        "limitations": ["Synthetic direct flood-extent fixture for disagreement testing."],
        "synthetic": True,
    }

    # Synthetic post-decision published record (for decision_time leakage prevention)
    synth_post_decision = copy.deepcopy(cems_ev)
    synth_post_decision["id"] = "synthetic-delayed-publication-cems"
    synth_post_decision["available_at"] = "2024-04-16T10:00:00Z"
    synth_post_decision["raw_path"] = None
    synth_post_decision["sha256"] = None
    synth_post_decision["synthetic"] = True
    synth_post_decision["limitations"] = [
        "Synthetic timestamped variant modelling publication on 2024-04-16T10:00:00Z (after 2024-04-15T08:00:00Z decision)."
    ]

    return {
        "independent_corroboration": {
            "description": (
                "Three genuinely independent observations (Copernicus COSMO-SkyMed SAR direct flood extent, "
                "GSI_11 in-situ Lough Funshinagh water level 69.37 mAOD, Met Éireann Mount Dillon rainfall) "
                "assessed against a synthetic flooded road passability claim."
            ),
            "uses_genuine_evidence": True,
            "evidence": [cems_ev, gsi_ev, met_ev],
            "claim": flooded_road_claim,
            "expected_status": "potential_conflict",
            "expected_independence_status": "distinct_declared_sources",
            "expected_independent_groups": 3,
        },
        "contextual_tension_covered_clear": {
            "description": (
                "Genuine multi-source tension: Copernicus EMSR718 shows no mapped overlap on a covered clear road "
                "(Rahara South) while independent genuine GSI_11 reports near-record lake level (69.37 mAOD) nearby. "
                "Demonstrates that no_mapped_overlap is not proof of road safety."
            ),
            "uses_genuine_evidence": True,
            "evidence": [cems_ev, gsi_ev, met_ev],
            "claim": covered_clear_claim,
            "expected_status": "no_mapped_overlap",
            "expected_independence_status": "distinct_declared_sources",
            "expected_independent_groups": 3,
        },
        "direct_disagreement_synthetic": {
            "description": (
                "Explicitly synthetic disagreement fixture: genuine EMSR718 direct flood extent overlaps the road "
                "while a synthetic independent direct aerial survey covering the road shows no mapped overlap. "
                "potential_conflict takes precedence and both findings remain visible."
            ),
            "uses_genuine_evidence": True,
            "evidence": [cems_ev, synth_independent_clear],
            "claim": flooded_road_claim,
            "expected_status": "potential_conflict",
            "expected_independence_status": "distinct_declared_sources",
            "expected_independent_groups": 2,
        },
        "shared_upstream_derived": {
            "description": (
                "Two flood products published by different organisations from the same upstream COSMO-SkyMed "
                "observation collapse into 1 correlated group (not independent corroboration)."
            ),
            "uses_genuine_evidence": True,
            "evidence": [cems_ev, derived_cems_partner],
            "claim": flooded_road_claim,
            "expected_status": "potential_conflict",
            "expected_independence_status": "shared_dependencies_detected",
            "expected_independent_groups": 1,
        },
        "indirect_only_insufficient": {
            "description": (
                "Genuine independent indirect observations only (GSI_11 stage 69.37 mAOD + Met Éireann rainfall) "
                "without direct flood extent mapping: relevant context, but insufficient to resolve road passability."
            ),
            "uses_genuine_evidence": True,
            "evidence": [gsi_ev, met_ev],
            "claim": flooded_road_claim,
            "expected_status": "insufficient_evidence",
            "expected_independence_status": "distinct_declared_sources",
            "expected_independent_groups": 2,
        },
        "decision_time_unavailable": {
            "description": (
                "Decision-time assessment at 2024-04-15T08:00:00Z: genuine evidence with unknown available_at "
                "yields AVAILABILITY_TIME_UNKNOWN, while synthetic delayed publication (available 2024-04-16T10:00Z) "
                "yields NOT_AVAILABLE_AT_DECISION_TIME."
            ),
            "uses_genuine_evidence": True,
            "evidence": [gsi_ev, synth_post_decision],
            "claim": {
                **flooded_road_claim,
                "claim_id": "emsr718-decision-time-20240415t0800z",
                "assessment_mode": "decision_time",
                "decision_time": "2024-04-15T08:00:00Z",
            },
            "expected_status": "insufficient_evidence",
            "expected_independence_status": "distinct_declared_sources",
            "expected_independent_groups": 2,
        },
    }


def main() -> None:
    genuine_bundle = build_genuine_evidence_bundle()
    EVIDENCE_OUT.write_text(json.dumps(genuine_bundle, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(genuine_bundle)} genuine independent evidence records to {EVIDENCE_OUT}:")
    for ev in genuine_bundle:
        print(f"  - {ev['id']} ({ev['source']}, kind={ev['kind']}, observed={ev['observed_at']}, sha256={ev['sha256'][:12]}...)")

    examples = build_emsr718_example_claims()
    EXAMPLES_OUT.write_text(json.dumps(examples, indent=2) + "\n", encoding="utf-8")

    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenarios = build_v03_scenarios(genuine_bundle)
    for name, bundle in scenarios.items():
        # Store lightweight reference summary + evidence/claim so each scenario is self-contained & replayable
        out = SCENARIOS_DIR / f"{name}.json"
        # To avoid duplicating 1.1MB CEMS polygon 5 times in git, reference genuine evidence IDs when exact match
        compact = {
            "description": bundle["description"],
            "uses_genuine_evidence": bundle["uses_genuine_evidence"],
            "claim": bundle["claim"],
            "expected_status": bundle["expected_status"],
            "expected_independence_status": bundle["expected_independence_status"],
            "expected_independent_groups": bundle["expected_independent_groups"],
            "evidence_refs": [
                {"ref_id": ev["id"]}
                if not ev["synthetic"]
                else {"inline": {k: v for k, v in ev.items() if k not in ("geometry", "coverage")} | {
                    "geometry_ref_id": cems_ref if ev["id"] in ("synthetic-partner-derived-emsr718", "synthetic-delayed-publication-cems") else None,
                    "coverage_ref_id": cems_ref if ev["id"] in ("synthetic-partner-derived-emsr718", "synthetic-delayed-publication-cems", "synthetic-independent-clear-direct") else None,
                    **({"geometry": ev["geometry"]} if ev["id"] == "synthetic-independent-clear-direct" else {}),
                }}
                for cems_ref in [genuine_bundle[0]["id"]]
                for ev in bundle["evidence"]
            ],
        }
        out.write_text(json.dumps(compact, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote scenario: {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
