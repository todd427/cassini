"""Evidence storage interface and file-backed JSON normalising store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import TypeAdapter

from core.models import Evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_REL_PATH = "sample_data/evidence.json"

_EVIDENCE_LIST_ADAPTER = TypeAdapter(list[Evidence])


@runtime_checkable
class EvidenceStore(Protocol):
    """Interface for loading validated, normalised Evidence records."""

    def load_all(self) -> list[Evidence]:
        ...


def resolve_evidence_path(explicit_path: str | Path | None = None) -> Path:
    if explicit_path is not None:
        raw = Path(explicit_path)
    else:
        env_val = os.environ.get("EIP_EVIDENCE_PATH")
        raw = Path(env_val) if env_val else Path(DEFAULT_EVIDENCE_REL_PATH)
    if raw.is_absolute():
        return raw
    return (REPO_ROOT / raw).resolve()


def load_evidence_file(path: str | Path | None = None) -> list[Evidence]:
    resolved = resolve_evidence_path(path)
    if not resolved.exists():
        return []
    raw_text = resolved.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    if not isinstance(data, list):
        raise ValueError(f"Evidence file {resolved} must contain a JSON array.")
    items = _EVIDENCE_LIST_ADAPTER.validate_python(data)
    seen_ids: set[str] = set()
    for item in items:
        if item.id in seen_ids:
            raise ValueError(f"Duplicate evidence id in {resolved}: {item.id}")
        seen_ids.add(item.id)
    return items


class FileEvidenceStore:
    """File-backed EvidenceStore reading JSON arrays of normalised Evidence."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = path

    def load_all(self) -> list[Evidence]:
        return load_evidence_file(self._path)


class InMemoryEvidenceStore:
    """In-memory EvidenceStore for testing and embedded policy pipelines."""

    def __init__(self, items: list[Evidence]) -> None:
        seen: set[str] = set()
        for item in items:
            if item.id in seen:
                raise ValueError(f"Duplicate evidence id: {item.id}")
            seen.add(item.id)
        self._items = list(items)

    def load_all(self) -> list[Evidence]:
        return list(self._items)
