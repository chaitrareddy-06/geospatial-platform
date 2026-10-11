"""Response models: what the API promises clients. Separate from domain objects."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.domain.entities.feature_page import FeaturePage, LayeredFeature
from app.domain.entities.feature_result import CrossCheck
from app.domain.entities.file_record import FileRecord, LayerSummary
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus


def json_safe(value: Any) -> Any:
    """Turn an attribute value into something strict JSON can carry.

    Shapefile attributes can be numpy numbers, dates or NaN/inf. NaN and inf
    are not valid JSON, so they become null; unknown objects become text.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    item = getattr(value, "item", None)  # numpy scalars
    if callable(item):
        try:
            return json_safe(item())
        except (ValueError, TypeError):
            pass
    return str(value)


class LayerOut(BaseModel):
    name: str
    feature_count: int
    measured_count: int
    skipped_count: int
    failed_count: int
    crs: str
    crs_strategy: str
    crs_reason: str

    @classmethod
    def from_summary(cls, layer: LayerSummary) -> LayerOut:
        return cls(
            name=layer.name,
            feature_count=layer.feature_count,
            measured_count=layer.measured_count,
            skipped_count=layer.skipped_count,
            failed_count=layer.failed_count,
            crs=layer.crs,
            crs_strategy=layer.crs_strategy,
            crs_reason=layer.crs_reason,
        )


class ErrorInfo(BaseModel):
    code: str
    reason: str | None = None
    message: str | None = None


class FileOut(BaseModel):
    """Metadata and status of one uploaded file."""

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: JobStatus
    kind: FileKind
    size_bytes: int
    sha256: str
    created_at: datetime
    completed_at: datetime | None
    processing_ms: float | None
    layers: list[LayerOut]
    warnings: list[str]
    error: ErrorInfo | None

    @classmethod
    def from_record(cls, record: FileRecord) -> FileOut:
        error = None
        if record.error_code is not None:
            error = ErrorInfo(
                code=record.error_code,
                reason=record.error_reason,
                message=record.error_message,
            )
        return cls(
            id=record.id,
            filename=record.filename,
            feature_count=record.feature_count,
            crs=record.crs,
            status=record.status,
            kind=record.kind,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            created_at=record.created_at,
            completed_at=record.completed_at,
            processing_ms=record.processing_ms,
            layers=[LayerOut.from_summary(layer) for layer in record.layers],
            warnings=list(record.warnings),
            error=error,
        )


class CrossCheckOut(BaseModel):
    """Projected vs geodesic comparison (percent = (projected - geodesic) / geodesic)."""

    geodesic_area_m2: float | None
    geodesic_length_m: float | None
    area_diff_pct: float | None
    length_diff_pct: float | None

    @classmethod
    def from_domain(cls, check: CrossCheck) -> CrossCheckOut:
        return cls(
            geodesic_area_m2=check.geodesic_area_m2,
            geodesic_length_m=check.geodesic_length_m,
            area_diff_pct=check.area_diff_pct,
            length_diff_pct=check.length_diff_pct,
        )


class FeatureMeasurementOut(BaseModel):
    """One feature's outcome. ``reason_code`` is for programs, ``reason`` for people."""

    index: int
    layer: str
    geometry_type: str
    status: str  # "measured" | "skipped" | "failed"
    reason: str | None
    reason_code: str | None
    repaired: bool
    area_m2: float | None
    length_m: float | None
    length_method: str | None
    part_count: int | None
    unsupported_parts: list[str]
    cross_check: CrossCheckOut | None
    properties: dict[str, Any]

    @classmethod
    def from_layered(cls, item: LayeredFeature) -> FeatureMeasurementOut:
        feature = item.feature
        measurement = feature.measurement
        return cls(
            index=feature.index,
            layer=item.layer,
            geometry_type=feature.kind.value,
            status=feature.status,
            reason=feature.reason,
            reason_code=feature.reason_code,
            repaired=feature.repaired,
            area_m2=measurement.area_m2 if measurement else None,
            length_m=measurement.length_m if measurement else None,
            length_method=feature.length_method,
            part_count=measurement.part_count if measurement else None,
            unsupported_parts=list(measurement.unsupported_parts) if measurement else [],
            cross_check=(
                CrossCheckOut.from_domain(feature.cross_check)
                if feature.cross_check
                else None
            ),
            properties=json_safe(feature.properties),
        )


class MeasurementPageOut(BaseModel):
    """One page of per-feature results for a file."""

    file_id: str
    file_status: JobStatus
    total: int  # all matching features, not just this page
    limit: int
    offset: int
    items: list[FeatureMeasurementOut]

    @classmethod
    def build(cls, record: FileRecord, page: FeaturePage) -> MeasurementPageOut:
        return cls(
            file_id=record.id,
            file_status=record.status,
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[FeatureMeasurementOut.from_layered(i) for i in page.items],
        )