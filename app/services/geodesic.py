"""Geodesic measurement and the per-feature accuracy cross-check.

Why this exists
---------------
The main measurement path reprojects into a metric CRS and measures on a flat
plane. That is fast, but every projection distorts something. This module
measures the same geometry a second, independent way: directly on the WGS84
ellipsoid with pyproj's ``Geod``. The two numbers are compared and the gap is
stored on each feature, so accuracy is evidence in the data.

It also fixes one known weakness: equal-area (LAEA) projections preserve
AREA but not DISTANCE, so for LAEA datasets the reported length is replaced
by the geodesic length.

This module is pure: no HTTP, no settings, no database, no Prometheus.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import shapely
from pyproj import Geod
from shapely.geometry.base import BaseGeometry

from app.domain.entities.feature import Feature
from app.services.measurement import FeatureMeasurement, measure_feature
from app.services.target_crs import TargetCRS

_GEOD = Geod(ellps="WGS84")

_MULTI_TYPES = frozenset(
    {"MultiPolygon", "MultiLineString", "MultiPoint", "GeometryCollection"}
)


@dataclass(frozen=True)
class GeodesicResult:
    """Geodesic totals for one geometry (square metres / metres)."""

    area_m2: float
    length_m: float


@dataclass(frozen=True)
class CrossCheck:
    """Projected vs geodesic comparison for one feature.

    ``*_diff_pct`` = (projected - geodesic) / geodesic * 100.
    A value is None when the feature has no such quantity.
    """

    geodesic_area_m2: float | None
    geodesic_length_m: float | None
    area_diff_pct: float | None
    length_diff_pct: float | None


LengthMethod = Literal["projected", "geodesic"]


@dataclass(frozen=True)
class CheckedFeatureMeasurement:
    """A feature measurement plus its (optional) cross-check."""

    result: FeatureMeasurement
    cross_check: CrossCheck | None
    length_method: LengthMethod | None


def _xy(geometry: BaseGeometry) -> tuple[np.ndarray, np.ndarray]:
    coords = shapely.get_coordinates(geometry)
    return (
        np.ascontiguousarray(coords[:, 0]),
        np.ascontiguousarray(coords[:, 1]),
    )


def _ring_area(ring: BaseGeometry) -> float:
    lons, lats = _xy(ring)
    area, _ = _GEOD.polygon_area_perimeter(lons, lats)
    # The sign depends on ring direction; we only want the size.
    return abs(float(area))


def _line_length(line: BaseGeometry) -> float:
    lons, lats = _xy(line)
    return float(_GEOD.line_length(lons, lats))


def _accumulate(geometry: BaseGeometry | None, totals: list[float]) -> None:
    """Walk the geometry tree once, adding area to totals[0], length to totals[1]."""
    if geometry is None or geometry.is_empty:
        return
    gtype = geometry.geom_type
    if gtype == "Polygon":
        area = _ring_area(geometry.exterior)
        area -= sum(_ring_area(ring) for ring in geometry.interiors)
        totals[0] += area
    elif gtype == "LineString":
        totals[1] += _line_length(geometry)
    elif gtype in _MULTI_TYPES:
        for part in geometry.geoms:
            _accumulate(part, totals)
    # Point, LinearRing and anything else: contribute nothing.


def geodesic_measure(geometry_lonlat: BaseGeometry | None) -> GeodesicResult:
    """Measure a lon/lat geometry on the WGS84 ellipsoid.

    Polygons give area (holes subtracted), lines give length. Points and
    unsupported parts add nothing. Ring direction does not matter.
    """
    totals = [0.0, 0.0]
    _accumulate(geometry_lonlat, totals)
    return GeodesicResult(area_m2=max(totals[0], 0.0), length_m=totals[1])


def build_lonlat_transformer(target: TargetCRS) -> Any | None:
    """Transformer from the SOURCE CRS to lon/lat, or None if already geographic.

    Raises pyproj errors if the transformation cannot be built; the caller
    decides what that means.
    """
    from pyproj import Transformer

    if target.source_crs.is_geographic:
        return None
    return Transformer.from_crs(target.source_crs, "EPSG:4326", always_xy=True)


def _to_lonlat(geometry: BaseGeometry, transformer: Any) -> BaseGeometry:
    def _apply(coords: np.ndarray) -> np.ndarray:
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    out = shapely.transform(geometry, _apply)
    if not np.isfinite(shapely.get_coordinates(out)).all():
        raise ValueError("lon/lat conversion produced non-finite coordinates")
    return out


def _pct_diff(projected: float | None, geodesic: float | None) -> float | None:
    if projected is None or geodesic is None or geodesic <= 0:
        return None
    return (projected - geodesic) / geodesic * 100.0


def measure_feature_checked(
    feature: Feature,
    target: TargetCRS,
    transformer: Any | None,
    lonlat_transformer: Any | None,
) -> CheckedFeatureMeasurement:
    """Measure one feature, cross-check it, and never raise.

    1. Normal projected measurement (``measure_feature``).
    2. If it was measured, compute geodesic values on the lon/lat geometry.
    3. Store the comparison. For LAEA datasets, replace the reported length
       with the geodesic length (LAEA does not preserve distance).
    4. If the cross-check itself fails, keep the normal measurement.
    """
    meters_per_unit = target.meters_per_unit or 1.0
    result = measure_feature(feature, transformer, meters_per_unit)

    measurement = result.measurement
    if result.status != "measured" or measurement is None:
        return CheckedFeatureMeasurement(result, None, None)

    has_area = measurement.area_m2 is not None
    has_length = measurement.length_m is not None
    length_method: LengthMethod | None = "projected" if has_length else None

    if not has_area and not has_length:
        return CheckedFeatureMeasurement(result, None, None)

    try:
        geometry = feature.geometry
        if lonlat_transformer is not None:
            geometry = _to_lonlat(geometry, lonlat_transformer)
        geo = geodesic_measure(geometry)
    except Exception:  # noqa: BLE001 - a failed cross-check must not fail the feature
        return CheckedFeatureMeasurement(result, None, length_method)

    cross_check = CrossCheck(
        geodesic_area_m2=geo.area_m2 if has_area else None,
        geodesic_length_m=geo.length_m if has_length else None,
        area_diff_pct=_pct_diff(measurement.area_m2, geo.area_m2) if has_area else None,
        length_diff_pct=(
            _pct_diff(measurement.length_m, geo.length_m) if has_length else None
        ),
    )

    if target.strategy == "laea" and has_length:
        result = replace(result, measurement=replace(measurement, length_m=geo.length_m))
        length_method = "geodesic"

    return CheckedFeatureMeasurement(result, cross_check, length_method)