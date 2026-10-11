"""The Prometheus scrape endpoint. Render, after refreshing the live gauges."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_job_runner
from app.api.metrics_route import MetricsRoute
from app.infrastructure.metrics.registry import get_metrics
from app.workers.job_runner import JobRunner

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"], route_class=MetricsRoute)

RunnerDep = Annotated[JobRunner, Depends(get_job_runner)]


@router.get(
    "/metrics",
    summary="Prometheus metrics (text exposition format)",
    response_class=Response,
)
def metrics(runner: RunnerDep) -> Response:
    metrics_store = get_metrics()
    # queue_size and active_jobs are "right now" values, so read them at scrape
    # time. A failing runner must never make the scrape itself fail.
    try:
        stats = runner.stats()
        metrics_store.set_workload(queued=stats.queued, active=stats.active)
    except Exception:  # noqa: BLE001 - scraping must keep working
        logger.exception("workload_refresh_failed")
    return Response(
        content=metrics_store.render(), media_type=metrics_store.content_type
    )