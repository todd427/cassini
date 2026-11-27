"""Comprehensive tests for EIP Core engine and FastAPI service (Contract v0.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.models import Evidence
from core.store import load_evidence_file


def _base_flood_evidence(**overrides) -> dict:
    base = {
        "id": "fixture-flood-1",
        "source": "fixture",
        "product_id": None,
        "source_url": None,
        "observed_at": "2026-01-01T10:00:00Z",
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
        "sha256": None,
        "raw_path": None,
        "licence": None,
        "limitations": ["Synthetic fixture, not an actual flood"],
        "synthetic": True,
    }
    base.update(overrides)
    return base


def _base_claim(**overrides) -> dict:
    base = {
        "claim_id": "road-1",
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


def _make_client(tmp_path: Path, evidence_items: list[dict]) -> TestClient:
    ev_file = tmp_path / "evidence.json"
    ev_file.write_text(json.dumps(evidence_items), encoding="utf-8")
    return TestClient(create_app(evidence_path=ev_file))


def test_health_and_openapi(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence()])
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "contract_version": "0.1"}

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/health" in paths
    assert "/v1/evidence" in paths
    assert "/v1/assess" in paths


def test_cors_restricted_to_localhost_5173(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [])
    allowed = client.options(
        "/v1/assess",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    blocked = client.options(
        "/v1/assess",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in blocked.headers


def test_list_evidence(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence()])
    res = client.get("/v1/evidence")
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == "fixture-flood-1"
    assert body["items"][0]["observed_at"] == "2026-01-01T10:00:00Z"


def test_fresh_overlap_potential_conflict_and_determinism(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence(coverage=None)])
    claim = _base_claim()
    res1 = client.post("/v1/assess", json=claim)
    res2 = client.post("/v1/assess", json=claim)
    assert res1.status_code == 200
    assert res1.json() == res2.json()

    body = res1.json()
    assert body["claim_id"] == "road-1"
    assert body["status"] == "potential_conflict"
    assert body["policy_version"] == "flood-road-0.1"
    assert body["reasons"] == ["FLOOD_EXTENT_INTERSECTS"]
    assert body["evidence_ids"] == ["fixture-flood-1"]
    assert body["findings"] == [
        {
            "evidence_id": "fixture-flood-1",
            "status": "potential_conflict",
            "age_hours": 2.0,
            "reasons": ["FLOOD_EXTENT_INTERSECTS"],
        }
    ]
    assert body["synthetic"] is True
    assert any("impassability" in lim.lower() for lim in body["limitations"])
    assert any("unverified" in lim.lower() for lim in body["limitations"])


def test_historical_replay_accepts_observation_after_claim_within_24h(tmp_path: Path) -> None:
    # Observed 5 hours AFTER claim time, still within 24h historical replay window
    ev = _base_flood_evidence(observed_at="2026-01-01T17:00:00Z")
    client = _make_client(tmp_path, [ev])
    res = client.post("/v1/assess", json=_base_claim(claimed_at="2026-01-01T12:00:00Z"))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "potential_conflict"
    assert body["findings"][0]["age_hours"] == 5.0


def test_covered_non_overlap(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence()])
    # Road inside coverage [-7.76..-7.71, 54.94..54.97] but south of flood [54.95..54.96]
    claim = _base_claim(
        claim_id="road-covered-clear",
        geometry={"type": "LineString", "coordinates": [[-7.75, 54.945], [-7.72, 54.945]]},
    )
    res = client.post("/v1/assess", json=claim)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_mapped_overlap"
    assert body["reasons"] == ["NO_MAPPED_OVERLAP"]
    assert any("safety" in lim.lower() or "passability" in lim.lower() for lim in body["limitations"])


def test_unknown_coverage_non_overlap_is_insufficient(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence(coverage=None)])
    claim = _base_claim(
        claim_id="road-no-cov",
        geometry={"type": "LineString", "coordinates": [[-7.75, 54.945], [-7.72, 54.945]]},
    )
    res = client.post("/v1/assess", json=claim)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "insufficient_evidence"
    assert body["reasons"] == ["COVERAGE_UNKNOWN"]


def test_outside_coverage_completely_and_partially(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence()])

    # Completely outside coverage
    claim_out = _base_claim(
        claim_id="road-out",
        geometry={"type": "LineString", "coordinates": [[-7.90, 54.95], [-7.85, 54.95]]},
    )
    res_out = client.post("/v1/assess", json=claim_out)
    assert res_out.status_code == 200
    assert res_out.json()["status"] == "insufficient_evidence"
    assert res_out.json()["reasons"] == ["OUTSIDE_COVERAGE"]

    # Partially inside coverage, not intersecting flood
    claim_partial = _base_claim(
        claim_id="road-partial",
        geometry={"type": "LineString", "coordinates": [[-7.80, 54.945], [-7.75, 54.945]]},
    )
    res_partial = client.post("/v1/assess", json=claim_partial)
    assert res_partial.status_code == 200
    assert res_partial.json()["status"] == "insufficient_evidence"
    assert res_partial.json()["reasons"] == ["OUTSIDE_COVERAGE"]


def test_stale_observation_is_insufficient(tmp_path: Path) -> None:
    # 30 hours before claim
    ev = _base_flood_evidence(observed_at="2025-12-31T06:00:00Z")
    client = _make_client(tmp_path, [ev])
    res = client.post("/v1/assess", json=_base_claim(claimed_at="2026-01-01T12:00:00Z"))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "insufficient_evidence"
    assert body["reasons"] == ["OBSERVATION_STALE"]
    assert body["findings"][0]["age_hours"] == 30.0


def test_unknown_observation_time_is_insufficient(tmp_path: Path) -> None:
    ev = _base_flood_evidence(observed_at=None)
    client = _make_client(tmp_path, [ev])
    res = client.post("/v1/assess", json=_base_claim())
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "insufficient_evidence"
    assert body["reasons"] == ["OBSERVATION_TIME_UNKNOWN"]
    assert body["findings"][0]["age_hours"] is None


def test_failed_authentication_excluded(tmp_path: Path) -> None:
    ev = _base_flood_evidence(authentication="failed")
    client = _make_client(tmp_path, [ev])
    res = client.post("/v1/assess", json=_base_claim())
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "insufficient_evidence"
    assert body["reasons"] == ["AUTHENTICATION_FAILED"]
    assert any("failed authentication" in lim.lower() for lim in body["limitations"])


def test_empty_dataset(tmp_path: Path) -> None:
    client = _make_client(tmp_path, [])
    res = client.post("/v1/assess", json=_base_claim())
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "insufficient_evidence"
    assert body["reasons"] == ["NO_EVIDENCE"]
    assert body["evidence_ids"] == []
    assert body["findings"] == []


def test_multiple_findings_precedence_and_synthetic_propagation(tmp_path: Path) -> None:
    ev_stale = _base_flood_evidence(
        id="ev-stale",
        observed_at="2025-12-25T10:00:00Z",
        synthetic=False,
    )
    ev_clear = _base_flood_evidence(
        id="ev-clear",
        observed_at="2026-01-01T11:00:00Z",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-7.72, 54.96],
                    [-7.715, 54.96],
                    [-7.715, 54.965],
                    [-7.72, 54.965],
                    [-7.72, 54.96],
                ]
            ],
        },
        synthetic=False,
    )
    ev_hit = _base_flood_evidence(
        id="ev-hit",
        observed_at="2026-01-01T10:00:00Z",
        synthetic=False,
    )

    # 1) stale + clear => no_mapped_overlap, synthetic False when claim & evidence real
    client_clear = _make_client(tmp_path, [ev_stale, ev_clear])
    res_clear = client_clear.post("/v1/assess", json=_base_claim(synthetic=False))
    assert res_clear.status_code == 200
    body_clear = res_clear.json()
    assert body_clear["status"] == "no_mapped_overlap"
    assert body_clear["reasons"] == ["NO_MAPPED_OVERLAP", "OBSERVATION_STALE"]
    assert body_clear["synthetic"] is False
    assert len(body_clear["findings"]) == 2
    assert any("correlated" in lim.lower() for lim in body_clear["limitations"])

    # 2) stale + clear + hit => potential_conflict takes precedence
    client_hit = _make_client(tmp_path, [ev_stale, ev_clear, ev_hit])
    res_hit = client_hit.post("/v1/assess", json=_base_claim(synthetic=False))
    assert res_hit.status_code == 200
    body_hit = res_hit.json()
    assert body_hit["status"] == "potential_conflict"
    assert body_hit["reasons"][0] == "FLOOD_EXTENT_INTERSECTS"
    assert set(body_hit["evidence_ids"]) == {"ev-stale", "ev-clear", "ev-hit"}

    # 3) real claim + one synthetic evidence => synthetic True
    ev_synth = _base_flood_evidence(id="ev-synth", synthetic=True)
    client_synth = _make_client(tmp_path, [ev_clear, ev_synth])
    res_synth = client_synth.post("/v1/assess", json=_base_claim(synthetic=False))
    assert res_synth.status_code == 200
    assert res_synth.json()["synthetic"] is True


@pytest.mark.parametrize(
    "bad_override",
    [
        {"claimed_at": "2026-01-01T12:00:00"},  # naive timestamp
        {"geometry": {"type": "Point", "coordinates": [-7.74, 54.95]}},  # wrong type
        {"geometry": {"type": "LineString", "coordinates": [[-7.74, 54.95]]}},  # < 2 pts
        {"geometry": {"type": "LineString", "coordinates": [[-7.74, 54.95], [-7.74, 54.95]]}},  # zero length
        {"geometry": {"type": "LineString", "coordinates": [[-190.0, 54.95], [-7.73, 54.95]]}},  # lon out of range
        {"geometry": {"type": "LineString", "coordinates": [[-7.74, 95.0], [-7.73, 54.95]]}},  # lat out of range
        {"claim_type": "bridge_safe"},  # unsupported claim_type
        {"unexpected_extra_field": "nope"},  # extra field forbidden
    ],
)
def test_malformed_claims_return_422(tmp_path: Path, bad_override: dict) -> None:
    client = _make_client(tmp_path, [_base_flood_evidence()])
    payload = _base_claim(**bad_override)
    res = client.post("/v1/assess", json=payload)
    assert res.status_code == 422


def test_evidence_validation_rejects_bowtie_polygon_and_unsafe_paths(tmp_path: Path) -> None:
    # Self-intersecting bowtie polygon must be rejected, not silently repaired
    bowtie = _base_flood_evidence(
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-7.74, 54.95],
                    [-7.73, 54.96],
                    [-7.73, 54.95],
                    [-7.74, 54.96],
                    [-7.74, 54.95],
                ]
            ],
        }
    )
    with pytest.raises(Exception):
        Evidence.model_validate(bowtie)

    # URL in raw_path rejected
    with pytest.raises(Exception):
        Evidence.model_validate(_base_flood_evidence(raw_path="https://example.com/a.zip"))

    # Traversal in raw_path rejected
    with pytest.raises(Exception):
        Evidence.model_validate(_base_flood_evidence(raw_path="../secret.zip"))

    # Duplicate IDs in store rejected
    dup_file = tmp_path / "dup.json"
    dup_file.write_text(
        json.dumps([_base_flood_evidence(id="dup-1"), _base_flood_evidence(id="dup-1")]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate evidence id"):
        load_evidence_file(dup_file)
