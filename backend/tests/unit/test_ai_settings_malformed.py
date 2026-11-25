"""PATCH /ai/settings must normalize malformed JSONB settings, never 500."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.ai_service import AIService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _NoOrgSession:
    pass


class _Org:
    def __init__(self, settings: Any) -> None:
        self.settings = settings


class _FakeOrgService:
    def __init__(self, settings: Any) -> None:
        self._org = _Org(settings)
        self.update_calls: list[dict[str, Any]] = []

    async def get(self, organization_id: uuid.UUID) -> _Org:
        return self._org

    async def update_settings(
        self, organization_id: uuid.UUID, settings_update: dict[str, Any]
    ) -> None:
        self.update_calls.append(settings_update)


@pytest.mark.parametrize("raw", ["not-a-dict", 42, None, ["x"]])
async def test_update_settings_with_non_dict_settings(
    monkeypatch: pytest.MonkeyPatch, raw: Any
) -> None:
    fake = _FakeOrgService(raw)
    monkeypatch.setattr(
        "app.services.organization_service.OrganizationService",
        lambda session: fake,
    )

    service = AIService(_NoOrgSession())  # type: ignore[arg-type]
    await service.update_ai_settings(ORG_ID, model="gpt-4o")

    assert fake.update_calls == [{"ai": {"model": "gpt-4o"}}]


@pytest.mark.parametrize("raw_ai", ["not-a-dict", 7, None, ["x"]])
async def test_update_settings_with_non_dict_ai(
    monkeypatch: pytest.MonkeyPatch, raw_ai: Any
) -> None:
    fake = _FakeOrgService({"other": "keep-me", "ai": raw_ai})
    monkeypatch.setattr(
        "app.services.organization_service.OrganizationService",
        lambda session: fake,
    )

    service = AIService(_NoOrgSession())  # type: ignore[arg-type]
    await service.update_ai_settings(ORG_ID, provider="openai", kill_switch=True)

    assert fake.update_calls == [{"ai": {"provider": "openai", "kill_switch": True}}]
