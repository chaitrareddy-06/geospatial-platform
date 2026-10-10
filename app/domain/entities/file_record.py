from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus


@dataclass(frozen=True)
class LayerSummary:
    """Counts and CRS decision for one dataset (layer) inside an upload."""

    name: str
    feature_count: int
    measured_count: int
    skipped_count: int
    failed_count: int
    crs: str  # the dataset's own CRS, e.g. "EPSG:4326"
    crs_strategy: str  # "native_projected" | "utm" | "laea"
    crs_reason: str


@dataclass(frozen=True)
class FileRecord:
    """One uploaded file and the outcome of processing it."""

    id: str
    filename: str
    kind: FileKind
    size_bytes: int
    sha256: str
    status: JobStatus
    created_at: datetime
    completed_at: datetime | None = None
    feature_count: int = 0
    crs: str | None = None  # the single CRS, or "multiple"
    layers: tuple[LayerSummary, ...] = ()
    warnings: tuple[str, ...] = ()
    processing_ms: float | None = None
    error_code: str | None = None  # stable machine code, e.g. "crs_resolution_failed"
    error_reason: str | None = None  # finer code, e.g. "missing_crs"
    error_message: str | None = None  # human sentence