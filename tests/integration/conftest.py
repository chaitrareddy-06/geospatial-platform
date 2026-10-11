"""Fixtures for API tests: a client whose service uses a fresh in-memory store.

By default the job runner is INLINE (the job finishes before the next request),
so tests are deterministic. Pass ``runner=`` to use a different one.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_file_service, get_job_runner
from app.main import create_app
from app.workers.job_runner import InlineJobRunner


@pytest.fixture
def make_client(make_service):
    def build(service=None, runner=None) -> TestClient:
        app = create_app()
        chosen = service if service is not None else make_service()
        chosen_runner = runner if runner is not None else InlineJobRunner(chosen)
        app.dependency_overrides[get_file_service] = lambda: chosen
        app.dependency_overrides[get_job_runner] = lambda: chosen_runner
        return TestClient(app)

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()