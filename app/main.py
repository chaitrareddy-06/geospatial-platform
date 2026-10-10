import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api.error_handlers import register_exception_handlers
from app.api.v1 import health
from app.core.config import settings
from app.core.logging_config import configure_logging, request_id_ctx

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    configure_logging(settings.log_level)

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

    register_exception_handlers(app)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()