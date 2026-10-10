"""CRS resolution: understand a dataset's CRS and decide if it is safe to measure in.

Pure functions, no framework imports. Part 1 only parses and classifies the CRS.
Choosing a projected CRS to measure in comes in the next parts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pyproj import CRS
from pyproj.exceptions import CRSError

from app.core.exceptions import CRSResolutionError

logger = logging.getLogger(__name__)

REASON_MISSING = "missing_crs"
REASON_INVALID = "invalid_crs"
REASON_UNSUPPORTED_TYPE = "unsupported_crs_type"


@dataclass(frozen=True)
class ResolvedCRS:
    """A parsed CRS plus the facts the measurement code needs."""

    crs: CRS
    label: str  # e.g. "EPSG:4326", or the CRS name when there is no EPSG code
    is_geographic: bool  # coordinates are degrees: NOT safe to measure in
    is_projected: bool  # coordinates are linear units: safe to measure in
    meters_per_unit: float | None  # projected CRS only (1.0 = metres, ~0.3048 = feet)


def _label_for(crs: CRS) -> str:
    authority = crs.to_authority()
    if authority is not None:
        return f"{authority[0]}:{authority[1]}"
    return crs.name


def _metres_per_unit(crs: CRS) -> float | None:
    if not crs.is_projected:
        return None
    axes = crs.axis_info
    if not axes:
        return None
    return float(axes[0].unit_conversion_factor)


def resolve_crs(crs_text: str | None) -> ResolvedCRS:
    """Parse crs_text (EPSG code, WKT, PROJ string...) into a ResolvedCRS.

    Raises CRSResolutionError (details["reason"] says why) when the CRS is
    missing, cannot be parsed, or is neither geographic nor projected.
    """
    if crs_text is None or not crs_text.strip():
        raise CRSResolutionError(
            "The dataset does not declare a CRS.",
            details={"reason": REASON_MISSING},
        )

    try:
        crs = CRS.from_user_input(crs_text.strip())
    except (CRSError, ValueError, TypeError) as exc:
        raise CRSResolutionError(
            "The CRS definition could not be understood.",
            details={"reason": REASON_INVALID, "crs_text": crs_text[:200]},
        ) from exc

    if not (crs.is_geographic or crs.is_projected):
        # e.g. geocentric (x, y, z) or local engineering CRS
        raise CRSResolutionError(
            "The CRS is neither geographic nor projected, so it cannot be used for measurement.",
            details={"reason": REASON_UNSUPPORTED_TYPE, "crs_name": crs.name},
        )

    resolved = ResolvedCRS(
        crs=crs,
        label=_label_for(crs),
        is_geographic=crs.is_geographic,
        is_projected=crs.is_projected,
        meters_per_unit=_metres_per_unit(crs),
    )
    logger.info(
        "crs_resolved",
        extra={
            "crs_label": resolved.label,
            "crs_geographic": resolved.is_geographic,
            "crs_meters_per_unit": resolved.meters_per_unit,
        },
    )
    return resolved