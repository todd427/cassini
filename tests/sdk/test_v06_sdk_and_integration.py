"""Integration and isolation tests for EIP v0.6.0 Python SDK, CLI, and external workflows."""

from __future__ import annotations

import ast
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn

from api.main import create_app
from core.models import Evidence
from core.store import InMemoryEvidenceStore
from eip_sdk import (
    ClaimInput,
    EIPClient,
    EIPConnectionError,
    EIPTimeoutError,
    EIPUnknownPolicyError,
    EIPUnsupportedClaimError,
    EIPValidationError,
    RawHTTPResponse,
)
from policies import build_default_registry
from tests.fixtures.cold_chain_policy import ColdChainTestPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _run_uvicorn_app(app):
    """Run a FastAPI app on an ephemeral localhost port for genuine HTTP SDK testing."""
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10.0
    ready = False
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.05)

    if not ready:
        server.should_exit = True
        thread.join(timeout=2.0)
        raise RuntimeError("Test uvicorn server failed to start within 10s.")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


@pytest.fixture(scope="module")
def live_default_api() -> str:
    app = create_app()
    with _run_uvicorn_app(app) as base_url:
        yield base_url


def test_sdk_and_examples_never_import_internal_eip_modules() -> None:
    """Guarantee strict REST-only boundary: zero imports of core, policies, connectors, or api."""
    forbidden_roots = {"core", "policies", "connectors", "api"}
    scan_dirs = [REPO_ROOT / "eip_sdk", REPO_ROOT / "examples"]

    for directory in scan_dirs:
        py_files = sorted(directory.rglob("*.py"))
        assert py_files, f"Expected Python files in {directory}"
        for path in py_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        assert root not in forbidden_roots, (
                            f"{path.relative_to(REPO_ROOT)} imports forbidden internal package '{alias.name}'"
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    assert root not in forbidden_roots, (
                        f"{path.relative_to(REPO_ROOT)} imports from forbidden internal package '{node.module}'"
                    )


def test_sdk_discovery_provenance_environmental_galileo_decision_time_and_graph(
    live_default_api: str,
    tmp_path: Path,
) -> None:
    """Exercise all core EIPClient capabilities against the live REST API."""
    client = EIPClient(live_default_api, timeout=5.0)

    # 1. Health, compatibility, and discovery
    health = client.health()
    assert health.status == "ok"
    assert health.contract_version == "0.1"

    caps = client.check_compatibility()
    assert "road_passable" in caps.supported_claim_types
    assert "gnss_nav_message_authenticated" in caps.supported_claim_types
    assert "flood_extent" in caps.supported_evidence_kinds
    assert "gnss_osnma_auth" in caps.supported_evidence_kinds
    assert client.supported_claim_types() == caps.supported_claim_types
    assert client.supported_evidence_kinds() == caps.supported_evidence_kinds

    policies = client.list_policies()
    assert {p.policy_id for p in policies} >= {"flood-road", "galileo-osnma"}
    assert client.get_policy("flood-road") is not None
    assert client.get_policy("nonexistent-policy") is None

    # 2. Evidence & provenance retrieval
    all_ev = client.list_evidence()
    assert len(all_ev) == 4
    galileo_ev = client.list_evidence(kind="gnss_osnma_auth")
    assert len(galileo_ev) == 1
    assert galileo_ev[0].authentication == "verified"
    assert galileo_ev[0].synthetic is False

    # 3. Environmental assessment (conflict + covered non-overlap)
    conflict_claim = ClaimInput.road_passable(
        claim_id="sdk-env-conflict",
        coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
        claimed_at="2024-04-15T08:00:00Z",
        source_label="Synthetic SDK test claim (Ballagh East)",
        synthetic=True,
    )
    env_res = client.assess(conflict_claim)
    assert env_res.is_conflict
    assert env_res.status == "potential_conflict"
    assert "FLOOD_EXTENT_INTERSECTS" in env_res.reasons
    assert env_res.assessed_at_header is not None
    assert env_res.independence is not None
    assert env_res.independence.independent_group_count == 3

    clear_claim = ClaimInput.road_passable(
        claim_id="sdk-env-clear",
        coordinates=[[-8.175, 53.462], [-8.155, 53.462]],
        claimed_at="2024-04-15T08:00:00Z",
        source_label="Synthetic SDK test claim (Rahara South)",
        synthetic=True,
    )
    clear_res = client.assess(clear_claim)
    assert clear_res.status == "no_mapped_overlap"
    assert clear_res.requires_caution is True

    # 4. Galileo OSNMA assessment through the exact same SDK client
    galileo_claim = ClaimInput.galileo_nav_auth(
        claim_id="sdk-galileo-e27",
        claimed_at="2023-08-27T20:10:00Z",
        source_label="Synthetic SDK test claim (Galileo E27)",
        svid=27,
        synthetic=True,
    )
    gal_res = client.assess(galileo_claim)
    assert gal_res.is_authenticated
    assert gal_res.policy_version == "galileo-osnma-0.1"
    assert "OSNMA_LOCALLY_VERIFIED" in gal_res.reasons

    pos_claim = ClaimInput.custom(
        claim_id="sdk-galileo-pos-unsuitable",
        claim_type="gnss_position_accurate",
        claimed_at="2023-08-27T20:10:00Z",
        source_label="Synthetic positioning claim",
        synthetic=True,
    )
    pos_res = client.assess(pos_claim)
    assert pos_res.status == "evidence_unsuitable"
    assert "NAV_AUTH_INSUFFICIENT_FOR_POSITIONING" in pos_res.reasons

    # 5. Decision-time auditing
    dt_res = client.assess_decision_time(conflict_claim, decision_time="2024-04-15T08:00:00Z")
    assert dt_res.is_insufficient
    assert "AVAILABILITY_TIME_UNKNOWN" in dt_res.reasons
    assert dt_res.temporal_context is not None
    assert len(dt_res.temporal_context.unknown_availability_ids) == 3

    # 6. Evidence graph & auditable report export
    graph_res = client.assess_with_graph(conflict_claim)
    assert len(graph_res.graph.evidence_nodes()) == 3
    assert len(graph_res.graph.upstream_nodes()) >= 6
    assert graph_res.graph.independent_group_count == 3

    report_path = tmp_path / "audit_report.json"
    report = client.export_report(conflict_claim, report_path, include_graph=True)
    assert report_path.exists()
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["report_schema_version"] == "eip-report-0.6"
    assert loaded["assessment"]["status"] == "potential_conflict"
    assert len(loaded["evidence_provenance"]) == 3
    assert loaded["graph"] is not None
    assert "not a truth oracle" in loaded["disclaimer"].lower()
    assert report.server_assessed_at is not None


def test_sdk_explicit_errors_without_silent_mock_fallback(live_default_api: str) -> None:
    """Unsupported claims, unknown policies, validation errors, and dead endpoints fail explicitly."""
    client = EIPClient(live_default_api, timeout=3.0)

    # Unsupported claim_type
    with pytest.raises(EIPUnsupportedClaimError) as exc_info:
        client.assess(
            ClaimInput.custom(
                claim_id="bad-claim-type",
                claim_type="hypothetical_unregistered_claim",
                claimed_at="2024-04-15T08:00:00Z",
                source_label="Test",
            )
        )
    assert exc_info.value.status_code == 422
    assert "road_passable" in exc_info.value.supported_claim_types

    # Unknown explicit policy_id
    with pytest.raises(EIPUnknownPolicyError) as pol_exc:
        client.assess(
            ClaimInput.custom(
                claim_id="bad-policy",
                claim_type="road_passable",
                claimed_at="2024-04-15T08:00:00Z",
                source_label="Test",
                policy_id="does-not-exist",
            )
        )
    assert "flood-road" in pol_exc.value.registered_policy_ids

    # Naive timestamp validation error (HTTP 422)
    with pytest.raises(EIPValidationError) as val_exc:
        client.assess(
            ClaimInput.road_passable(
                claim_id="naive-ts",
                coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
                claimed_at="2024-04-15T08:00:00",
                source_label="Naive timestamp test",
            )
        )
    assert val_exc.value.status_code == 422

    # Unavailable server -> EIPConnectionError (never synthetic fallback)
    closed_port = _find_free_port()
    dead_client = EIPClient(f"http://127.0.0.1:{closed_port}", timeout=1.0)
    with pytest.raises(EIPConnectionError):
        dead_client.health()

    # Simulated timeout transport -> EIPTimeoutError
    def _slow_transport(method, url, body, headers, timeout) -> RawHTTPResponse:
        raise EIPTimeoutError("Simulated timeout", base_url=url)

    timeout_client = EIPClient(live_default_api, timeout=0.1, transport=_slow_transport)
    with pytest.raises(EIPTimeoutError):
        timeout_client.health()


def test_unchanged_sdk_discovers_and_consumes_newly_registered_policy() -> None:
    """Register ColdChainTestPolicy on a live API and consume it via unmodified EIPClient."""
    registry = build_default_registry()
    registry.register(ColdChainTestPolicy(max_age_hours=6.0))

    synthetic_telemetry = Evidence.model_validate(
        {
            "id": "cold-sensor-batch-99",
            "source": "synthetic_cold_chain_logger",
            "product_id": "LOGGER_BATCH_99",
            "observed_at": "2025-02-01T10:00:00Z",
            "available_at": "2025-02-01T10:05:00Z",
            "retrieved_at": "2025-02-01T10:06:00Z",
            "kind": "temperature_telemetry",
            "geometry": None,
            "coverage": None,
            "attributes": {"min_temp_c": 2.4, "max_temp_c": 11.8},
            "provenance": {
                "original_source": "ColdLogger-99",
                "publishing_organisation": "Synthetic QA Telemetry Fixture",
                "upstream_datasets": ["batch-99-log"],
            },
            "authentication": "unknown",
            "synthetic": True,
        }
    )

    ext_app = create_app(
        registry=registry,
        store=InMemoryEvidenceStore([synthetic_telemetry]),
    )

    with _run_uvicorn_app(ext_app) as base_url:
        client = EIPClient(base_url, timeout=5.0)

        # Dynamically discover new claim type & evidence kind without touching SDK code
        caps = client.capabilities()
        assert "cold_chain_within_limits" in caps.supported_claim_types
        assert "temperature_telemetry" in caps.supported_evidence_kinds
        assert "test-cold-chain" in caps.registered_policy_ids

        policy = client.get_policy("test-cold-chain")
        assert policy is not None
        assert policy.policy_version == "test-cold-chain-0.1"

        # Consume newly registered policy with unmodified ClaimInput.custom()
        claim = ClaimInput.custom(
            claim_id="shipment-99-compliance",
            claim_type="cold_chain_within_limits",
            claimed_at="2025-02-01T11:00:00Z",
            source_label="Synthetic cold-chain excursion claim",
            attributes={"allowed_min_c": 2.0, "allowed_max_c": 8.0},
            synthetic=True,
        )
        graph_res = client.assess_with_graph(claim)
        assert graph_res.assessment.is_conflict
        assert graph_res.assessment.policy_version == "test-cold-chain-0.1"
        assert "TEMPERATURE_EXCURSION_DETECTED" in graph_res.assessment.reasons
        assert len(graph_res.graph.evidence_nodes()) == 1

        # Decision-time mode works cleanly too (available_at=10:05 <= decision_time=11:00)
        dt_res = client.assess_decision_time(claim, decision_time="2025-02-01T11:00:00Z")
        assert dt_res.is_conflict


def test_cli_examples_and_enterprise_workflow_end_to_end(
    live_default_api: str,
    tmp_path: Path,
) -> None:
    """Run CLI, developer examples, and external enterprise triage demo against live API."""
    env = {**os.environ, "EIP_API_URL": live_default_api}

    # 1. CLI health + capabilities
    res = subprocess.run(
        [sys.executable, "-m", "eip_sdk", "--base-url", live_default_api, "capabilities"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    caps_json = json.loads(res.stdout)
    assert "road_passable" in caps_json["supported_claim_types"]

    # 2. CLI assess --graph --report-out
    claim_file = tmp_path / "claim.json"
    claim_file.write_text(
        json.dumps(
            {
                "claim_id": "cli-ballagh-1",
                "claim_type": "road_passable",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-8.1165, 53.4916], [-8.1075, 53.4916]],
                },
                "claimed_at": "2024-04-15T08:00:00Z",
                "source_label": "Synthetic CLI test claim",
                "synthetic": True,
            }
        ),
        encoding="utf-8",
    )
    report_out = tmp_path / "cli_report.json"
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "eip_sdk",
            "--base-url",
            live_default_api,
            "assess",
            "--claim-file",
            str(claim_file),
            "--graph",
            "--report-out",
            str(report_out),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    cli_report = json.loads(res.stdout)
    assert report_out.exists()
    assert cli_report["assessment"]["status"] == "potential_conflict"
    assert cli_report["graph"]["independent_group_count"] == 3

    # 3. CLI connection error exit code = 2
    closed_port = _find_free_port()
    err_res = subprocess.run(
        [sys.executable, "-m", "eip_sdk", "--base-url", f"http://127.0.0.1:{closed_port}", "health"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert err_res.returncode == 2
    assert json.loads(err_res.stderr)["error"] == "connection_error"

    # 4. Run all 5 developer examples against live server
    for script in [
        "examples/minimal_quickstart.py",
        "examples/environmental_assessment.py",
        "examples/galileo_nav_auth.py",
        "examples/decision_time_audit.py",
        "examples/provenance_graph_inspection.py",
    ]:
        ex_res = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
            env=env,
        )
        assert ex_res.stdout.strip(), f"{script} produced empty output"

    # 5. External Enterprise Claims Triage CLI workflow
    dossier_out = tmp_path / "claims_triage_dossier.json"
    wf_res = subprocess.run(
        [
            sys.executable,
            "examples/enterprise_insurance_workflow.py",
            "--base-url",
            live_default_api,
            "--case-id",
            "CASE-RF-2024-001",
            "--output",
            str(dossier_out),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    dossier = json.loads(wf_res.stdout)
    assert dossier_out.exists()
    assert dossier["hypothetical_workflow"] is True
    assert dossier["synthetic_claim"] is True
    assert dossier["eip_assessment"]["status"] == "potential_conflict"
    assert dossier["decision_support_guidance"]["automated_final_decision"] is False
    assert dossier["decision_support_guidance"]["human_signoff_required"] is True
