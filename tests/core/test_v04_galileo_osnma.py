"""EIP v0.4 tests: genuine local Galileo OSNMA cryptographic verification,
tamper detection, EvidenceConnector protocol, GalileoOsnmaPolicy outcomes,
scope boundary (positioning accuracy -> evidence_unsuitable), and API discovery.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from connectors.base import EvidenceConnector
from connectors.build_evidence_bundle import (
    build_genuine_evidence_bundle,
    build_v04_galileo_scenarios,
)
from connectors.galileo_osnma import (
    DEFAULT_MERKLE_PATH,
    DEFAULT_PUBKEY_PATH,
    DEFAULT_SBF_PATH,
    GalileoOsnmaConnector,
    _crc16_xmodem,
    verify_merkle_tree_xml,
    verify_sbf_bytes,
)
from core.engine import AssessmentEngine
from core.models import ClaimRequest, Evidence
from policies import build_default_registry

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = REPO_ROOT / "sample_data" / "scenarios"


def test_genuine_sbf_four_layer_local_cryptographic_verification() -> None:
    """Verify all 4 cryptographic layers locally over preserved Septentrio SBF + GSC XMLs."""
    mt = verify_merkle_tree_xml(DEFAULT_MERKLE_PATH)
    assert mt["verified"] is True
    assert mt["pkid"] == 1
    assert mt["merkle_root_hex"] == "0e63f552c8021709043c239032effe941bf22c8389032f5f2701e0fbc80148b8"

    report = verify_sbf_bytes(
        sbf_bytes=DEFAULT_SBF_PATH.read_bytes(),
        merkle_xml_path=DEFAULT_MERKLE_PATH,
        pubkey_xml_path=DEFAULT_PUBKEY_PATH,
    )
    assert report.outcome == "authenticated"
    assert report.authentication == "verified"
    assert report.merkle_proof_verified is True
    assert report.ecdsa_kroot_verified is True
    assert report.tesla_verified_subframes == 73
    assert report.tag0_checked_count == 188
    assert report.tag0_verified_count == 188
    assert report.tag0_failed_count == 0
    assert report.authenticated_svids == [7, 18, 21, 27]
    assert report.receiver_model == "Septentrio mosaic-X5"
    assert report.nma_status == "test"


def test_tampering_one_bit_in_real_galileo_nav_message_fails_osnma_cryptographically() -> None:
    """Flip 1 bit inside a genuine Galileo I/NAV ephemeris word (updating SBF block CRC)
    and prove our local OSNMA verifier detects HMAC-SHA-256 Tag0 tampering."""
    raw = bytearray(DEFAULT_SBF_PATH.read_bytes())

    # Locate a GALRawINAV (4023) block from mid-recording carrying WT=1 (ephemeris) and flip 1 bit
    pos = 0
    tampered = False
    seen = 0
    while pos + 8 <= len(raw):
        if raw[pos : pos + 2] != b"$@":
            pos += 1
            continue
        crc_obs, bid_rev, length = struct.unpack_from("<HHH", raw, pos + 2)
        if length < 8 or length % 4 != 0 or pos + length > len(raw):
            pos += 1
            continue
        if (bid_rev & 0x1FFF) == 4023 and length >= 52:
            seen += 1
            if seen > 400:
                words = struct.unpack_from("<8I", raw, pos + 20)
                wtype = (words[0] >> 24) & 0x3F
                if wtype == 1:
                    # Flip 1 bit inside WT1 ephemeris payload (bit 10 of word 1) and recompute SBF CRC
                    new_w1 = words[1] ^ 0x00000400
                    struct.pack_into("<I", raw, pos + 24, new_w1)
                    new_crc = _crc16_xmodem(bytes(raw[pos + 4 : pos + length]))
                    struct.pack_into("<H", raw, pos + 2, new_crc)
                    tampered = True
                    break
        pos += length

    assert tampered is True
    report = verify_sbf_bytes(
        sbf_bytes=bytes(raw),
        merkle_xml_path=DEFAULT_MERKLE_PATH,
        pubkey_xml_path=DEFAULT_PUBKEY_PATH,
    )
    assert report.outcome == "failed"
    assert report.authentication == "failed"
    assert report.tag0_failed_count >= 1
    assert "MAC_TAG_VERIFICATION_FAILED" in report.failure_reasons


def test_truncated_single_subframe_yields_pending_before_kroot_assembly() -> None:
    report = verify_sbf_bytes(
        sbf_bytes=DEFAULT_SBF_PATH.read_bytes(),
        merkle_xml_path=DEFAULT_MERKLE_PATH,
        pubkey_xml_path=DEFAULT_PUBKEY_PATH,
        max_subframes=1,
    )
    assert report.outcome == "pending"
    assert report.authentication == "unknown"


def test_galileo_connector_protocol_provenance_and_sha256() -> None:
    conn = GalileoOsnmaConnector()
    assert isinstance(conn, EvidenceConnector)
    items = conn.load_evidence()
    assert len(items) == 1
    ev = items[0]
    assert ev.synthetic is False
    assert ev.kind == "gnss_osnma_auth"
    assert ev.geometry is None
    assert ev.authentication == "verified"
    assert ev.available_at is None
    assert ev.attributes["verification_method"] == "local_osnma_cryptographic"
    assert ev.attributes["locally_verified"] is True
    assert ev.attributes["tag0_verified_count"] == 188
    expected_sha = hashlib.sha256(DEFAULT_SBF_PATH.read_bytes()).hexdigest()
    assert ev.sha256 == expected_sha


def test_all_v04_galileo_scenarios_and_api_discovery() -> None:
    genuine_bundle = build_genuine_evidence_bundle()
    scenarios = build_v04_galileo_scenarios(genuine_bundle)
    engine = AssessmentEngine(build_default_registry())

    for name, bundle in scenarios.items():
        assert (SCENARIOS_DIR / f"{name}.json").exists()
        ev_objs = [Evidence.model_validate(e) for e in bundle["evidence"]]
        claim = ClaimRequest.model_validate(bundle["claim"])
        res1 = engine.assess(claim, ev_objs)
        res2 = engine.assess(claim, ev_objs)
        assert res1.model_dump(mode="json") == res2.model_dump(mode="json")
        assert res1.status == bundle["expected_status"], f"Status mismatch in {name}"
        assert res1.reasons == bundle["expected_reasons"], f"Reason mismatch in {name}"
        assert res1.policy_version == "galileo-osnma-0.1"

    # Verify live API discovery & dispatch against sample_data/evidence.json
    client = TestClient(create_app())
    caps = client.get("/v1/capabilities").json()
    assert "gnss_nav_message_authenticated" in caps["supported_claim_types"]
    assert "gnss_position_accurate" in caps["supported_claim_types"]
    assert "gnss_osnma_auth" in caps["supported_evidence_kinds"]
    assert "galileo-osnma" in caps["registered_policy_ids"]

    # Live POST /v1/assess for genuine authenticated Galileo nav message
    auth_res = client.post(
        "/v1/assess",
        json=scenarios["galileo_genuine_authenticated"]["claim"],
    )
    assert auth_res.status_code == 200
    assert auth_res.json()["status"] == "authenticated"
    assert auth_res.json()["policy_version"] == "galileo-osnma-0.1"

    # Live POST /v1/assess for positioning-accuracy claim -> evidence_unsuitable!
    pos_res = client.post(
        "/v1/assess",
        json=scenarios["galileo_positioning_unsuitable"]["claim"],
    )
    assert pos_res.status_code == 200
    assert pos_res.json()["status"] == "evidence_unsuitable"
    assert pos_res.json()["reasons"] == ["NAV_AUTH_INSUFFICIENT_FOR_POSITIONING"]

    # Invalid SVID attribute -> HTTP 422
    bad_svid = client.post(
        "/v1/assess",
        json={
            **scenarios["galileo_genuine_authenticated"]["claim"],
            "attributes": {"svid": 99},
        },
    )
    assert bad_svid.status_code == 422
    assert bad_svid.json()["detail"]["error"] == "claim_validation_error"
