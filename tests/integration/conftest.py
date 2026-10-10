"""Fixtures for API tests: a client whose service uses a fresh in-memory store."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_file_service
from app.main import create_app


@pytest.fixture
def make_client(make_service):
    def build(service=None) -> TestClient:
        app = create_app()
        chosen = service if service is not None else make_service()
        app.dependency_overrides[get_file_service] = lambda: chosen
        return TestClient(app)

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()