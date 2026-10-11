"""The Prometheus scrape endpoint. Thin on purpose: render and return."""

from fastapi import APIRouter, Response

from app.infrastructure.metrics.registry import get_metrics

router = APIRouter(tags=["ops"])


@router.get(
    "/metrics",
    summary="Prometheus metrics (text exposition format)",
    response_class=Response,
)
def metrics() -> Response:
    metrics_store = get_metrics()
    return Response(content=metrics_store.render(), media_type=metrics_store.content_type)