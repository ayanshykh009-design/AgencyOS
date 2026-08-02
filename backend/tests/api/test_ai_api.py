"""API tests for the AI automation endpoints.

Verifies routes are registered and unauthenticated requests get a structured
401 before touching the database (full behavior needs a live DB + JWT).
"""

from __future__ import annotations

import uuid

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def test_list_tools_requires_auth(client) -> None:
    res = client.get("/api/v1/ai/tools")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_get_ai_settings_requires_auth(client) -> None:
    res = client.get("/api/v1/ai/settings")
    assert res.status_code == 401


def test_patch_ai_settings_requires_auth(client) -> None:
    res = client.patch("/api/v1/ai/settings", json={"provider": "anthropic"})
    assert res.status_code == 401


def test_run_brain_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/ai/run",
        json={"goal": "draft_email", "lead_id": str(LEAD_ID)},
    )
    assert res.status_code == 401


def test_dispatch_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/ai/dispatch",
        json={"workflow": "outreach-dispatch", "payload": {"msg": "hi"}},
    )
    assert res.status_code == 401
