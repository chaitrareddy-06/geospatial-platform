"""Measurement: reproject a geometry, then compute area and length in metres.

Pure functions, no framework imports. Handles Point, MultiPoint, LineString,
MultiLineString, Polygon, MultiPolygon and (recursively) GeometryCollection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import shapely
from pyproj import Transformer
from pyproj.exceptions import ProjError
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import CRSResolutionError, GeometryProcessingError
from app.domain.entities.feature import Feature
from app.domain.enums.geometry_kind import GeometryKind
from app.services.target_crs import REASON_REPROJECTION_FAILED, TargetCRS

logger = logging.getLogger(__name__)

REASON_NO_GEOMETRY = "empty_geometry"
REASON_UNSUPPORTED_FOR_MEASUREMENT = "unsupported_for_measurement"
REASON_BAD_REPROJECTION = "reprojection_produced_invalid_coordinates"
REASON_UNEXPECTED = "unexpected_error"

STATUS_MEASURED = "measured"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"

_MULTI_KINDS = {
    GeometryKind.MULTI_POINT,
    GeometryKind.MULTI_LINE_STRING,
    GeometryKind.MULTI_POLYGON,
    GeometryKind.GEOMETRY_COLLECTION,
}


@dataclass(frozen=True)
class Measurement:
    kind: GeometryKind
    area_m2: float | None = None
    length_m: float | None = None
    part_count: int | None = None  # for Multi* and collections
    unsupported_parts: tuple[str, ...] = ()  # geometry types we could not measure


@dataclass(frozen=True)
class FeatureMeasurement:
    """Outcome for one feature: measured, skipped (already flagged) or failed."""

    index: int
    kind: GeometryKind
    status: str  # STATUS_MEASURED / STATUS_SKIPPED / STATUS_FAILED
    measurement: Measurement | None = None
    reason: str | None = None
    repaired: bool = False


@dataclass
class _Totals:
    area: float = 0.0
    length: float = 0.0
    has_area: bool = False
    has_length: bool = False
    unsupported: list[str] = field(default_factory=list)


def build_transformer(target: TargetCRS) -> Transformer | None:
    """Transformer from the source CRS to the measurement CRS, or None if the
    source CRS is already the measurement CRS."""
    if not target.needs_reprojection:
        return None
    try:
        return Transformer.from_crs(
            target.source_crs, target.measurement_crs, always_xy=True
        )
    except ProjError as exc:
        raise CRSResolutionError(
            "Could not build a transformation to the measurement CRS.",
            details={"reason": REASON_REPROJECTION_FAILED},
        ) from exc


def _reproject(geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    def convert(coords: np.ndarray) -> np.ndarray:
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    try:
        projected = shapely.transform(geometry, convert)
    except ProjError as exc:
        raise GeometryProcessingError(
            "Reprojecting the geometry failed.",
            details={"reason": REASON_BAD_REPROJECTION},
        ) from exc

    # PROJ marks points it cannot transform as inf instead of raising.
    if not np.isfinite(shapely.get_coordinates(projected)).all():
        raise GeometryProcessingError(
            "Reprojecting the geometry produced invalid coordinates.",
            details={"reason": REASON_BAD_REPROJECTION},
        )
    return projected


def _walk(geometry: BaseGeometry, totals: _Totals) -> None:
    """Visit every part of a geometry, adding up area and length."""
    if geometry.is_empty:
        return
    geom_type = geometry.geom_type
    if geom_type == "Polygon":
        totals.area += geometry.area
        totals.has_area = True
    elif geom_type == "LineString":
        totals.length += geometry.length
        totals.has_length = True
    elif geom_type in ("Point", "MultiPoint"):
        return  # accepted, nothing to measure
    elif geom_type in ("MultiPolygon", "MultiLineString", "GeometryCollection"):
        for part in geometry.geoms:  # type: ignore[attr-defined]
            _walk(part, totals)
    else:
        totals.unsupported.append(geom_type)  # e.g. LinearRing


def measure_geometry(
    geometry: BaseGeometry | None,
    transformer: Transformer | None,
    meters_per_unit: float = 1.0,
) -> Measurement:
    """Measure one geometry.

    transformer: from build_transformer (None = already in the measurement CRS).
    meters_per_unit: unit factor of the measurement CRS (1.0 unless native feet).
    Raises GeometryProcessingError for empty, unsupported or untransformable input.
    """
    if geometry is None or geometry.is_empty:
        raise GeometryProcessingError(
            "There is no geometry to measure.",
            details={"reason": REASON_NO_GEOMETRY},
        )

    kind = GeometryKind.from_geom_type(geometry.geom_type)
    if kind in {GeometryKind.UNKNOWN, GeometryKind.NULL}:
        raise GeometryProcessingError(
            "This geometry type cannot be measured.",
            details={
                "reason": REASON_UNSUPPORTED_FOR_MEASUREMENT,
                "geometry_type": geometry.geom_type,
            },
        )

    part_count = len(geometry.geoms) if kind in _MULTI_KINDS else None  # type: ignore[attr-defined]

    if kind in {GeometryKind.POINT, GeometryKind.MULTI_POINT}:
        return Measurement(kind=kind, part_count=part_count)

    projected = _reproject(geometry, transformer) if transformer else geometry

    totals = _Totals()
    _walk(projected, totals)
    return Measurement(
        kind=kind,
        area_m2=totals.area * meters_per_unit**2 if totals.has_area else None,
        length_m=totals.length * meters_per_unit if totals.has_length else None,
        part_count=part_count,
        unsupported_parts=tuple(totals.unsupported),
    )


def measure_feature(
    feature: Feature,
    transformer: Transformer | None,
    meters_per_unit: float = 1.0,
) -> FeatureMeasurement:
    """Measure one feature. Never raises: any problem becomes a status record."""
    if feature.is_skipped:
        return FeatureMeasurement(
            index=feature.index,
            kind=feature.kind,
            status=STATUS_SKIPPED,
            reason=feature.skip_reason,
            repaired=feature.repaired,
        )

    try:
        measurement = measure_geometry(feature.geometry, transformer, meters_per_unit)
    except GeometryProcessingError as exc:
        reason = (exc.details or {}).get("reason", REASON_UNEXPECTED)
        logger.warning(
            "feature_measurement_failed",
            extra={"feature_index": feature.index, "failure_reason": reason},
        )
        return FeatureMeasurement(
            index=feature.index,
            kind=feature.kind,
            status=STATUS_FAILED,
            reason=reason,
            repaired=feature.repaired,
        )
    except Exception:  # noqa: BLE001 - one bad feature must never kill the file
        logger.warning(
            "feature_measurement_unexpected_error",
            extra={"feature_index": feature.index},
            exc_info=True,
        )
        return FeatureMeasurement(
            index=feature.index,
            kind=feature.kind,
            status=STATUS_FAILED,
            reason=REASON_UNEXPECTED,
            repaired=feature.repaired,
        )

    return FeatureMeasurement(
        index=feature.index,
        kind=measurement.kind,
        status=STATUS_MEASURED,
        measurement=measurement,
        repaired=feature.repaired,
    )