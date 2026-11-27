"""Explicit EvidenceConnector interface for EIP source connectors.

Prepares a uniform contract for future Copernicus STAC, Galileo OSNMA,
terrestrial sensor, and structured human-report connectors without requiring
changes to the generic evidence engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.models import Evidence


@dataclass(frozen=True)
class ConnectorMetadata:
    """Declarative metadata describing an evidence source connector."""

    connector_id: str
    source_name: str
    publishing_organisation: str | None
    produced_evidence_kinds: list[str]
    supports_authentication: bool = False
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class EvidenceConnector(Protocol):
    """Protocol implemented by all evidence ingestion/normalisation connectors."""

    @property
    def metadata(self) -> ConnectorMetadata:
        ...

    def load_evidence(self) -> list[Evidence]:
        """Normalise raw provider artefacts into validated EIP Evidence objects."""
        ...
