"""Domain-independent WGS84 GeoJSON models and Shapely spatial primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry


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
        if (
            isinstance(alt, bool)
            or not isinstance(alt, (int, float))
            or not math.isfinite(alt)
        ):
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


class PointGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Point"]
    coordinates: list[float]

    @model_validator(mode="after")
    def validate_geometry(self) -> PointGeometry:
        _validate_position(self.coordinates)
        try:
            geom = shape({"type": self.type, "coordinates": self.coordinates})
        except Exception as exc:
            raise ValueError(f"Malformed Point geometry: {exc}") from exc
        if not isinstance(geom, Point) or geom.is_empty or not geom.is_valid:
            raise ValueError("Point geometry is invalid or empty.")
        return self


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
        if (
            not isinstance(geom, (Polygon, MultiPolygon))
            or geom.is_empty
            or not geom.is_valid
        ):
            raise ValueError(f"{self.type} geometry is invalid or empty.")
        if geom.area <= 0.0:
            raise ValueError(f"{self.type} geometry must have positive area.")
        return self


GeoJSONGeometry = Annotated[
    PointGeometry | LineStringGeometry | PolygonOrMultiPolygonGeometry,
    Field(discriminator="type"),
]


@dataclass(frozen=True)
class SpatialRelation:
    """Generic spatial relationship between a claim geometry, observation, and coverage."""

    intersects_observation: bool
    has_coverage: bool
    intersects_coverage: bool | None
    fully_within_coverage: bool | None


def to_shapely(geom: BaseModel) -> BaseGeometry:
    """Convert a validated Pydantic GeoJSON model into a Shapely geometry."""
    return shape(geom.model_dump())


def evaluate_spatial_relation(
    claim_geom: BaseGeometry,
    observation_geom: BaseGeometry,
    coverage_geom: BaseGeometry | None,
) -> SpatialRelation:
    """Compute deterministic spatial predicates without domain interpretation."""
    has_cov = coverage_geom is not None
    intersects_cov = coverage_geom.intersects(claim_geom) if coverage_geom is not None else None
    fully_within = coverage_geom.covers(claim_geom) if coverage_geom is not None else None
    intersects_obs = bool(observation_geom.intersects(claim_geom))
    return SpatialRelation(
        intersects_observation=intersects_obs,
        has_coverage=has_cov,
        intersects_coverage=bool(intersects_cov) if intersects_cov is not None else None,
        fully_within_coverage=bool(fully_within) if fully_within is not None else None,
    )
