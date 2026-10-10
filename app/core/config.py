from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Geospatial Processing Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Logging
    log_level: str = "INFO"

    # Upload limits (used later by the file validation service)
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_uncompressed_size_bytes: int = 500 * 1024 * 1024  # 500 MB, zip bomb guard
    max_compression_ratio: int = 100  # zip bomb guard


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so the .env file is read only once."""
    return Settings()


settings = get_settings()