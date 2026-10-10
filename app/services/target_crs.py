"""Target CRS resolution: which CRS do we measure this dataset in?

Pure functions, no framework imports. The caller passes settings in as
parameters; this module never reads Settings.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely.geometry import Point

from app.core.exceptions import CRSResolutionError
from app.domain.entities.dataset import ParsedDataset
from app.services.crs_resolution import resolve_crs
from app.services.projection_strategy import MAX_UTM_OFFSET_DEG, choose_projection
from app.services.utm_selection import lonlat_bounds

logger = logging.getLogger(__name__)

STRATEGY_NATIVE = "native_projected"

REASON_NATIVE = "source_crs_is_projected_with_known_unit"
REASON_NOT_ASSUMABLE = "missing_crs_not_assumable"
REASON_REPROJECTION_FAILED = "reprojection_failed"
REASON_NO_USABLE = "no_usable_geometries"

_WEB_MERCATOR_EPSG = {3857, 3785, 900913}


@dataclass(frozen=True)
class TargetCRS:
    """The decision: where to measure, why, and what was assumed along the way."""

    source_label: str  # the dataset's CRS, e.g. "EPSG:4326"
    source_assumed: bool  # True when the dataset had no CRS and we assumed 4326
    measurement_crs: CRS
    measurement_label: str  # e.g. "EPSG:32644" or "LAEA(lat_0=..,lon_0=..)"
    strategy: str  # "native_projected", "utm" or "laea"
    reason: str
    needs_reprojection: bool  # False only when the source CRS is used as is
    meters_per_unit: float  # 1.0 for UTM/LAEA; may be ~0.3048 for native feet
    warnings: tuple[str, ...] = ()


def _is_missing(crs_text: str | None) -> bool:
    return crs_text is None or not crs_text.strip()


def _is_web_mercator(crs: CRS) -> bool:
    if crs.to_epsg() in _WEB_MERCATOR_EPSG:
        return True
    name = crs.name.lower()
    return "pseudo-mercator" in name or "mercator_auxiliary_sphere" in name


def _fits_lonlat(bounds: tuple[float, float, float, float]) -> bool:
    minx, miny, maxx, maxy = bounds
    return -180.0 <= minx and maxx <= 180.0 and -90.0 <= miny and maxy <= 90.0


def _projected_bounds_to_lonlat(
    crs: CRS, bounds: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    try:
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        result = transformer.transform_bounds(*bounds)
    except ProjError as exc:
        raise CRSResolutionError(
            "Could not convert the dataset extent to longitude/latitude.",
            details={"reason": REASON_REPROJECTION_FAILED},
        ) from exc
    if not all(math.isfinite(v) for v in result):
        raise CRSResolutionError(
            "Converting the dataset extent to longitude/latitude produced invalid values.",
            details={"reason": REASON_REPROJECTION_FAILED},
        )
    return result  # type: ignore[no-any-return]


def resolve_target_crs(
    dataset: ParsedDataset,
    *,
    assume_wgs84_if_missing: bool = False,
    max_utm_offset_deg: float = MAX_UTM_OFFSET_DEG,
) -> TargetCRS:
    """Decide which CRS to measure a dataset in.

    Raises CRSResolutionError (details["reason"] says why) for a missing or
    invalid CRS, no usable geometries, or an extent that cannot be converted.
    """
    geometries = [f.geometry for f in dataset.features if not f.is_skipped]
    bounds = lonlat_bounds(geometries)  # works on any coordinates, not just lon/lat
    if bounds is None:
        raise CRSResolutionError(
            "The dataset has no usable geometries to measure.",
            details={"reason": REASON_NO_USABLE},
        )

    warnings: list[str] = []
    assumed = False

    if _is_missing(dataset.crs_text) and assume_wgs84_if_missing:
        if not _fits_lonlat(bounds):
            raise CRSResolutionError(
                "The dataset has no CRS and its coordinates do not look like "
                "longitude/latitude, so EPSG:4326 cannot be assumed.",
                details={"reason": REASON_NOT_ASSUMABLE},
            )
        resolved = resolve_crs("EPSG:4326")
        assumed = True
        warnings.append(
            "No CRS declared; assumed EPSG:4326 because all coordinates fit "
            "longitude/latitude ranges. Verify this before trusting measurements."
        )
    else:
        resolved = resolve_crs(dataset.crs_text)  # raises for missing or invalid

    trusted_projected = (
        resolved.is_projected
        and resolved.meters_per_unit is not None
        and not _is_web_mercator(resolved.crs)
    )
    if trusted_projected:
        assert resolved.meters_per_unit is not None
        result = TargetCRS(
            source_label=resolved.label,
            source_assumed=assumed,
            measurement_crs=resolved.crs,
            measurement_label=resolved.label,
            strategy=STRATEGY_NATIVE,
            reason=REASON_NATIVE,
            needs_reprojection=False,
            meters_per_unit=resolved.meters_per_unit,
            warnings=tuple(warnings),
        )
    else:
        if resolved.is_projected:
            if _is_web_mercator(resolved.crs):
                warnings.append(
                    "Source CRS is Web Mercator, which inflates areas away from the "
                    "equator; measuring in a better projection instead."
                )
            else:
                warnings.append(
                    "Source CRS has no usable linear unit; measuring in a better "
                    "projection instead."
                )
            minx, miny, maxx, maxy = _projected_bounds_to_lonlat(resolved.crs, bounds)
        else:
            minx, miny, maxx, maxy = bounds

        # choose_projection only uses each geometry's bounds, so two corner
        # points carry the same information as the full dataset.
        corners = [Point(minx, miny), Point(maxx, maxy)]
        choice = choose_projection(corners, max_utm_offset_deg=max_utm_offset_deg)
        result = TargetCRS(
            source_label=resolved.label,
            source_assumed=assumed,
            measurement_crs=choice.crs,
            measurement_label=choice.label,
            strategy=choice.strategy,
            reason=choice.reason,
            needs_reprojection=True,
            meters_per_unit=1.0,
            warnings=tuple(warnings),
        )

    logger.info(
        "target_crs_resolved",
        extra={
            "source_crs": result.source_label,
            "source_crs_assumed": result.source_assumed,
            "measurement_crs": result.measurement_label,
            "crs_strategy": result.strategy,
            "crs_reason": result.reason,
        },
    )
    return result