from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["Operations"])


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    """Return 200 if the process is up. Does not check dependencies."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }