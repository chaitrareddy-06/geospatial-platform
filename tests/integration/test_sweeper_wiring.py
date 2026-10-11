"""The app lifespan starts the stale-job sweeper and stops it on shutdown."""

from fastapi.testclient import TestClient

from app.api.dependencies import get_stale_job_sweeper
from app.main import create_app


def test_lifespan_starts_and_stops_the_sweeper():
    get_stale_job_sweeper.cache_clear()

    with TestClient(create_app()):
        sweeper = get_stale_job_sweeper()
        assert sweeper.is_running

    # After shutdown the sweeper is stopped and dropped from the cache.
    assert not sweeper.is_running
    assert get_stale_job_sweeper.cache_info().currsize == 0