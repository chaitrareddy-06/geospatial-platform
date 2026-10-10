from fastapi import FastAPI

from app.api.v1 import health
from app.core.config import settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production-grade geospatial file processing service. "
            "Upload KML or zipped Shapefiles and get per-feature measurements "
            "computed in an appropriate projected CRS."
        ),
        debug=settings.debug,
    )

    app.include_router(health.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()