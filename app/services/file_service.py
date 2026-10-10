"""The upload flow: validate, detect duplicates, parse, process, store.

This service knows nothing about HTTP. The API reads the bytes and calls
``ingest``; settings are read by the caller and passed to the constructor.

Failure behaviour
-----------------
* Cheap upload checks (empty, wrong type, too large) raise right away and
  nothing is stored.
* A content-hash match with a COMPLETED upload raises DuplicateFileError.
* After that point every failure is recorded: the record ends up FAILED with
  an error code, so the outcome can be looked up later. Unexpected crashes are
  logged in full but only a generic message is stored.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.core.exceptions import (
    AppError,
    DuplicateFileError,
    GeometryProcessingError,
    ResourceNotFoundError,
)
from app.core.logging_config import job_id_ctx
from app.domain.entities.file_record import FileRecord, LayerSummary
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus
from app.repositories.file_repository import FileRepository
from app.services.dataset_processing import DatasetResult, process_dataset
from app.services.file_validation import validate_upload
from app.services.kml_parser import parse_kml
from app.services.shapefile_parser import parse_shapefile_zip

logger = logging.getLogger(__name__)

ERROR_INTERNAL = "internal_error"
REASON_NO_DATASETS = "no_datasets"
MULTIPLE_CRS = "multiple"


def _now() -> datetime:
    return datetime.now(UTC)


def _layer_summary(result: DatasetResult) -> LayerSummary:
    return LayerSummary(
        name=result.source_name,
        feature_count=result.feature_count,
        measured_count=result.measured_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        crs=result.target.source_label,
        crs_strategy=result.target.strategy,
        crs_reason=result.target.reason,
    )


class FileService:
    def __init__(
        self,
        repository: FileRepository,
        *,
        assume_wgs84_if_missing: bool,
        max_utm_offset_deg: float,
        max_upload_size_bytes: int,
    ) -> None:
        self._repository = repository
        self._assume_wgs84_if_missing = assume_wgs84_if_missing
        self._max_utm_offset_deg = max_utm_offset_deg
        self.max_upload_size_bytes = max_upload_size_bytes

    def ingest(self, filename: str, content: bytes) -> FileRecord:
        """Validate, process and store one upload. Returns the final record."""
        upload = validate_upload(
            filename, content, max_size_bytes=self.max_upload_size_bytes
        )

        existing = self._repository.find_completed_by_sha256(upload.sha256)
        if existing is not None:
            logger.info(
                "duplicate_upload_rejected",
                extra={"source_file": upload.filename, "existing_id": existing.id},
            )
            raise DuplicateFileError(
                details={"existing_id": existing.id, "sha256": upload.sha256}
            )

        record = FileRecord(
            id=uuid.uuid4().hex,
            filename=upload.filename,
            kind=upload.kind,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            status=JobStatus.PROCESSING,
            created_at=_now(),
        )
        self._repository.add(record)

        token = job_id_ctx.set(record.id)
        try:
            return self._run(record, content)
        finally:
            job_id_ctx.reset(token)

    def get(self, file_id: str) -> FileRecord:
        record = self._repository.get(file_id)
        if record is None:
            raise ResourceNotFoundError("File not found.", details={"id": file_id})
        return record

    # ------------------------------------------------------------------

    def _run(self, record: FileRecord, content: bytes) -> FileRecord:
        started = time.perf_counter()
        try:
            results = self._process(record.kind, content, record.filename)
        except AppError as exc:
            details = exc.details or {}
            finished = replace(
                record,
                status=JobStatus.FAILED,
                completed_at=_now(),
                processing_ms=(time.perf_counter() - started) * 1000.0,
                error_code=exc.error_code,
                error_reason=details.get("reason"),
                error_message=getattr(exc, "message", str(exc)),
            )
            logger.warning(
                "file_processing_failed",
                extra={
                    "file_id": record.id,
                    "error_code": finished.error_code,
                    "reason": finished.error_reason,
                },
            )
        except Exception:  # noqa: BLE001 - a crash must become a FAILED record
            logger.exception("file_processing_crashed", extra={"file_id": record.id})
            finished = replace(
                record,
                status=JobStatus.FAILED,
                completed_at=_now(),
                processing_ms=(time.perf_counter() - started) * 1000.0,
                error_code=ERROR_INTERNAL,
                error_message="Unexpected error while processing the file.",
            )
        else:
            layers = tuple(_layer_summary(r) for r in results)
            labels = {layer.crs for layer in layers}
            finished = replace(
                record,
                status=JobStatus.COMPLETED,
                completed_at=_now(),
                processing_ms=(time.perf_counter() - started) * 1000.0,
                feature_count=sum(layer.feature_count for layer in layers),
                crs=labels.pop() if len(labels) == 1 else MULTIPLE_CRS,
                layers=layers,
                warnings=tuple(w for r in results for w in r.warnings),
            )
            logger.info(
                "file_processing_completed",
                extra={
                    "file_id": record.id,
                    "feature_count": finished.feature_count,
                    "duration_ms": round(finished.processing_ms or 0.0, 2),
                },
            )

        self._repository.update(finished)
        return finished

    def _process(
        self, kind: FileKind, content: bytes, filename: str
    ) -> list[DatasetResult]:
        if kind is FileKind.KML:
            datasets = [parse_kml(content, filename)]
        else:
            datasets = parse_shapefile_zip(content, filename)
        if not datasets:
            raise GeometryProcessingError(
                "The file contains no datasets to process.",
                details={"reason": REASON_NO_DATASETS},
            )
        return [
            process_dataset(
                dataset,
                assume_wgs84_if_missing=self._assume_wgs84_if_missing,
                max_utm_offset_deg=self._max_utm_offset_deg,
            )
            for dataset in datasets
        ]