"""Builds the objects the routes depend on. Settings are read HERE, not in services."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService


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