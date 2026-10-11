"""The upload flow: validate, detect duplicates, queue, parse, process, store.

This service knows nothing about HTTP. The API reads the bytes and calls
``submit`` (fast: record is QUEUED) and a job runner later calls ``run_job``
(slow: parse and measure). ``ingest`` does both in one go and is kept for
synchronous use and tests. Settings are read by the caller and passed to the
constructor.

Failure behaviour
-----------------
* Cheap upload checks (empty, wrong type, too large) raise right away and
  nothing is stored.
* A content-hash match with a COMPLETED upload raises DuplicateFileError.
* After submit, every failure is recorded: the record ends up FAILED with an
  error code, so the outcome can be looked up later. Unexpected crashes are
  logged in full but only a generic message is stored.
* Per-feature results are stored BEFORE the record is marked COMPLETED, so a
  reader never sees a COMPLETED file without its features. FAILED files store
  no features.
* run_job only works on QUEUED records, so running the same job twice (a
  retry, a duplicated queue message) does nothing the second time.
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
from app.domain.entities.feature_page import FeaturePage
from app.domain.entities.file_record import FileRecord, LayerSummary
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus
from app.repositories.feature_result_repository import FeatureResultRepository
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
        feature_repository: FeatureResultRepository | None = None,
    ) -> None:
        self._repository = repository
        self._features = feature_repository
        self._assume_wgs84_if_missing = assume_wgs84_if_missing
        self._max_utm_offset_deg = max_utm_offset_deg
        self.max_upload_size_bytes = max_upload_size_bytes

    # ------------------------------------------------------------------
    # Accepting an upload (fast)

    def submit(self, filename: str, content: bytes) -> FileRecord:
        """Validate the upload and store a QUEUED record. Does no processing."""
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
            status=JobStatus.QUEUED,
            created_at=_now(),
        )
        self._repository.add(record)
        logger.info(
            "file_queued",
            extra={"file_id": record.id, "size_bytes": record.size_bytes},
        )
        return record

    # ------------------------------------------------------------------
    # Processing a queued upload (slow)

    def run_job(self, file_id: str, content: bytes) -> FileRecord:
        """Process a QUEUED record and return its final record.

        Raises ResourceNotFoundError for an unknown id. A record that is not
        QUEUED is returned unchanged (safe to call twice).
        """
        record = self.get(file_id)
        if record.status is not JobStatus.QUEUED:
            logger.info(
                "job_skipped_not_queued",
                extra={"file_id": file_id, "status": record.status.value},
            )
            return record

        processing = replace(record, status=JobStatus.PROCESSING)
        self._repository.update(processing)

        token = job_id_ctx.set(record.id)
        try:
            return self._run(processing, content)
        finally:
            job_id_ctx.reset(token)

    def ingest(self, filename: str, content: bytes) -> FileRecord:
        """Submit and process in one call (synchronous). Returns the final record."""
        record = self.submit(filename, content)
        return self.run_job(record.id, content)

    # ------------------------------------------------------------------
    # Reading

    def get(self, file_id: str) -> FileRecord:
        record = self._repository.get(file_id)
        if record is None:
            raise ResourceNotFoundError("File not found.", details={"id": file_id})
        return record

    def list_measurements(
        self,
        file_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        status: str | None = None,
    ) -> tuple[FileRecord, FeaturePage]:
        """Return the file record and one page of its per-feature results.

        Raises ResourceNotFoundError for an unknown id. A file that is not
        COMPLETED simply has an empty page; the record's status says why.
        """
        record = self.get(file_id)
        if self._features is None:
            return record, FeaturePage(items=(), total=0, offset=offset, limit=limit)
        page = self._features.list_page(
            file_id, offset=offset, limit=limit, status=status
        )
        return record, page

    # ------------------------------------------------------------------

    def _store_features(self, file_id: str, results: list[DatasetResult]) -> None:
        if self._features is None:
            return
        for result in results:
            self._features.add_layer(file_id, result.source_name, result.features)

    def _run(self, record: FileRecord, content: bytes) -> FileRecord:
        started = time.perf_counter()
        try:
            results = self._process(record.kind, content, record.filename)
            self._store_features(record.id, results)
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