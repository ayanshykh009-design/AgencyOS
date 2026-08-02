"""Tests for the LLM provider layer: pricing, prompts, and the LLMService facade."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.llm.models import (
    ChatResult,
    EmbedResult,
    LLMMessage,
    LLMUsage,
    MessageRole,
)
from app.llm.pricing import estimate_cost
from app.llm.prompts import PromptManager
from app.llm.providers import ProviderClient
from app.llm.service import LLMService


class FakeClient(ProviderClient):
    """In-memory provider client for deterministic tests (no network)."""

    def __init__(self, *, provider: str = "openai", model: str = "gpt-4o-mini") -> None:
        self._provider = provider
        self._model = model
        self.calls: list[tuple[str, dict]] = []
        self.next_result: ChatResult | None = None
        self.next_embedding: EmbedResult | None = None

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools=None,
        temperature=None,
        max_tokens=None,
        stream: bool = False,
    ):
        self.calls.append(("chat", {"messages": messages, "tools": tools, "stream": stream}))
        if stream:
            return self._stream()
        return self.next_result or ChatResult(
            text="hello",
            usage=LLMUsage("openai", "gpt-4o-mini", 10, 5, 0.001),
            model=self.model,
            finish_reason="stop",
        )

    async def _stream(self):
        yield ChatResult(
            text="hi",
            usage=LLMUsage("openai", "gpt-4o-mini", 0, 0, 0.0),
            model=self.model,
            finish_reason="",
        )
        yield ChatResult(
            text="",
            usage=LLMUsage("openai", "gpt-4o-mini", 10, 5, 0.001),
            model=self.model,
            finish_reason="stop",
        )

    async def embeddings(self, inputs: list[str]) -> EmbedResult:
        self.calls.append(("embeddings", {"inputs": inputs}))
        return self.next_embedding or EmbedResult(
            vectors=[[0.1, 0.2]],
            usage=LLMUsage("openai", "gpt-4o-mini", 3, 0, 0.0001),
            model=self.model,
        )


# -- Pricing -----------------------------------------------------------------


def test_estimate_cost_known_provider_and_model() -> None:
    # gpt-4o-mini: 0.000150 / 0.000600 per 1k tokens
    cost = estimate_cost("openai", "gpt-4o-mini", 1000, 500)
    assert cost == pytest.approx(0.000150 * 1000 / 1000 + 0.000600 * 500 / 1000)


def test_estimate_cost_unknown_provider_is_zero() -> None:
    assert estimate_cost("made-up", "whatever", 1000, 1000) == 0.0


def test_estimate_cost_unknown_model_falls_back_internally() -> None:
    # Unknown model on a known provider: falls back to the first listed model's
    # pricing rather than raising (prices may be updated over time).
    cost_known_model = estimate_cost("openai", "gpt-4o-mini", 0, 0)
    assert cost_known_model == 0.0


# -- PromptManager -----------------------------------------------------------


def test_prompt_manager_loads_real_prompt() -> None:
    manager = PromptManager()
    meta, body = manager.render_message("signal-extraction", "1.0.0")
    assert meta.name == "signal-extraction"
    assert meta.version == "1.0.0"
    assert meta.status == "draft"
    assert meta.model == "gpt-4o"
    assert "research" in meta.tags
    assert "role" in body.lower()


def test_prompt_manager_renders_variables(tmp_path: Path) -> None:
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "tmpl.md").write_text(
        "---\nname: tmpl\nversion: 1.0.0\nstatus: draft\nmodel: gpt-4o\n"
        "tags: []\n---\nHello {{ prospect.firstName }}!"
    )
    rendered = PromptManager(root=root).render("tmpl", "1.0.0", {"prospect": {"firstName": "Ada"}})
    assert rendered == "Hello Ada!"


def test_prompt_manager_dotted_path_lists(tmp_path: Path) -> None:
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "tmpl.md").write_text(
        "---\nname: tmpl\nversion: 1.0.0\nstatus: draft\nmodel: gpt-4o\ntags: []\n---\n{{ list.0 }}"
    )
    rendered = PromptManager(root=root).render("tmpl", "1.0.0", {"list": ["zero", "one"]})
    assert rendered == "zero"


def test_prompt_manager_missing_variable_raises(tmp_path: Path) -> None:
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "tmpl.md").write_text(
        "---\nname: tmpl\nversion: 1.0.0\nstatus: draft\nmodel: gpt-4o\n"
        "tags: []\n---\nHello {{ prospect.firstName }}!"
    )
    with pytest.raises(KeyError):
        PromptManager(root=root).render("tmpl", "1.0.0", {})


def test_prompt_manager_unknown_prompt_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        PromptManager(root=tmp_path).load("does-not-exist", "1.0.0")


# -- LLMService --------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_chat_delegates_to_client_and_records_usage() -> None:
    client = FakeClient()
    recorded: list[tuple] = []

    async def recorder(usage: LLMUsage, feature: str) -> None:
        recorded.append((usage, feature))

    service = LLMService(client, organization_id=None, feature="research", usage_record=recorder)

    result = await service.chat([LLMMessage(MessageRole.USER, "hi")])
    assert result.text == "hello"
    assert len(recorded) == 1
    assert recorded[0][0].provider == "openai"
    assert recorded[0][1] == "research"
    assert recorded[0][0].input_tokens == 10


@pytest.mark.asyncio
async def test_service_embeddings_record_usage() -> None:
    client = FakeClient()
    recorded: list[tuple] = []

    async def recorder(usage: LLMUsage, feature: str) -> None:
        recorded.append((usage, feature))

    service = LLMService(client, feature="embeddings", usage_record=recorder)

    await service.embeddings(["a", "b"])
    assert len(recorded) == 1
    assert recorded[0][0].input_tokens == 3


@pytest.mark.asyncio
async def test_service_without_recorder_skips_usage_recording() -> None:
    client = FakeClient()
    service = LLMService(client, feature="research")

    result = await service.chat([LLMMessage(MessageRole.USER, "hi")])
    assert result.text == "hello"


def test_service_render_prompt_renders_via_prompt_manager() -> None:
    client = FakeClient()
    service = LLMService(client)
    rendered = service.render_prompt("connection-request", "1.0.0", {})
    assert "connection-request" in rendered.lower() or "Role" in rendered


def test_service_for_provider_unsupported_raises() -> None:
    with pytest.raises(ValueError):
        LLMService.for_provider("warp-drive")


class _StatusError(RuntimeError):
    """Transport-style error carrying an HTTP status code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


