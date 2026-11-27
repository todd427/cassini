"""Acceptance tests for EIP v0.2 architecture: domain-independence, policies,
temporal integrity (retrospective vs decision-time), source independence,
integrity verification, discovery API, and non-geographical extensibility.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from core.engine import AssessmentEngine
from core.integrity import verify_evidence_checksum
from core.models import ClaimRequest, Evidence
from core.policy import PolicyRegistry
from core.store import InMemoryEvidenceStore
from policies import build_default_registry
from tests.fixtures.cold_chain_policy import ColdChainTestPolicy

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _flood_ev(ev_id: str = "ev-1", **overrides) -> dict:
    base = {
        "id": ev_id,
        "source": "synthetic_cems",
        "product_id": f"PROD-{ev_id}",
        "observed_at": "2026-01-01T10:00:00Z",
        "available_at": "2026-01-01T11:00:00Z",
        "retrieved_at": "2026-01-02T10:00:00Z",
        "kind": "flood_extent",
        "geometry": {
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
        },
        "coverage": {
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
        },
        "authentication": "unknown",
        "limitations": ["Synthetic test evidence."],
        "synthetic": True,
    }
    base.update(overrides)
    return base


def _road_claim(**overrides) -> dict:
    base = {
        "claim_id": "road-v02-1",
        "claim_type": "road_passable",
        "geometry": {
            "type": "LineString",
            "coordinates": [[-7.745, 54.955], [-7.725, 54.955]],
        },
        "claimed_at": "2026-01-01T12:00:00Z",
        "source_label": "Synthetic road report",
        "synthetic": True,
    }
    base.update(overrides)
    return base


def test_generic_core_engine_contains_no_flood_road_rules() -> None:
    """Verify generic core modules contain zero flood-road rules or policy imports."""
    generic_core_files = [
        REPO_ROOT / "core" / "engine.py",
        REPO_ROOT / "core" / "models.py",
        REPO_ROOT / "core" / "policy.py",
        REPO_ROOT / "core" / "temporal.py",
        REPO_ROOT / "core" / "spatial.py",
        REPO_ROOT / "core" / "independence.py",
        REPO_ROOT / "core" / "integrity.py",
        REPO_ROOT / "core" / "store.py",
    ]
    forbidden_terms = [
        "flood_extent",
        "road_passable",
        "FLOOD_EXTENT_INTERSECTS",
        "NO_MAPPED_OVERLAP",
        "flood-road",
        "FloodRoadPolicy",
        "from policies",
    ]
    for path in generic_core_files:
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in text, f"Domain-specific term '{term}' leaked into {path.name}"


def test_discovery_endpoints_and_unsupported_claim_type() -> None:
    app = create_app(store=InMemoryEvidenceStore([]))
    client = TestClient(app)

    caps = client.get("/v1/capabilities")
    assert caps.status_code == 200
    caps_body = caps.json()
    assert caps_body["contract_version"] == "0.2"
    assert "0.1" in caps_body["compatible_contract_versions"]
    assert "road_passable" in caps_body["supported_claim_types"]
    assert "flood_extent" in caps_body["supported_evidence_kinds"]
    assert "flood-road" in caps_body["registered_policy_ids"]
    assert caps_body["assessment_modes"] == ["retrospective", "decision_time"]

    pols = client.get("/v1/policies")
    assert pols.status_code == 200
    pol_list = pols.json()["policies"]
    flood_pols = [p for p in pol_list if p["policy_id"] == "flood-road"]
    assert len(flood_pols) == 1
    assert flood_pols[0]["policy_version"] == "flood-road-0.1"
    assert flood_pols[0]["thresholds"]["max_age_hours"] == 24.0
    assert "FLOOD_EXTENT_INTERSECTS" in flood_pols[0]["reason_explanations"]

    # Unsupported claim_type returns explicit structured HTTP 422
    bad = client.post("/v1/assess", json=_road_claim(claim_type="nonexistent_domain_claim"))
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert detail["error"] == "unsupported_claim_type"
    assert detail["claim_type"] == "nonexistent_domain_claim"
    assert "road_passable" in detail["supported_claim_types"]

    # Unknown explicit policy_id returns explicit structured HTTP 422
    bad_pol = client.post("/v1/assess", json=_road_claim(policy_id="missing-policy"))
    assert bad_pol.status_code == 422
    assert bad_pol.json()["detail"]["error"] == "unknown_policy"


def test_decision_time_blocks_future_observations_and_post_decision_publication() -> None:
    # Ev A: observed AFTER decision_time (future observation)
    ev_future_obs = Evidence.model_validate(
        _flood_ev(
            "ev-future-obs",
            observed_at="2026-01-01T15:00:00Z",
            available_at="2026-01-01T16:00:00Z",
        )
    )
    # Ev B: observed BEFORE decision_time, but published/available AFTER decision_time
    ev_late_pub = Evidence.model_validate(
        _flood_ev(
            "ev-late-pub",
            observed_at="2026-01-01T10:00:00Z",
            available_at="2026-01-01T14:00:00Z",
        )
    )
    # Ev C: observed & available BEFORE decision_time
    ev_available = Evidence.model_validate(
        _flood_ev(
            "ev-available",
            observed_at="2026-01-01T09:00:00Z",
            available_at="2026-01-01T11:30:00Z",
        )
    )
    # Ev D: observed before decision_time, but available_at is UNKNOWN (null)
    ev_unknown_avail = Evidence.model_validate(
        _flood_ev(
            "ev-unknown-avail",
            observed_at="2026-01-01T10:00:00Z",
            available_at=None,
        )
    )

    decision_time = "2026-01-01T12:30:00Z"

    # 1) Retrospective mode STILL evaluates future observation & late publication (historical replay preserved)
    app_retro = create_app(store=InMemoryEvidenceStore([ev_future_obs, ev_late_pub]))
    client_retro = TestClient(app_retro)
    res_retro = client_retro.post(
        "/v1/assess",
        json=_road_claim(assessment_mode="retrospective"),
    )
    assert res_retro.status_code == 200
    assert res_retro.json()["status"] == "potential_conflict"
    assert res_retro.json()["assessment_mode"] == "retrospective"
    assert "X-EIP-Assessed-At" in res_retro.headers

    # 2) Decision-time mode BLOCKS both future observation and late publication
    res_dt_blocked = client_retro.post(
        "/v1/assess",
        json=_road_claim(
            assessment_mode="decision_time",
            decision_time=decision_time,
            assessed_at="2026-01-02T09:00:00Z",
        ),
    )
    assert res_dt_blocked.status_code == 200
    body_blocked = res_dt_blocked.json()
    assert body_blocked["status"] == "insufficient_evidence"
    assert body_blocked["reasons"] == ["NOT_AVAILABLE_AT_DECISION_TIME"]
    assert set(body_blocked["temporal_context"]["excluded_not_available_ids"]) == {
        "ev-future-obs",
        "ev-late-pub",
    }
    assert body_blocked["temporal_context"]["decision_time"] == decision_time
    assert body_blocked["traceability"]["assessed_at"] == "2026-01-02T09:00:00Z"
    assert len(body_blocked["traceability"]["input_fingerprint"]) == 64

    # 3) Decision-time mode with unknown available_at communicates uncertainty explicitly
    app_unk = create_app(store=InMemoryEvidenceStore([ev_unknown_avail]))
    res_unk = TestClient(app_unk).post(
        "/v1/assess",
        json=_road_claim(assessment_mode="decision_time", decision_time=decision_time),
    )
    assert res_unk.status_code == 200
    body_unk = res_unk.json()
    assert body_unk["status"] == "insufficient_evidence"
    assert body_unk["reasons"] == ["AVAILABILITY_TIME_UNKNOWN"]
    assert body_unk["temporal_context"]["unknown_availability_ids"] == ["ev-unknown-avail"]
    assert any("available_at" in lim for lim in body_unk["limitations"])

    # 4) Decision-time mode with demonstrably available evidence evaluates normally
    app_ok = create_app(store=InMemoryEvidenceStore([ev_available]))
    res_ok = TestClient(app_ok).post(
        "/v1/assess",
        json=_road_claim(assessment_mode="decision_time", decision_time=decision_time),
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "potential_conflict"
    assert res_ok.json()["reasons"] == ["FLOOD_EXTENT_INTERSECTS"]

    # 5) decision_time mode without decision_time returns 422
    res_missing_dt = TestClient(app_ok).post(
        "/v1/assess",
        json=_road_claim(assessment_mode="decision_time"),
    )
    assert res_missing_dt.status_code == 422


def test_source_independence_shared_upstream_and_unknown_cases() -> None:
    engine = AssessmentEngine(build_default_registry())
    claim = ClaimRequest.model_validate(_road_claim())

    # 1) Two products derived from the same upstream satellite acquisition -> NOT independent
    ev_a = Evidence.model_validate(
        _flood_ev(
            "ev-cems-v1",
            provenance={
                "original_source": "COSMO-SkyMed Second Generation",
                "publishing_organisation": "Copernicus EMS Rapid Mapping",
                "upstream_datasets": ["CSG_20240415_0602_ORTHO"],
                "derived_from": [],
                "measurement_method": "SAR semi-automatic extraction",
                "shared_dependencies": ["EU-DEM-v1.1"],
            },
        )
    )
    ev_b = Evidence.model_validate(
        _flood_ev(
            "ev-partner-reprocess",
            provenance={
                "original_source": "COSMO-SkyMed Second Generation",
                "publishing_organisation": "Downstream Analytics Partner",
                "upstream_datasets": ["CSG_20240415_0602_ORTHO"],
                "derived_from": ["ev-cems-v1"],
                "measurement_method": "SAR flood mask re-classification",
                "shared_dependencies": ["EU-DEM-v1.1"],
            },
        )
    )
    res_shared = engine.assess(claim, [ev_a, ev_b])
    assert res_shared.independence is not None
    assert res_shared.independence.status == "shared_dependencies_detected"
    assert res_shared.independence.assessed_source_count == 2
    assert res_shared.independence.independent_group_count == 1
    assert res_shared.independence.correlated_groups == [["ev-cems-v1", "ev-partner-reprocess"]]
    assert any("upstream_dataset:" in s for s in res_shared.independence.shared_dependencies)
    assert any("not counted as independent" in lim.lower() for lim in res_shared.limitations)

    # 2) Two sources without declared provenance -> independence MUST remain unknown
    ev_no_prov_1 = Evidence.model_validate(_flood_ev("ev-noprov-1", provenance=None))
    ev_no_prov_2 = Evidence.model_validate(_flood_ev("ev-noprov-2", provenance=None))
    res_unknown = engine.assess(claim, [ev_no_prov_1, ev_no_prov_2])
    assert res_unknown.independence is not None
    assert res_unknown.independence.status == "unknown"
    assert res_unknown.independence.independent_group_count is None

    # 3) Two sources with distinct declared upstream lineage -> 2 distinct declared groups
    ev_ind_1 = Evidence.model_validate(
        _flood_ev(
            "ev-sar-s1",
            provenance={
                "original_source": "Sentinel-1A",
                "publishing_organisation": "ESA Copernicus",
                "upstream_datasets": ["S1A_IW_GRDH_20260101"],
                "measurement_method": "C-band SAR",
            },
        )
    )
    ev_ind_2 = Evidence.model_validate(
        _flood_ev(
            "ev-gauge-opw",
            provenance={
                "original_source": "OPW River Gauge Station 26005",
                "publishing_organisation": "Office of Public Works",
                "upstream_datasets": ["OPW_26005_20260101"],
                "measurement_method": "In-situ pressure transducer",
            },
        )
    )
    res_distinct = engine.assess(claim, [ev_ind_1, ev_ind_2])
    assert res_distinct.independence is not None
    assert res_distinct.independence.status == "distinct_declared_sources"
    assert res_distinct.independence.independent_group_count == 2


def test_local_checksum_integrity_helper(tmp_path: Path) -> None:
    artifact = tmp_path / "raw.bin"
    artifact.write_bytes(b"copernicus-test-payload")
    import hashlib

    digest = hashlib.sha256(b"copernicus-test-payload").hexdigest()

    ev_ok = Evidence.model_validate(
        _flood_ev("ev-hash-ok", raw_path="raw.bin", sha256=digest)
    )
    assert verify_evidence_checksum(ev_ok, tmp_path).status == "verified_local_bytes"

    ev_bad = Evidence.model_validate(
        _flood_ev("ev-hash-bad", raw_path="raw.bin", sha256="0" * 64)
    )
    assert verify_evidence_checksum(ev_bad, tmp_path).status == "checksum_mismatch"

    ev_missing = Evidence.model_validate(
        _flood_ev("ev-hash-miss", raw_path="missing.bin", sha256=digest)
    )
    assert verify_evidence_checksum(ev_missing, tmp_path).status == "missing_raw_file"


def test_extensibility_non_geographical_cold_chain_policy_via_api() -> None:
    """Register and invoke a non-geographical policy in a completely different domain
    without modifying any generic engine or API code."""
    registry = build_default_registry()
    registry.register(ColdChainTestPolicy(max_age_hours=6.0))

    # Synthetic non-geographical temperature telemetry (geometry=None!)
    telemetry_excursion = Evidence.model_validate(
        {
            "id": "coldchain-probe-1",
            "source": "synthetic_iot_logger",
            "observed_at": "2026-05-10T09:00:00Z",
            "available_at": "2026-05-10T09:05:00Z",
            "retrieved_at": "2026-05-10T09:10:00Z",
            "kind": "temperature_telemetry",
            "geometry": None,
            "attributes": {"min_temp_c": 3.1, "max_temp_c": 11.4, "unit": "C"},
            "provenance": {
                "original_source": "NTC-Probe-A1",
                "publishing_organisation": "Synthetic ColdChain Telemetry",
                "upstream_datasets": ["LOGGER-BATCH-99"],
                "measurement_method": "Calibrated NTC thermistor",
            },
            "authentication": "unknown",
            "limitations": ["Synthetic non-geographical telemetry fixture."],
            "synthetic": True,
        }
    )
    telemetry_derived_same_probe = Evidence.model_validate(
        {
            "id": "coldchain-dashboard-export-1",
            "source": "synthetic_erp_mirror",
            "observed_at": "2026-05-10T09:00:00Z",
            "available_at": "2026-05-10T09:15:00Z",
            "retrieved_at": "2026-05-10T09:20:00Z",
            "kind": "temperature_telemetry",
            "geometry": None,
            "attributes": {"min_temp_c": 3.1, "max_temp_c": 11.4, "unit": "C"},
            "provenance": {
                "original_source": "NTC-Probe-A1",
                "publishing_organisation": "ERP Mirror",
                "upstream_datasets": ["LOGGER-BATCH-99"],
                "derived_from": ["coldchain-probe-1"],
            },
            "authentication": "unknown",
            "limitations": ["Derived mirror of probe-1."],
            "synthetic": True,
        }
    )
    telemetry_in_range = Evidence.model_validate(
        {
            "id": "coldchain-probe-ok",
            "source": "synthetic_iot_logger",
            "observed_at": "2026-05-10T09:00:00Z",
            "available_at": "2026-05-10T09:05:00Z",
            "kind": "temperature_telemetry",
            "geometry": None,
            "attributes": {"min_temp_c": 2.8, "max_temp_c": 6.2, "unit": "C"},
            "authentication": "unknown",
            "synthetic": True,
        }
    )
    # Also include an unrelated flood_extent record to verify relevance filtering
    unrelated_flood = Evidence.model_validate(_flood_ev("unrelated-flood"))

    app = create_app(
        registry=registry,
        store=InMemoryEvidenceStore(
            [unrelated_flood, telemetry_excursion, telemetry_derived_same_probe]
        ),
    )
    client = TestClient(app)

    # 1) Discovery automatically reflects the newly registered policy
    caps = client.get("/v1/capabilities").json()
    assert "cold_chain_within_limits" in caps["supported_claim_types"]
    assert "temperature_telemetry" in caps["supported_evidence_kinds"]
    assert "test-cold-chain" in caps["registered_policy_ids"]

    # 2) Non-geographical claim detects excursion AND detects shared upstream probe
    cold_claim = {
        "claim_id": "shipment-42",
        "claim_type": "cold_chain_within_limits",
        "geometry": None,
        "claimed_at": "2026-05-10T10:00:00Z",
        "source_label": "Synthetic carrier declaration",
        "synthetic": True,
        "attributes": {"allowed_min_c": 2.0, "allowed_max_c": 8.0},
        "assessment_mode": "decision_time",
        "decision_time": "2026-05-10T10:00:00Z",
    }
    res = client.post("/v1/assess", json=cold_claim)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "potential_conflict"
    assert body["policy_version"] == "test-cold-chain-0.1"
    assert body["reasons"] == ["TEMPERATURE_EXCURSION_DETECTED"]
    assert body["evidence_ids"] == ["coldchain-probe-1", "coldchain-dashboard-export-1"]
    assert body["independence"]["status"] == "shared_dependencies_detected"
    assert body["independence"]["independent_group_count"] == 1

    # 3) Earlier decision_time before telemetry was published blocks future leakage
    early_res = client.post(
        "/v1/assess",
        json={**cold_claim, "decision_time": "2026-05-10T09:02:00Z"},
    )
    assert early_res.status_code == 200
    assert early_res.json()["status"] == "insufficient_evidence"
    assert early_res.json()["reasons"] == ["NOT_AVAILABLE_AT_DECISION_TIME"]

    # 4) In-range telemetry yields within_limits
    app_ok = create_app(
        registry=registry,
        store=InMemoryEvidenceStore([telemetry_in_range]),
    )
    ok_res = TestClient(app_ok).post("/v1/assess", json=cold_claim)
    assert ok_res.status_code == 200
    assert ok_res.json()["status"] == "within_limits"
    assert ok_res.json()["reasons"] == ["WITHIN_TEMPERATURE_LIMITS"]

    # 5) Invalid cold-chain claim attributes return HTTP 422
    bad_attr = client.post(
        "/v1/assess",
        json={**cold_claim, "attributes": {"allowed_min_c": 10.0, "allowed_max_c": 2.0}},
    )
    assert bad_attr.status_code == 422
    assert bad_attr.json()["detail"]["error"] == "claim_validation_error"


def test_cems_connector_protocol_and_real_emsr718_decision_time_uncertainty() -> None:
    """Real EMSR718 archive has unknown exact UTC publication time (available_at=None),
    so decision_time mode must report AVAILABILITY_TIME_UNKNOWN while retrospective
    mode preserves v0.1 potential_conflict."""
    from connectors.base import EvidenceConnector
    from connectors.cems_rapid_mapping import CemsRapidMappingConnector

    connector = CemsRapidMappingConnector(retrieved_at="2026-11-27T16:00:00Z")
    assert isinstance(connector, EvidenceConnector)
    items = connector.load_evidence()
    assert len(items) == 1
    ev = items[0]
    assert ev.synthetic is False
    assert ev.available_at is None
    assert ev.provenance is not None
    assert ev.provenance.original_source == "COSMO-SkyMed"
    assert ev.provenance.publishing_organisation == "Copernicus EMS Rapid Mapping"

    examples = json.loads((REPO_ROOT / "sample_data" / "example_claims.json").read_text())
    intersect_claim = examples[0]["claim"]
    engine = AssessmentEngine(build_default_registry())

    # Retrospective replay matches v0.1 behaviour
    retro = engine.assess(ClaimRequest.model_validate(intersect_claim), items)
    assert retro.status == "potential_conflict"
    assert retro.reasons == ["FLOOD_EXTENT_INTERSECTS"]

    # Decision-time mode refuses to assume unknown available_at preceded decision
    dt_claim = ClaimRequest.model_validate(
        {
            **intersect_claim,
            "assessment_mode": "decision_time",
            "decision_time": "2024-04-15T08:00:00Z",
        }
    )
    dt_res = engine.assess(dt_claim, items)
    assert dt_res.status == "insufficient_evidence"
    assert dt_res.reasons == ["AVAILABILITY_TIME_UNKNOWN"]
    assert dt_res.temporal_context is not None
    assert dt_res.temporal_context.unknown_availability_ids == [ev.id]


def test_policy_registry_prevents_duplicate_ids_and_claim_types() -> None:
    import pytest

    registry = PolicyRegistry()
    registry.register(ColdChainTestPolicy())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ColdChainTestPolicy())

