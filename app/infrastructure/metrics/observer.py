"""Adapter: turns service events into plain numbers for the Metrics class."""

from __future__ import annotations

from app.core.exceptions import CRSResolutionError
from app.domain.entities.file_record import FileRecord
from app.domain.enums.job_status import JobStatus
from app.infrastructure.metrics.registry import Metrics
from app.services.dataset_processing import DatasetResult


class MetricsObserver:
    def __init__(self, metrics: Metrics) -> None:
        self._metrics = metrics

    def upload_accepted(self, record: FileRecord) -> None:
        self._metrics.record_upload(record.size_bytes)

    def dataset_processed(self, result: DatasetResult) -> None:
        self._metrics.record_dataset(
            kind_counts=result.kind_counts,
            measured=result.measured_count,
            skipped=result.skipped_count,
            failed=result.failed_count,
            area_calculations=result.area_calculations,
            length_calculations=result.length_calculations,
            duration_seconds=result.duration_ms / 1000.0,
            crs_strategy=result.target.strategy,
            reprojected=result.target.needs_reprojection,
            repaired=result.validation.repaired,
            invalid=result.validation.invalid,
            skip_reasons=result.validation.skip_reasons,
        )

    def job_finished(self, record: FileRecord) -> None:
        duration = (
            record.processing_ms / 1000.0 if record.processing_ms is not None else None
        )
        if record.status is JobStatus.COMPLETED:
            self._metrics.record_job(success=True, duration_seconds=duration)
            return

        reason = record.error_reason or record.error_code
        self._metrics.record_job(
            success=False, reason=reason, duration_seconds=duration
        )
        if record.error_code == CRSResolutionError.error_code and record.error_reason:
            self._metrics.record_crs_failure(record.error_reason)