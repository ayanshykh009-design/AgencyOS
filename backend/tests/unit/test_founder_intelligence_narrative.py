"""Regression tests for the founder intelligence narrative path (M9).

A fake provider asserts that the rendered prompt is sent as a real
``LLMMessage`` (not a raw dict), so providers can safely read
``message.role.value``. A second test proves unexpected failures are logged
rather than silently swallowed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pytest

from app.core.config import settings
from app.llm.models import ChatResult, LLMMessage, LLMUsage, MessageRole
from app.llm.providers import ProviderClient
from app.services.intelligence.founder_intelligence_service import (
    FounderIntelligenceService,
)

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _Signal:
    title = "Pipeline risk"
    summary = "Two deals stalled"
    severity = type("Sev", (), {"value": "high"})()
    business_impact = {"amount": 12000}
    priority_score = 0.9
    confidence = type("Conf", (), {"value": "high"})()
    evidence = ["e1"]


class _FakeProvider(ProviderClient):
    def __init__(self) -> None:
        self.messages: list[LLMMessage] | None = None
        self.closed = 0

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ANN002
        self.messages = list(messages)
        return ChatResult(
            text="Model-written narrative about stalled deals.",
            usage=LLMUsage("fake", "fake-model", 10, 5, 0.0),
            model="fake-model",
            finish_reason="stop",
        )

    async def embeddings(self, inputs):  # noqa: ANN001
        raise AssertionError("not used")

    async def aclose(self) -> None:
        self.closed += 1


class _UnexpectedProvider(_FakeProvider):
    async def chat(self, messages, **kwargs):  # noqa: ANN001, ANN002
        raise TypeError("'str' object has no attribute 'value'")


async def test_generate_narrative_uses_model_text_with_llm_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeProvider()
    service = FounderIntelligenceService(session=None)  # type: ignore[arg-type]

    async def fake_llm(self: Any, organization_id: uuid.UUID) -> Any:
        from app.llm.service import LLMService

        return LLMService(provider)

    monkeypatch.setattr(settings, "INTELLIGENCE_NARRATIVE_ENABLED", True)
    monkeypatch.setattr(FounderIntelligenceService, "_llm_service", fake_llm)

    narrative = await service.generate_narrative(ORG_ID, [_Signal()])  # type: ignore[list-item]

    assert narrative == "Model-written narrative about stalled deals."
    assert provider.messages is not None
    assert len(provider.messages) == 1
    message = provider.messages[0]
    assert isinstance(message, LLMMessage)
    assert message.role is MessageRole.SYSTEM
    assert message.role.value == "system"
    assert "business intelligence analyst" in message.content
    # The prompt must actually interpolate the bounded signal context; a
    # descriptive line without a {{ signalsJson }} placeholder regressed here.
    assert "Pipeline risk" in message.content
    assert provider.closed == 1


async def test_generate_narrative_logs_unexpected_failure_and_falls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = _UnexpectedProvider()
    service = FounderIntelligenceService(session=None)  # type: ignore[arg-type]

    async def fake_llm(self: Any, organization_id: uuid.UUID) -> Any:
        from app.llm.service import LLMService

        return LLMService(provider)

    monkeypatch.setattr(settings, "INTELLIGENCE_NARRATIVE_ENABLED", True)
    monkeypatch.setattr(FounderIntelligenceService, "_llm_service", fake_llm)

    with caplog.at_level(logging.ERROR, logger="agencyos.founder.intelligence"):
        narrative = await service.generate_narrative(ORG_ID, [_Signal()])  # type: ignore[list-item]

    assert "Pipeline risk" in narrative
    assert "unexpected intelligence narrative failure" in caplog.text
    assert provider.closed == 1