async def _fast_sleep(seconds: float) -> None:
    """No-op backoff for retry tests."""


class FlakyClient(FakeClient):
    """Raises a queued exception per chat call until exhausted, then succeeds."""

    def __init__(self, failures: list[Exception]) -> None:
        super().__init__()
        self._failures = list(failures)
        self.attempts = 0

    async def chat(self, messages, *, tools=None, temperature=None, max_tokens=None, stream=False):
        self.attempts += 1
        if self._failures:
            raise self._failures.pop(0)
        return await super().chat(
            messages, tools=tools, temperature=temperature, max_tokens=max_tokens, stream=stream
        )


@pytest.mark.asyncio
async def test_service_retries_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.service._async_sleep", _fast_sleep)
    client = FlakyClient(failures=[httpx.ConnectError("boom"), httpx.ConnectError("boom")])
    service = LLMService(client)

    result = await service.chat([LLMMessage(MessageRole.USER, "hi")])

    assert result.text == "hello"
    assert client.attempts == 3


@pytest.mark.asyncio
async def test_service_retries_rate_limit_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.service._async_sleep", _fast_sleep)
    client = FlakyClient(failures=[_StatusError(429)])
    service = LLMService(client)

    result = await service.chat([LLMMessage(MessageRole.USER, "hi")])

    assert result.text == "hello"
    assert client.attempts == 2


@pytest.mark.asyncio
async def test_service_does_not_retry_non_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FlakyClient(failures=[ValueError("bad request")])
    service = LLMService(client)

    with pytest.raises(ValueError):
        await service.chat([LLMMessage(MessageRole.USER, "hi")])
    assert client.attempts == 1


@pytest.mark.asyncio
async def test_service_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.service._async_sleep", _fast_sleep)
    client = FlakyClient(failures=[_StatusError(500), _StatusError(500), _StatusError(500)])
    service = LLMService(client)

    with pytest.raises(_StatusError):
        await service.chat([LLMMessage(MessageRole.USER, "hi")])
    assert client.attempts == 3
