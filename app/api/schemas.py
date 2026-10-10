"""Response models: what the API promises clients. Separate from domain objects."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domain.entities.file_record import FileRecord, LayerSummary
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus


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