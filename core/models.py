"""Pydantic models and strict validators for EIP shared contract v0.1."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)
from shapely.geometry import LineString, MultiPolygon, Polygon, shape

CONTRACT_VERSION = "0.1"
POLICY_VERSION = "flood-road-0.1"
MAX_AGE_HOURS = 24.0

AuthenticationStatus = Literal["unknown", "verified", "failed"]
AssessmentStatus = Literal[
    "potential_conflict",
    "no_mapped_overlap",
    "insufficient_evidence",
]
EvidenceKind = Literal["flood_extent"]
ClaimType = Literal["road_passable"]
ReasonCode = Literal[
    "FLOOD_EXTENT_INTERSECTS",
    "NO_MAPPED_OVERLAP",
    "OBSERVATION_STALE",
    "OBSERVATION_TIME_UNKNOWN",
    "COVERAGE_UNKNOWN",
    "OUTSIDE_COVERAGE",
    "NO_EVIDENCE",
    "AUTHENTICATION_FAILED",
]


def _validate_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "Timestamp must be timezone-aware ISO 8601 (UTC 'Z' or explicit offset)."
        )
    return value.astimezone(timezone.utc)


def _serialize_utc(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.isoformat().replace("+00:00", "Z")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


AwareUtcDatetime = Annotated[
    datetime,
    AfterValidator(_validate_utc_aware),
    PlainSerializer(_serialize_utc, return_type=str),
]


def _validate_position(pos: Any) -> None:
    if not isinstance(pos, (list, tuple)) or len(pos) < 2 or len(pos) > 3:
        raise ValueError("Each GeoJSON position must be a [lon, lat] coordinate array.")
    lon, lat = pos[0], pos[1]
    if isinstance(lon, bool) or isinstance(lat, bool):
        raise ValueError("Coordinates must be numeric, not boolean.")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise ValueError("Coordinates must be numeric.")
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValueError("Coordinates must be finite numbers.")
    if not (-180.0 <= float(lon) <= 180.0):
        raise ValueError(f"Longitude {lon} out of WGS84 range [-180, 180].")
    if not (-90.0 <= float(lat) <= 90.0):
        raise ValueError(f"Latitude {lat} out of WGS84 range [-90, 90].")
    if len(pos) == 3:
        alt = pos[2]
        if isinstance(alt, bool) or not isinstance(alt, (int, float)) or not math.isfinite(alt):
            raise ValueError("Altitude coordinate must be a finite number.")


def _validate_linear_ring(ring: Any) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        raise ValueError("Polygon linear ring must have at least 4 positions.")
    for pos in ring:
        _validate_position(pos)
    if ring[0][:2] != ring[-1][:2]:
        raise ValueError("Polygon linear ring must be closed (first position equals last).")


def _validate_polygon_coords(rings: Any) -> None:
    if not isinstance(rings, list) or len(rings) == 0:
        raise ValueError("Polygon must have at least one linear ring.")
    for ring in rings:
        _validate_linear_ring(ring)


class LineStringGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["LineString"]
    coordinates: list[list[float]]

    @model_validator(mode="after")
    def validate_geometry(self) -> LineStringGeometry:
        if len(self.coordinates) < 2:
            raise ValueError("LineString must contain at least 2 coordinate positions.")
        for pos in self.coordinates:
            _validate_position(pos)
        try:
            geom = shape({"type": self.type, "coordinates": self.coordinates})
        except Exception as exc:
            raise ValueError(f"Malformed LineString geometry: {exc}") from exc
        if not isinstance(geom, LineString) or geom.is_empty or not geom.is_valid:
            raise ValueError("LineString geometry is invalid or empty.")
        if geom.length == 0.0:
            raise ValueError("LineString geometry must have non-zero length.")
        return self


class PolygonOrMultiPolygonGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon", "MultiPolygon"]
    coordinates: Any

    @model_validator(mode="after")
    def validate_geometry(self) -> PolygonOrMultiPolygonGeometry:
        if self.type == "Polygon":
            _validate_polygon_coords(self.coordinates)
        else:
            if not isinstance(self.coordinates, list) or len(self.coordinates) == 0:
                raise ValueError("MultiPolygon must contain at least one Polygon.")
            for poly in self.coordinates:
                _validate_polygon_coords(poly)
        try:
            geom = shape({"type": self.type, "coordinates": self.coordinates})
        except Exception as exc:
            raise ValueError(f"Malformed {self.type} geometry: {exc}") from exc
        if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty or not geom.is_valid:
            raise ValueError(f"{self.type} geometry is invalid or empty.")
        if geom.area <= 0.0:
            raise ValueError(f"{self.type} geometry must have positive area.")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    product_id: str | None = None
    source_url: str | None = None
    observed_at: AwareUtcDatetime | None = None
    retrieved_at: AwareUtcDatetime | None = None
    kind: EvidenceKind
    geometry: PolygonOrMultiPolygonGeometry
    coverage: PolygonOrMultiPolygonGeometry | None = None
    authentication: AuthenticationStatus = "unknown"
    sha256: str | None = None
    raw_path: str | None = None
    licence: str | None = None
    limitations: list[str] = Field(default_factory=list)
    synthetic: bool

    @field_validator("raw_path")
    @classmethod
    def validate_raw_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme:
            raise ValueError("raw_path must be a local relative path, not a URL.")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("raw_path must be a safe local relative path without '..'.")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if len(cleaned) != 64 or any(ch not in "0123456789abcdef" for ch in cleaned):
            raise ValueError("sha256 must be a 64-character lowercase hex digest.")
        return cleaned


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    claim_type: ClaimType
    geometry: LineStringGeometry
    claimed_at: AwareUtcDatetime
    source_label: str = Field(min_length=1)
    synthetic: bool


class EvidenceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    status: AssessmentStatus
    age_hours: float | None
    reasons: list[ReasonCode]


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: AssessmentStatus
    policy_version: str = POLICY_VERSION
    reasons: list[ReasonCode]
    evidence_ids: list[str]
    findings: list[EvidenceFinding]
    limitations: list[str]
    synthetic: bool


class EvidenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Evidence]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    contract_version: str = CONTRACT_VERSION
