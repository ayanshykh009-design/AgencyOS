"""Unit tests for the AI automation service (settings + dispatch + manifest)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.models.organization import Organization
from app.services.ai_service import AIService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _FakeOrgSession:
    """AsyncSession stand-in: returns the same org object for every ``get``."""

    def __init__(self, org: Organization) -> None:
        self._org = org
        self.commits = 0

    async def get(self, model: Any, pk: Any) -> Organization | None:  # noqa: ANN401
        return self._org

    async def commit(self) -> None:
        self.commits += 1


class _NoOrgSession:
    """AsyncSession stand-in that behaves like the org row is missing."""

    async def get(self, model: Any, pk: Any) -> None:  # noqa: ANN401
        return None


def _org(*, ai: dict[str, Any] | None = None) -> Organization:
    org = Organization(name="Acme", slug="acme", settings={} if ai is None else {"ai": ai})
    org.id = ORG_ID
    return org


async def test_tools_returns_static_manifest() -> None:
    service = AIService(_NoOrgSession())
    manifest = await service.tools()

    names = {entry["name"] for entry in manifest}
    expected = {
        "lead_search",
        "lead_research",
        "http_get",
        "web_search",
        "draft_outreach",
        "n8n_dispatch",
    }
    assert expected == names
    for entry in manifest:
        assert entry["description"]
        assert entry["parameters"]["type"] == "object"


async def test_get_ai_settings_defaults_to_env() -> None:
    service = AIService(_NoOrgSession())
    provider, model, overridden = await service.get_ai_settings(ORG_ID)

    assert provider == settings.LLM_PROVIDER
    assert model == settings.LLM_DEFAULT_MODEL
    assert overridden is False


async def test_get_ai_settings_honors_org_override() -> None:
    org = _org(ai={"provider": "anthropic", "model": "claude-3-5-sonnet"})
    service = AIService(_FakeOrgSession(org))
    provider, model, overridden = await service.get_ai_settings(ORG_ID)

    assert provider == "anthropic"
    assert model == "claude-3-5-sonnet"
    assert overridden is True


async def test_update_ai_settings_merges_and_commits() -> None:
    org = _org()
    service = AIService(_FakeOrgSession(org))

    await service.update_ai_settings(ORG_ID, provider="deepseek", model="deepseek-chat")

    assert org.settings["ai"] == {"provider": "deepseek", "model": "deepseek-chat"}


async def test_update_ai_settings_rejects_unknown_provider() -> None:
    service = AIService(_FakeOrgSession(_org()))

    with pytest.raises(AppError) as exc:
        await service.update_ai_settings(ORG_ID, provider="mystery-model")
    assert exc.value.status_code == 400
    assert exc.value.code == "ai.invalid_provider"


async def test_update_ai_settings_noop_when_nothing_changes() -> None:
    org = _org()
    service = AIService(_FakeOrgSession(org))

    await service.update_ai_settings(ORG_ID)

    assert org.settings == {}


async def test_dispatch_fails_cleanly_without_n8n() -> None:
    service = AIService(_NoOrgSession())

    with pytest.raises(AppError) as exc:
        await service.dispatch(workflow="outreach-dispatch", payload={"msg": "hi"})

    assert exc.value.status_code == 502
    assert exc.value.code == "ai.dispatch_failed"
