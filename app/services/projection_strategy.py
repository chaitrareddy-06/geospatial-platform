"""Projection strategy: UTM for local data, equal-area for wide or polar data.

Pure functions, no framework imports. Input geometries must be lon/lat degrees.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import CRSResolutionError
from app.services.utm_selection import (
    UTM_MAX_LATITUDE,
    UTM_MIN_LATITUDE,
    utm_zone_for,
)

logger = logging.getLogger(__name__)

STRATEGY_UTM = "utm"
STRATEGY_LAEA = "laea"

REASON_SINGLE_ZONE = "within_single_utm_zone"
REASON_POLAR = "polar_latitudes"
REASON_TOO_WIDE = "extent_exceeds_utm_zone"

REASON_NO_USABLE = "no_usable_geometries"
REASON_NOT_LONLAT = "coordinates_not_lonlat"

# How far (degrees of longitude) any part of the data may be from the UTM
# zone's centre line. Roughly 4 deg gives ~0.4 percent area scale error at the
# equator. This is a tunable choice; Step 9's geodesic check measures it.
MAX_UTM_OFFSET_DEG = 4.0


@dataclass(frozen=True)
class ProjectionChoice:
    crs: CRS
    label: str  # "EPSG:32644" or "LAEA(lat_0=..,lon_0=..)"
    strategy: str  # STRATEGY_UTM or STRATEGY_LAEA
    reason: str
    preserves: str  # "conformal" (UTM) or "area" (LAEA)
    center_lon: float
    center_lat: float
    lon_span_deg: float


def _wrap_lon(lon: float) -> float:
    """Wrap any longitude into [-180, 180)."""
    return ((lon + 180.0) % 360.0) - 180.0


def circular_lon_extent(lons: Sequence[float]) -> tuple[float, float]:
    """Return (span_degrees, centre_longitude) of the smallest arc holding all lons.

    The smallest arc is found by locating the largest empty gap on the circle,
    so data on both sides of the antimeridian is treated as one small cluster.
    """
    values = sorted({_wrap_lon(float(lon)) for lon in lons})
    if len(values) == 1:
        return 0.0, values[0]

    n = len(values)
    best_gap = values[0] + 360.0 - values[-1]  # the gap that wraps around
    best_index = n - 1
    for i in range(n - 1):
        gap = values[i + 1] - values[i]
        if gap > best_gap:
            best_gap = gap
            best_index = i

    start = values[(best_index + 1) % n]  # first longitude after the biggest gap
    span = 360.0 - best_gap
    return span, _wrap_lon(start + span / 2.0)


def _laea_for(center_lon: float, center_lat: float) -> tuple[CRS, str]:
    lon = round(center_lon, 4)
    lat = round(center_lat, 4)
    crs = CRS.from_proj4(
        f"+proj=laea +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 "
        "+datum=WGS84 +units=m +no_defs"
    )
    return crs, f"LAEA(lat_0={lat:.2f},lon_0={lon:.2f})"


def choose_projection(geometries: Iterable[BaseGeometry | None]) -> ProjectionChoice:
    """Choose a projected CRS to measure lon/lat geometries in."""
    usable = [g for g in geometries if g is not None and not g.is_empty]
    if not usable:
        raise CRSResolutionError(
            "No usable geometries to choose a projection for.",
            details={"reason": REASON_NO_USABLE},
        )

    bounds = shapely.bounds(np.array(usable, dtype=object))  # shape (n, 4)
    lons = np.concatenate([bounds[:, 0], bounds[:, 2]])
    lats = np.concatenate([bounds[:, 1], bounds[:, 3]])

    if (
        not (np.isfinite(lons).all() and np.isfinite(lats).all())
        or np.abs(lons).max() > 180.0
        or np.abs(lats).max() > 90.0
    ):
        raise CRSResolutionError(
            "Coordinates do not look like longitude/latitude degrees.",
            details={"reason": REASON_NOT_LONLAT},
        )

    min_lat = float(lats.min())
    max_lat = float(lats.max())
    center_lat = (min_lat + max_lat) / 2.0
    span, center_lon = circular_lon_extent(lons.tolist())

    if min_lat < UTM_MIN_LATITUDE or max_lat > UTM_MAX_LATITUDE:
        choice = _laea_choice(center_lon, center_lat, span, REASON_POLAR)
    else:
        zone = utm_zone_for(center_lon, center_lat)
        edges = (center_lon - span / 2.0, center_lon + span / 2.0)
        offset = max(abs(_wrap_lon(e - zone.central_longitude)) for e in edges)
        if offset <= MAX_UTM_OFFSET_DEG:
            choice = ProjectionChoice(
                crs=zone.crs,
                label=zone.label,
                strategy=STRATEGY_UTM,
                reason=REASON_SINGLE_ZONE,
                preserves="conformal",
                center_lon=center_lon,
                center_lat=center_lat,
                lon_span_deg=span,
            )
        else:
            choice = _laea_choice(center_lon, center_lat, span, REASON_TOO_WIDE)

    logger.info(
        "projection_chosen",
        extra={
            "projection_label": choice.label,
            "projection_strategy": choice.strategy,
            "projection_reason": choice.reason,
            "lon_span_deg": round(choice.lon_span_deg, 4),
        },
    )
    return choice


def _laea_choice(
    center_lon: float, center_lat: float, span: float, reason: str
) -> ProjectionChoice:
    crs, label = _laea_for(center_lon, center_lat)
    return ProjectionChoice(
        crs=crs,
        label=label,
        strategy=STRATEGY_LAEA,
        reason=reason,
        preserves="area",
        center_lon=center_lon,
        center_lat=center_lat,
        lon_span_deg=span,
    )