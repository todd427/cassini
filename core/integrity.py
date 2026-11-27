"""Reusable local integrity checksum and authentication helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.models import Evidence

IntegrityStatus = Literal[
    "verified_local_bytes",
    "checksum_mismatch",
    "missing_raw_file",
    "unverifiable_no_metadata",
]


@dataclass(frozen=True)
class IntegrityCheckResult:
    """Result of checking an evidence record's raw artifact SHA-256."""

    evidence_id: str
    status: IntegrityStatus
    expected_sha256: str | None
    actual_sha256: str | None
    note: str


def compute_file_sha256(path: Path) -> str:
    """Compute lowercase SHA-256 hex digest of a local file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_evidence_checksum(
    evidence: Evidence,
    base_dir: Path,
) -> IntegrityCheckResult:
    """Verify local raw artifact bytes against declared SHA-256.

    Note: A matching SHA-256 confirms local byte integrity only; it does not
    establish source authenticity or provider cryptographic signature.
    """
    if not evidence.sha256 or not evidence.raw_path:
        return IntegrityCheckResult(
            evidence_id=evidence.id,
            status="unverifiable_no_metadata",
            expected_sha256=evidence.sha256,
            actual_sha256=None,
            note="No raw_path or sha256 recorded for local byte verification.",
        )
    target = (base_dir / evidence.raw_path).resolve()
    if not target.exists() or not target.is_file():
        return IntegrityCheckResult(
            evidence_id=evidence.id,
            status="missing_raw_file",
            expected_sha256=evidence.sha256,
            actual_sha256=None,
            note=f"Declared raw artifact not found at {evidence.raw_path}.",
        )
    actual = compute_file_sha256(target)
    if actual == evidence.sha256:
        return IntegrityCheckResult(
            evidence_id=evidence.id,
            status="verified_local_bytes",
            expected_sha256=evidence.sha256,
            actual_sha256=actual,
            note="SHA-256 matches local raw file bytes (local byte integrity only, not source authenticity).",
        )
    return IntegrityCheckResult(
        evidence_id=evidence.id,
        status="checksum_mismatch",
        expected_sha256=evidence.sha256,
        actual_sha256=actual,
        note="Local raw artifact SHA-256 does not match declared sha256.",
    )


def is_authentication_failed(evidence: Evidence) -> bool:
    return evidence.authentication == "failed"


def is_authentication_unverified(evidence: Evidence) -> bool:
    return evidence.authentication == "unknown"
