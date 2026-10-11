"""The processing pipeline: one parsed dataset in, one complete result out.

Order of work
-------------
1. validate geometries (repair or skip bad ones)
2. decide the measurement CRS (UTM / equal-area / native projected)
3. build the transformers
4. measure every feature, each with its geodesic cross-check
5. roll everything up into a ``DatasetResult``

Failure behaviour
-----------------
* A bad FEATURE never stops the file: it becomes a "skipped" or "failed"
  entry with a reason (a sentence) and a reason_code (a stable code).
* A bad DATASET (no CRS, no usable geometry, extent that cannot be
  converted) raises ``CRSResolutionError``. The caller (the job runner)
  turns that into a FAILED job with the reason.

This module is pure: it does not read settings. The caller passes the
values in.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pyproj.exceptions import ProjError

from app.core.exceptions import CRSResolutionError
from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.entities.feature_result import ProcessedFeature
from app.domain.enums.file_kind import FileKind
from app.services.geodesic import (
    build_lonlat_transformer,
    measure_feature_checked,
)
from app.services.geometry_validation import (
    REASON_SKIPPED_BY_PARSER,
    ValidationReport,
    validate_dataset,
)
from app.services.measurement import FeatureMeasurement, build_transformer
from app.services.projection_strategy import MAX_UTM_OFFSET_DEG
from app.services.target_crs import TargetCRS, resolve_target_crs

logger = logging.getLogger(__name__)

REASON_TRANSFORMER_FAILED = "reprojection_failed"


@dataclass(frozen=True)
class DatasetResult:
    """Everything the API, the job runner and the metrics layer need."""

    source_name: str
    source_kind: FileKind
    target: TargetCRS
    validation: ValidationReport
    features: tuple[ProcessedFeature, ...]
    kind_counts: dict[str, int]
    measured_count: int
    skipped_count: int
    failed_count: int
    area_calculations: int  # features that produced an area
    length_calculations: int  # features that produced a length
    total_area_m2: float
    total_length_m: float
    max_abs_area_diff_pct: float | None  # worst projected-vs-geodesic gap
    duration_ms: float
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def feature_count(self) -> int:
        return len(self.features)


def _build_transformers(target: TargetCRS) -> tuple[Any | None, Any | None]:
    try:
        return build_transformer(target), build_lonlat_transformer(target)
    except ProjError as exc:
        raise CRSResolutionError(
            "Could not build the coordinate transformation for this dataset.",
            details={"reason": REASON_TRANSFORMER_FAILED},
        ) from exc


def _reason_code(feature: Feature, result: FeatureMeasurement) -> str | None:
    """Stable code for a skipped or failed feature; None when it was measured."""
    if result.status == "skipped":
        return feature.skip_code or REASON_SKIPPED_BY_PARSER
    if result.status == "failed":
        return result.reason
    return None


def process_dataset(
    dataset: ParsedDataset,
    *,
    assume_wgs84_if_missing: bool = False,
    max_utm_offset_deg: float = MAX_UTM_OFFSET_DEG,
) -> DatasetResult:
    """Run the full pipeline on one parsed dataset.

    Raises CRSResolutionError when the dataset as a whole cannot be measured.
    """
    started = time.perf_counter()

    validated, report = validate_dataset(dataset)

    target = resolve_target_crs(
        validated,
        assume_wgs84_if_missing=assume_wgs84_if_missing,
        max_utm_offset_deg=max_utm_offset_deg,
    )
    transformer, lonlat_transformer = _build_transformers(target)

    processed: list[ProcessedFeature] = []
    for feature in validated.features:
        checked = measure_feature_checked(
            feature, target, transformer, lonlat_transformer
        )
        result = checked.result
        processed.append(
            ProcessedFeature(
                index=feature.index,
                kind=feature.kind,
                status=result.status,
                reason=result.reason,
                reason_code=_reason_code(feature, result),
                repaired=result.repaired,
                properties=dict(feature.properties),
                measurement=result.measurement,
                cross_check=checked.cross_check,
                length_method=checked.length_method,
            )
        )

    areas = [
        p.measurement.area_m2
        for p in processed
        if p.measurement is not None and p.measurement.area_m2 is not None
    ]
    lengths = [
        p.measurement.length_m
        for p in processed
        if p.measurement is not None and p.measurement.length_m is not None
    ]
    area_diffs = [
        abs(p.cross_check.area_diff_pct)
        for p in processed
        if p.cross_check is not None and p.cross_check.area_diff_pct is not None
    ]
    statuses = Counter(p.status for p in processed)
    kind_counts = dict(Counter(p.kind.value for p in processed))

    outcome = DatasetResult(
        source_name=validated.source_name,
        source_kind=validated.source_kind,
        target=target,
        validation=report,
        features=tuple(processed),
        kind_counts=kind_counts,
        measured_count=statuses["measured"],
        skipped_count=statuses["skipped"],
        failed_count=statuses["failed"],
        area_calculations=len(areas),
        length_calculations=len(lengths),
        total_area_m2=float(sum(areas)),
        total_length_m=float(sum(lengths)),
        max_abs_area_diff_pct=max(area_diffs) if area_diffs else None,
        duration_ms=(time.perf_counter() - started) * 1000.0,
        warnings=tuple(validated.warnings) + target.warnings,
    )

    logger.info(
        "dataset_processed",
        extra={
            "source_file": outcome.source_name,
            "feature_count": outcome.feature_count,
            "measured_count": outcome.measured_count,
            "skipped_count": outcome.skipped_count,
            "failed_count": outcome.failed_count,
            "crs_strategy": target.strategy,
            "duration_ms": round(outcome.duration_ms, 2),
        },
    )
    return outcome