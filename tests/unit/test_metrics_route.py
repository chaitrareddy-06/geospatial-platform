"""MetricsRoute records the status the client will see, from inside the route."""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import register_exception_handlers
from app.api.metrics_route import MetricsRoute
from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.metrics.registry import get_metrics

TEMPLATE = "/probe/{item_id}"


def _build_client() -> TestClient:
    router = APIRouter(route_class=MetricsRoute)

    @router.get(TEMPLATE)
    def probe(item_id: str) -> dict[str, bool]:
        if item_id == "missing":
            raise ResourceNotFoundError()
        if item_id == "boom":
            raise RuntimeError("boom")
        return {"ok": True}

    @router.get("/internal/metrics")
    def fake_scrape() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _count(path: str, status: int) -> float:
    child = get_metrics().api_requests.labels(method="GET", path=path, status=str(status))
    return child._value.get()  # noqa: SLF001 - reading the sample in a test


def test_app_error_is_recorded_with_its_own_status_code() -> None:
    client = _build_client()
    before = _count(TEMPLATE, 404)
    assert client.get("/probe/missing").status_code == 404
    assert _count(TEMPLATE, 404) == before + 1


def test_unexpected_crash_is_recorded_as_500() -> None:
    client = _build_client()
    before = _count(TEMPLATE, 500)
    assert client.get("/probe/boom").status_code == 500
    assert _count(TEMPLATE, 500) == before + 1


def test_scrape_path_is_not_counted() -> None:
    client = _build_client()
    before = _count("/internal/metrics", 200)
    assert client.get("/internal/metrics").status_code == 200
    assert _count("/internal/metrics", 200) == before