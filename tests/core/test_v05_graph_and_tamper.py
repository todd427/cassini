"""EIP v0.5 backend tests: domain-independent evidence graph, Galileo controlled
offline tamper comparison API, and local offline Lough Funshinagh display context.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from core.models import Evidence
from core.store import InMemoryEvidenceStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_core_graph_contains_no_domain_specific_rules() -> None:
    text = (REPO_ROOT / "core" / "graph.py").read_text(encoding="utf-8")
    for forbidden in (
        "flood_extent",
        "road_passable",
        "FLOOD_EXTENT_INTERSECTS",
        "gnss_osnma_auth",
        "FloodRoadPolicy",
        "GalileoOsnmaPolicy",
    ):
        assert forbidden not in text


def test_assess_graph_environmental_multi_source_and_missing_evidence() -> None:
    client = TestClient(create_app())
    examples = json.loads((REPO_ROOT / "sample_data" / "example_claims.json").read_text())

    res = client.post("/v1/assess/graph", json=examples[0]["claim"])
    assert res.status_code == 200
    assert "X-EIP-Assessed-At" in res.headers
    body = res.json()

    assert body["assessment"]["status"] == "potential_conflict"
    graph = body["graph"]
    assert graph["independence_status"] == "distinct_declared_sources"
    assert graph["independent_group_count"] == 3
    assert graph["assessed_source_count"] == 3

    node_types = {n["node_type"] for n in graph["nodes"]}
    assert {"claim", "evidence", "original_source", "publisher", "upstream_dependency"}.issubset(
        node_types
    )
    ev_nodes = [n for n in graph["nodes"] if n["node_type"] == "evidence"]
    assert len(ev_nodes) == 3
    roles = {n["metadata"]["evidence_id"]: n["relation_role"] for n in ev_nodes}
    assert roles["cems-emsr718-aoi02-del-monit01-v2"] == "potentially_contradicting"
    assert roles["gsi-gwlevel-gsi-11-20240415t0600z"] == "contextual"
    assert roles["met-eireann-1975-20240415"] == "contextual"

    # Empty store -> explicit missing_evidence node
    empty_client = TestClient(create_app(store=InMemoryEvidenceStore([])))
    miss_res = empty_client.post("/v1/assess/graph", json=examples[0]["claim"])
    assert miss_res.status_code == 200
    miss_nodes = miss_res.json()["graph"]["nodes"]
    assert any(n["node_type"] == "missing_evidence" for n in miss_nodes)


def test_assess_graph_highlights_shared_upstream_dependencies() -> None:
    ev1 = Evidence.model_validate(
        {
            "id": "src-a",
            "source": "pub_a",
            "observed_at": "2026-01-01T10:00:00Z",
            "kind": "flood_extent",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-7.74, 54.95], [-7.73, 54.95], [-7.73, 54.96], [-7.74, 54.96], [-7.74, 54.95]]],
            },
            "provenance": {
                "original_source": "COSMO-SkyMed",
                "publishing_organisation": "Org A",
                "upstream_datasets": ["SHARED_PASS_01"],
            },
            "synthetic": True,
        }
    )
    ev2 = Evidence.model_validate(
        {
            "id": "src-b",
            "source": "pub_b",
            "observed_at": "2026-01-01T10:00:00Z",
            "kind": "flood_extent",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-7.74, 54.95], [-7.73, 54.95], [-7.73, 54.96], [-7.74, 54.96], [-7.74, 54.95]]],
            },
            "provenance": {
                "original_source": "COSMO-SkyMed",
                "publishing_organisation": "Org B",
                "upstream_datasets": ["SHARED_PASS_01"],
                "derived_from": ["src-a"],
            },
            "synthetic": True,
        }
    )
    client = TestClient(create_app(store=InMemoryEvidenceStore([ev1, ev2])))
    res = client.post(
        "/v1/assess/graph",
        json={
            "claim_id": "shared-test",
            "claim_type": "road_passable",
            "geometry": {"type": "LineString", "coordinates": [[-7.745, 54.955], [-7.725, 54.955]]},
            "claimed_at": "2026-01-01T12:00:00Z",
            "source_label": "Synthetic shared-upstream test",
            "synthetic": True,
        },
    )
    assert res.status_code == 200
    graph = res.json()["graph"]
    assert graph["independence_status"] == "shared_dependencies_detected"
    assert graph["independent_group_count"] == 1
    assert any(e["relation"] == "derived_from" and e["shared"] is True for e in graph["edges"])
    assert any(
        n["node_type"] == "upstream_dependency" and n["status"] == "shared"
        for n in graph["nodes"]
    )


def test_galileo_tamper_demo_api_and_local_context_endpoint() -> None:
    client = TestClient(create_app())

    res = client.post("/v1/galileo/tamper-demo")
    assert res.status_code == 200
    body = res.json()
    assert body["tamper_details"]["sbf_block_crc_recomputed"] is True
    assert body["tamper_details"]["original_word_hex"] != body["tamper_details"]["tampered_word_hex"]

    orig = body["original"]
    tamp = body["tampered"]
    assert orig["assessment"]["status"] == "authenticated"
    assert orig["evidence"][0]["synthetic"] is False
    assert orig["evidence"][0]["attributes"]["tag0_verified_count"] == 188

    assert tamp["assessment"]["status"] == "authentication_failed"
    assert tamp["assessment"]["reasons"] == ["AUTHENTICATION_FAILED"]
    assert tamp["evidence"][0]["synthetic"] is True
    assert tamp["evidence"][0]["attributes"]["merkle_proof_verified"] is True
    assert tamp["evidence"][0]["attributes"]["ecdsa_kroot_verified"] is True
    assert tamp["evidence"][0]["attributes"]["tag0_failed_count"] >= 1

    ctx = client.get("/v1/context/lough-funshinagh")
    assert ctx.status_code == 200
    ctx_body = ctx.json()
    assert ctx_body["display_only"] is True
    assert len(ctx_body["baseline_water_extent"]["features"]) == 1
    assert len(ctx_body["landmarks"]["features"]) >= 4
