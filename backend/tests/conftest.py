"""Shared pytest fixtures for the backend test suites."""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Yield a test client bound to the ASGI app.

    ``base_url`` uses a trusted host so the TrustedHostMiddleware (which
    allow-lists ``localhost``/``127.0.0.1``) does not reject test traffic.
    """
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client
