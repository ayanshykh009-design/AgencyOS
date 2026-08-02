"""API tests for the research endpoints.

Full CRUD needs a live DB + authenticated user (covered by integration),
so here we verify the routes are registered and guarded: unauthenticated
requests must receive a structured 401 without touching the database.
"""
from __future__ import annotations

import uuid

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def test_trigger_research_requires_auth(client) -> None:
    res = client.post(f"/api/v1/research/{LEAD_ID}")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_get_research_requires_auth(client) -> None:
    res = client.get(f"/api/v1/research/{LEAD_ID}")
    assert res.status_code == 401


def test_update_research_requires_auth(client) -> None:
    res = client.patch(f"/api/v1/research/{LEAD_ID}", json={"status": "completed"})
    assert res.status_code == 401


def test_delete_research_requires_auth(client) -> None:
    res = client.delete(f"/api/v1/research/{LEAD_ID}")
    assert res.status_code == 401
