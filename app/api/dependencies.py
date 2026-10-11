"""Builds the objects the routes depend on. Settings are read HERE, not in services."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService
from app.workers.job_runner import JobRunner, ThreadPoolJobRunner

# Becomes a setting later; a constant keeps config.py untouched for now.
JOB_WORKERS = 2


@lru_cache
def get_repository() -> InMemoryFileRepository:
    """One store for the whole process. Replaced by PostgreSQL after Step 3."""
    return InMemoryFileRepository()


@lru_cache
def get_feature_repository() -> InMemoryFeatureResultRepository:
    """One per-feature store for the whole process. Also moves to PostgreSQL."""
    return InMemoryFeatureResultRepository()


@lru_cache
def get_file_service() -> FileService:
    return FileService(
        get_repository(),
        feature_repository=get_feature_repository(),
        assume_wgs84_if_missing=settings.assume_wgs84_if_missing_crs,
        max_utm_offset_deg=settings.max_utm_offset_degrees,
        max_upload_size_bytes=settings.max_upload_size_bytes,
    )


@lru_cache
def get_job_runner() -> JobRunner:
    """One background runner for the whole process. A Redis runner replaces it later."""
    return ThreadPoolJobRunner(get_file_service(), max_workers=JOB_WORKERS)


def shutdown_job_runner() -> None:
    """Stop the runner (waiting for running jobs) if one was ever created."""
    if get_job_runner.cache_info().currsize > 0:
        get_job_runner().shutdown(wait=True)
        get_job_runner.cache_clear()