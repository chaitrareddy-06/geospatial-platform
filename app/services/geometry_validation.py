from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity, make_valid

from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.geometry_kind import GeometryKind

# Skip-reason categories (used later as metric labels)
REASON_EMPTY = "empty_geometry"
REASON_UNKNOWN_TYPE = "unknown_geometry_type"
REASON_NON_FINITE = "non_finite_coordinates"
REASON_REPAIR_FAILED = "repair_failed"
REASON_NO_USABLE_PARTS = "no_usable_parts"


@dataclass(frozen=True)
class ValidationReport:
    total: int = 0
    valid: int = 0
    repaired: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


def _has_non_finite(geometry: BaseGeometry) -> bool:
    coords = shapely.get_coordinates(geometry)
    return coords.size > 0 and not bool(np.isfinite(coords).all())


def _clean_collection(geometry: BaseGeometry) -> BaseGeometry | None:
    """Drop empty parts from a collection, recursively. None if nothing is left."""
    if not hasattr(geometry, "geoms"):
        return None if geometry.is_empty else geometry
    parts = [_clean_collection(part) for part in geometry.geoms]
    kept = [part for part in parts if part is not None]
    if not kept:
        return None
    if len(kept) == len(list(geometry.geoms)) and all(
        a is b for a, b in zip(kept, geometry.geoms, strict=False)
    ):
        return geometry
    return type(geometry)(kept)


def _validate_feature(feature: Feature) -> tuple[Feature, str | None]:
    """Return (new_feature, skip_category). skip_category is None if kept."""
    geometry = feature.geometry

    # Null geometry: parsers already skipped it. Leave as is.
    if geometry is None:
        return feature, None

    if feature.kind is GeometryKind.UNKNOWN:
        reason = f"Unsupported geometry type: {geometry.geom_type}"
        return feature.with_skip_reason(reason), REASON_UNKNOWN_TYPE

    if geometry.is_empty:
        return feature.with_skip_reason("Geometry is empty"), REASON_EMPTY

    if _has_non_finite(geometry):
        return (
            feature.with_skip_reason("Geometry has NaN or infinite coordinates"),
            REASON_NON_FINITE,
        )

    repaired = False

    # Collections: drop empty parts first.
    if feature.kind is GeometryKind.GEOMETRY_COLLECTION:
        cleaned = _clean_collection(geometry)
        if cleaned is None:
            return (
                feature.with_skip_reason("Collection has no usable parts"),
                REASON_NO_USABLE_PARTS,
            )
        if cleaned is not geometry:
            geometry = cleaned
            repaired = True

    if not geometry.is_valid:
        try:
            fixed = make_valid(geometry)
        except Exception as exc:  # noqa: BLE001 - one bad feature must not stop the file
            return (
                feature.with_skip_reason(f"Could not repair geometry: {exc}"),
                REASON_REPAIR_FAILED,
            )
        if fixed.is_empty or not fixed.is_valid:
            return (
                feature.with_skip_reason(
                    f"Repair produced no usable geometry ({explain_validity(geometry)})"
                ),
                REASON_REPAIR_FAILED,
            )
        geometry = fixed
        repaired = True

    if repaired:
        return feature.with_geometry(geometry, repaired=True), None
    return feature, None


def validate_dataset(dataset: ParsedDataset) -> tuple[ParsedDataset, ValidationReport]:
    """Validate every feature. Returns a NEW dataset and a report. Never raises per feature."""
    new_features: list[Feature] = []
    reasons: Counter[str] = Counter()
    valid = repaired = skipped = 0

    for feature in dataset.features:
        was_skipped = feature.is_skipped
        try:
            new_feature, category = _validate_feature(feature)
        except Exception as exc:  # noqa: BLE001 - last-resort isolation
            new_feature = feature.with_skip_reason(f"Validation failed: {exc}")
            category = REASON_REPAIR_FAILED

        new_features.append(new_feature)

        if new_feature.is_skipped:
            skipped += 1
            if not was_skipped and category:
                reasons[category] += 1
            elif was_skipped:
                reasons["skipped_by_parser"] += 1
        elif new_feature.repaired:
            repaired += 1
        else:
            valid += 1

    report = ValidationReport(
        total=len(new_features),
        valid=valid,
        repaired=repaired,
        skipped=skipped,
        skip_reasons=dict(reasons),
    )
    return replace(dataset, features=tuple(new_features)), report