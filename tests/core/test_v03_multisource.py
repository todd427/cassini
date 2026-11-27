"""EIP v0.3 tests: genuine independent connectors, multi-source corroboration,
direct vs indirect epistemic distinction, shared upstream detection, and scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from connectors.base import EvidenceConnector
from connectors.build_evidence_bundle import (
    build_genuine_evidence_bundle,
    build_v03_scenarios,
)
from connectors.gsi_gwlevel import GsiGwlevelConnector
from connectors.met_eireann import MetEireannDailyConnector
from core.engine import AssessmentEngine
from core.models import ClaimRequest, Evidence
from core.store import InMemoryEvidenceStore, load_evidence_file
from policies import build_default_registry

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = REPO_ROOT / "sample_data" / "scenarios"


def test_new_connectors_implement_protocol_and_load_genuine_data() -> None:
    gsi_conn = GsiGwlevelConnector()
    met_conn = MetEireannDailyConnector()
    assert isinstance(gsi_conn, EvidenceConnector)
    assert isinstance(met_conn, EvidenceConnector)

    gsi_items = gsi_conn.load_evidence()
    assert len(gsi_items) == 1
    assert gsi_items[0].synthetic is False
    assert gsi_items[0].kind == "hydrometric_water_level"
    assert gsi_items[0].attributes["stage_maod"] == 69.37

    met_items = met_conn.load_evidence()
    assert len(met_items) == 1
    assert met_items[0].synthetic is False
    assert met_items[0].kind == "meteorological_rainfall"
    assert met_items[0].attributes["rain_mm"] == 6.1


def test_capabilities_and_evidence_api_expose_all_three_genuine_sources() -> None:
    client = TestClient(create_app())

    caps = client.get("/v1/capabilities")
    assert caps.status_code == 200
    kinds = caps.json()["supported_evidence_kinds"]
    assert "flood_extent" in kinds
    assert "hydrometric_water_level" in kinds
    assert "meteorological_rainfall" in kinds

    ev_res = client.get("/v1/evidence")
    assert ev_res.status_code == 200
    items = ev_res.json()["items"]
    assert len(items) >= 3
    assert all(item["synthetic"] is False for item in items)
    assert {
        "copernicus_ems_rapid_mapping",
        "gsi_gwlevel",
        "met_eireann_daily",
    }.issubset({item["source"] for item in items})


def test_all_v03_demonstration_scenarios() -> None:
    genuine_bundle = build_genuine_evidence_bundle()
    scenarios = build_v03_scenarios(genuine_bundle)
    engine = AssessmentEngine(build_default_registry())

    # Verify all scenario JSON files exist on disk under sample_data/scenarios/
    for name in scenarios:
        assert (SCENARIOS_DIR / f"{name}.json").exists()

    for name, bundle in scenarios.items():
        ev_objs = [Evidence.model_validate(e) for e in bundle["evidence"]]
        claim = ClaimRequest.model_validate(bundle["claim"])

        res1 = engine.assess(claim, ev_objs)
        res2 = engine.assess(claim, ev_objs)
        assert res1.model_dump(mode="json") == res2.model_dump(mode="json")

        assert res1.status == bundle["expected_status"], f"Status mismatch in {name}"
        assert res1.independence is not None
        assert (
            res1.independence.status == bundle["expected_independence_status"]
        ), f"Independence status mismatch in {name}"
        assert (
            res1.independence.independent_group_count
            == bundle["expected_independent_groups"]
        ), f"Independent group count mismatch in {name}"

    # Spot-check critical epistemic invariants:
    # 1) Independent corroboration: direct potential_conflict + 2 indirect contextual_support
    corrob = engine.assess(
        ClaimRequest.model_validate(scenarios["independent_corroboration"]["claim"]),
        [Evidence.model_validate(e) for e in scenarios["independent_corroboration"]["evidence"]],
    )
    assert corrob.status == "potential_conflict"
    assert "FLOOD_EXTENT_INTERSECTS" in corrob.reasons
    assert "CONTEXTUAL_WATER_LEVEL_ELEVATED" in corrob.reasons
    assert "CONTEXTUAL_RAINFALL_OBSERVED" in corrob.reasons
    finding_statuses = {f.evidence_id: f.status for f in corrob.findings}
    assert finding_statuses["cems-emsr718-aoi02-del-monit01-v2"] == "potential_conflict"
    assert finding_statuses["gsi-gwlevel-gsi-11-20240415t0600z"] == "contextual_support"
    assert finding_statuses["met-eireann-1975-20240415"] == "contextual_support"

    # 2) Indirect evidence ONLY (even record lake stage 69.37 mAOD + rainfall) MUST NOT prove road flooding
    indirect_only = engine.assess(
        ClaimRequest.model_validate(scenarios["indirect_only_insufficient"]["claim"]),
        [Evidence.model_validate(e) for e in scenarios["indirect_only_insufficient"]["evidence"]],
    )
    assert indirect_only.status == "insufficient_evidence"
    assert "INDIRECT_EVIDENCE_ONLY" in indirect_only.reasons
    assert any("indirect contextual indicators" in lim.lower() for lim in indirect_only.limitations)

    # 3) Shared upstream derived products MUST NOT count as 2 independent corroborations
    shared = engine.assess(
        ClaimRequest.model_validate(scenarios["shared_upstream_derived"]["claim"]),
        [Evidence.model_validate(e) for e in scenarios["shared_upstream_derived"]["evidence"]],
    )
    assert shared.independence is not None
    assert shared.independence.status == "shared_dependencies_detected"
    assert shared.independence.independent_group_count == 1
    assert len(shared.independence.correlated_groups) == 1
    assert len(shared.independence.correlated_groups[0]) == 2

    # 4) Direct-vs-direct disagreement preserves both per-source findings & potential_conflict precedence
    disagree = engine.assess(
        ClaimRequest.model_validate(scenarios["direct_disagreement_synthetic"]["claim"]),
        [Evidence.model_validate(e) for e in scenarios["direct_disagreement_synthetic"]["evidence"]],
    )
    assert disagree.status == "potential_conflict"
    assert {f.status for f in disagree.findings} == {"potential_conflict", "no_mapped_overlap"}
    assert any("disagree" in lim.lower() for lim in disagree.limitations)

    # 5) Decision-time unavailable blocks post-decision publication AND flags unknown availability
    dt_unavail = engine.assess(
        ClaimRequest.model_validate(scenarios["decision_time_unavailable"]["claim"]),
        [Evidence.model_validate(e) for e in scenarios["decision_time_unavailable"]["evidence"]],
    )
    assert dt_unavail.status == "insufficient_evidence"
    assert set(dt_unavail.reasons) == {
        "AVAILABILITY_TIME_UNKNOWN",
        "NOT_AVAILABLE_AT_DECISION_TIME",
    }
    assert dt_unavail.temporal_context is not None
    assert dt_unavail.temporal_context.unknown_availability_ids == [
        "gsi-gwlevel-gsi-11-20240415t0600z"
    ]
    assert dt_unavail.temporal_context.excluded_not_available_ids == [
        "synthetic-delayed-publication-cems"
    ]


def test_live_api_assess_against_default_three_source_evidence() -> None:
    evidence = load_evidence_file()
    client = TestClient(create_app(store=InMemoryEvidenceStore(evidence)))
    examples = json.loads((REPO_ROOT / "sample_data" / "example_claims.json").read_text())

    # Flooded road -> potential_conflict corroborated by 3 independent genuine sources
    res = client.post("/v1/assess", json=examples[0]["claim"])
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "potential_conflict"
    assert len(body["findings"]) == 3
    assert body["independence"]["status"] == "distinct_declared_sources"
    assert body["independence"]["independent_group_count"] == 3
