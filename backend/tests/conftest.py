"""Shared pytest fixtures for the backend test suites."""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Yield a test client bound to the ASGI app."""
    with TestClient(app) as test_client:
        yield test_client
