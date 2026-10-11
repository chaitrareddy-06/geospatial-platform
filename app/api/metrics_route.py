"""Records HTTP metrics from inside the route, where the path template is known.

A custom APIRoute knows its own path template (e.g. /files/{file_id}/), but not
the prefix the router was mounted under (/api/v1, /api, or none). The prefix is
recovered per request: the concrete tail of this route (/files/abc/) is cut off
the real URL path, and what is left is the prefix. The label is prefix plus
template, so it never contains a raw ID.

Requests that match no route at all (unknown URLs, wrong method) never reach a
route, so a thin middleware in main.py records those as "unmatched". It tells
the two cases apart with a small holder dict that the route class flips.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.infrastructure.metrics.registry import get_metrics

logger = logging.getLogger(__name__)

UNMATCHED_PATH = "unmatched"
SCOPE_KEY = "metrics_holder"
VALIDATION_STATUS = 422
CRASH_STATUS = 500


def full_template(route_path: str, path_format: str, request: Request) -> str:
    """Return mount prefix + route template, e.g. /api/v1/files/{file_id}/."""
    actual = request.scope.get("path", "")
    try:
        params = {k: str(v) for k, v in request.path_params.items()}
        concrete = path_format.format(**params)
    except Exception:  # noqa: BLE001 - fall back to the bare template
        return route_path
    if concrete and actual.endswith(concrete):
        return actual[: len(actual) - len(concrete)] + route_path
    return route_path


def _record(method: str, path: str, status_code: int, started: float) -> None:
    """Count one request. A metrics problem must never affect the response."""
    try:
        if path.endswith("/metrics"):
            return  # scrapes would only count themselves
        get_metrics().record_request(
            method=method,
            path=path,
            status_code=status_code,
            duration_seconds=time.perf_counter() - started,
        )
    except Exception:  # noqa: BLE001 - metrics must never break a request
        logger.exception("request_metrics_failed")


def record_unmatched(method: str, status_code: int, started: float) -> None:
    """Used by the fallback middleware for requests that matched no route."""
    _record(method, UNMATCHED_PATH, status_code, started)


class MetricsRoute(APIRoute):
    """An APIRoute that records api_request_* metrics for its own requests."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_handler = super().get_route_handler()
        route_path = self.path
        path_format = self.path_format

        async def handler(request: Request) -> Response:
            started = time.perf_counter()
            status_code = CRASH_STATUS  # recorded if something unexpected escapes
            holder = request.scope.get(SCOPE_KEY)
            if isinstance(holder, dict):
                holder["recorded"] = True  # tells the fallback middleware to skip
            try:
                response = await original_handler(request)
                status_code = response.status_code
                return response
            except AppError as exc:
                status_code = exc.status_code
                raise
            except StarletteHTTPException as exc:
                status_code = exc.status_code
                raise
            except RequestValidationError:
                status_code = VALIDATION_STATUS
                raise
            finally:
                _record(
                    request.method,
                    full_template(route_path, path_format, request),
                    status_code,
                    started,
                )

        return handler