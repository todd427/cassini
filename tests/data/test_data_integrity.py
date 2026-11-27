"""Data provenance, checksum, schema, and fixture integrity tests for EIP."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shapely.geometry import shape

from core.assessment import assess_claim
from core.models import ClaimRequest, Evidence
from core.store import load_evidence_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE_PATH = REPO_ROOT / "sample_data" / "evidence.json"
FIXTURES_DIR = REPO_ROOT / "sample_data" / "fixtures"
EXAMPLES_PATH = REPO_ROOT / "sample_data" / "example_claims.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_real_copernicus_evidence_provenance_and_checksum() -> None:
    items = load_evidence_file(EVIDENCE_PATH)
    assert len(items) >= 1

    real_items = [ev for ev in items if not ev.synthetic]
    assert len(real_items) >= 1, "Expected at least one genuine non-synthetic Copernicus dataset."

    for ev in real_items:
        assert ev.source == "copernicus_ems_rapid_mapping"
        assert ev.product_id is not None and "EMSR" in ev.product_id
        assert ev.source_url is not None and ev.source_url.startswith("https://")
        assert ev.observed_at is not None
        assert ev.retrieved_at is not None
        assert ev.licence is not None and "Copernicus" in ev.licence
        assert ev.authentication == "unknown"
        assert ev.raw_path is not None
        assert ev.sha256 is not None

        raw_file = (REPO_ROOT / ev.raw_path).resolve()
        assert raw_file.exists(), f"Raw artifact missing at {raw_file}"
        assert _sha256(raw_file) == ev.sha256, "SHA-256 mismatch against raw artifact!"

        flood_geom = shape(ev.geometry.model_dump())
        assert flood_geom.is_valid and not flood_geom.is_empty
        minx, miny, maxx, maxy = flood_geom.bounds
        # Verify WGS84 lon/lat order for Ireland (approx lon -11..-5, lat 51..56)
        assert -11.0 <= minx < maxx <= -5.0
        assert 51.0 <= miny < maxy <= 56.0

        assert ev.coverage is not None
        cov_geom = shape(ev.coverage.model_dump())
        assert cov_geom.is_valid and not cov_geom.is_empty
        assert cov_geom.intersects(flood_geom)


def test_all_synthetic_fixtures_valid_and_deterministic() -> None:
    expected_files = {
        "fresh_intersection.json",
        "covered_non_intersection.json",
        "stale_observation.json",
        "unknown_observation_time.json",
        "outside_coverage.json",
        "unknown_coverage.json",
        "missing_evidence.json",
    }
    actual_files = {p.name for p in FIXTURES_DIR.glob("*.json")}
    assert expected_files.issubset(actual_files)

    for fname in sorted(expected_files):
        bundle = json.loads((FIXTURES_DIR / fname).read_text(encoding="utf-8"))
        evidence = [Evidence.model_validate(item) for item in bundle["evidence"]]
        for ev in evidence:
            assert ev.synthetic is True, f"Fixture {fname} must be explicitly marked synthetic."
        claim = ClaimRequest.model_validate(bundle["claim"])
        assert claim.synthetic is True

        res1 = assess_claim(claim, evidence)
        res2 = assess_claim(claim, evidence)
        assert res1.model_dump(mode="json") == res2.model_dump(mode="json")
        assert res1.status == bundle["expected_status"], f"Mismatch in {fname}"
        assert res1.reasons == bundle["expected_reasons"], f"Reason mismatch in {fname}"
        assert res1.synthetic is True


def test_emsr718_example_claims_against_real_evidence() -> None:
    evidence = load_evidence_file(EVIDENCE_PATH)
    examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    assert len(examples) >= 4

    for ex in examples:
        claim = ClaimRequest.model_validate(ex["claim"])
        assert claim.synthetic is True
        result = assess_claim(claim, evidence)
        assert result.status == ex["expected_status"], f"Failed example: {ex['label']}"
        assert result.synthetic is True
