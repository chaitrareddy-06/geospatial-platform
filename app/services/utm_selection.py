"""UTM zone selection (pure functions, no framework imports).

Input must be longitude/latitude in degrees (EPSG:4326 order: x=lon, y=lat).
Multi-zone datasets, the antimeridian and projected input are handled later.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import shapely
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import CRSResolutionError

logger = logging.getLogger(__name__)

REASON_INVALID_COORDINATES = "invalid_coordinates"
REASON_OUTSIDE_UTM_RANGE = "outside_utm_range"

UTM_MAX_LATITUDE = 84.0
UTM_MIN_LATITUDE = -80.0


@dataclass(frozen=True)
class UTMSelection:
    crs: CRS
    label: str  # e.g. "EPSG:32644"
    zone: int  # 1..60
    hemisphere: str  # "N" or "S"
    central_longitude: float  # centre line of the zone, in degrees


def utm_zone_for(longitude: float, latitude: float) -> UTMSelection:
    """Return the UTM CRS covering one lon/lat point."""
    if not (math.isfinite(longitude) and math.isfinite(latitude)):
        raise CRSResolutionError(
            "Coordinates are not finite numbers.",
            details={"reason": REASON_INVALID_COORDINATES},
        )
    if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
        raise CRSResolutionError(
            "Coordinates are outside valid longitude/latitude ranges.",
            details={
                "reason": REASON_INVALID_COORDINATES,
                "longitude": longitude,
                "latitude": latitude,
            },
        )
    if not (UTM_MIN_LATITUDE <= latitude <= UTM_MAX_LATITUDE):
        raise CRSResolutionError(
            "Latitude is outside the range where UTM is defined (80S to 84N).",
            details={"reason": REASON_OUTSIDE_UTM_RANGE, "latitude": latitude},
        )

    zone = min(int((longitude + 180.0) // 6) + 1, 60)  # lon=180 would give 61
    northern = latitude >= 0
    epsg = (32600 if northern else 32700) + zone
    selection = UTMSelection(
        crs=CRS.from_epsg(epsg),
        label=f"EPSG:{epsg}",
        zone=zone,
        hemisphere="N" if northern else "S",
        central_longitude=-183.0 + 6.0 * zone,
    )
    logger.info(
        "utm_zone_selected",
        extra={"utm_label": selection.label, "utm_zone": zone},
    )
    return selection


def lonlat_bounds(
    geometries: Iterable[BaseGeometry | None],
) -> tuple[float, float, float, float] | None:
    """Overall (minx, miny, maxx, maxy) of all usable geometries, or None.

    None and empty geometries are ignored.
    """
    usable = [g for g in geometries if g is not None and not g.is_empty]
    if not usable:
        return None
    minx, miny, maxx, maxy = shapely.total_bounds(np.array(usable, dtype=object))
    return (float(minx), float(miny), float(maxx), float(maxy))


def select_utm_for_bounds(
    bounds: tuple[float, float, float, float],
) -> UTMSelection:
    """Pick the UTM zone containing the centre of the bounding box."""
    minx, miny, maxx, maxy = bounds
    return utm_zone_for((minx + maxx) / 2.0, (miny + maxy) / 2.0)