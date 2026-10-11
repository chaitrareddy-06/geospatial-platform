"""Application settings, read from environment variables and an optional .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Geospatial Processing Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    max_upload_size_bytes: int = 50 * 1024 * 1024
    max_uncompressed_size_bytes: int = 500 * 1024 * 1024
    max_compression_ratio: int = 100

    # Max distance (degrees of longitude) any data may be from a UTM zone's centre
    # line before we switch to an equal-area projection. The cap of 10 is a
    # reasoned limit, not a standard: beyond it UTM distortion is too large.
    max_utm_offset_degrees: float = Field(default=4.0, gt=0, le=10)

    # Opt-in guess for files with no CRS: if every coordinate fits lon/lat ranges,
    # treat the file as EPSG:4326 (always with a warning). Off by default because
    # a wrong guess means wrong measurements.
    assume_wgs84_if_missing_crs: bool = False

    # Number of background worker threads that process uploaded files. The bounds
    # are a sanity check: at least one worker, and a cap so a typo in .env cannot
    # start hundreds of threads on a small machine.
    job_workers: int = Field(default=2, ge=1, le=16)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()