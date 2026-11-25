"""Regression tests for AI error sanitization and HTTP/provider client lifecycle.

These tests are deliberately self-contained unit tests: no database, no
migrations, no network.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from app.agents.executors.base import ExecutorContext
from app.agents.executors.brain_executor import ResearchAgentExecutor
from app.ai.brain import Brain, BrainConfig, ToolRegistry
from app.core.config import settings
from app.core.errors import AppError
from app.llm.error_sanitizer import safe_error
from app.llm.models import ChatResult, LLMUsage, ToolCall
from app.llm.providers import ProviderClient
from app.llm.service import LLMService, aclose_llm
from app.services.ai_service import AIService
from app.tools.base import ToolResult

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000202")
TRACE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

_SECRET = "Bearer sk-super-secret-123"
_HOST = "https://n8n.internal.example"
_BODY = '{"password":"hunter2"}'


class _NoOrgSession:
    async def get(self, model: Any, pk: Any) -> None:  # noqa: ANN401
        return None


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"ok": True}


class _CountingClient:
    """AsyncClient stand-in that records close() calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.closed = 0
        self.posts: list[str] = []

    async def post(self, url: str, json: Any = None) -> _FakeResponse:
        self.posts.append(url)
        if self.fail:
            raise httpx.ConnectError(f"POST {url} failed {_BODY} {_SECRET}")
        return _FakeResponse()

    async def aclose(self) -> None:
        self.closed += 1


# -- sanitization boundary ---------------------------------------------------


def test_safe_error_returns_public_message_and_logs_sanitized_metadata_only(caplog) -> None:
    with caplog.at_level("WARNING", logger="agencyos"):
        message = safe_error(
            RuntimeError(f"GET {_HOST} {_SECRET}"),
            public="stable public message",
            log_label="test.boundary",
        )
    assert message == "stable public message"
    assert "test.boundary" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "sanitized upstream failure" in caplog.text
    assert _HOST not in caplog.text
    assert _SECRET not in caplog.text
    assert _BODY not in caplog.text


def test_safe_error_does_not_log_raw_string_detail(caplog) -> None:
    with caplog.at_level("WARNING", logger="agencyos"):
        message = safe_error(
            f"POST {_HOST} {_BODY} {_SECRET}",
            public="stable public message",
            log_label="test.string-boundary",
        )
    assert message == "stable public message"
    assert "test.string-boundary" in caplog.text
    assert "type=str" in caplog.text
    assert _HOST not in caplog.text
    assert _BODY not in caplog.text
    assert _SECRET not in caplog.text


async def test_n8n_tool_hides_transport_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.tools.n8n_tool import N8nDispatchTool

    monkeypatch.setattr(settings, "N8N_BASE_URL", _HOST)
    client = _CountingClient(fail=True)
    tool = N8nDispatchTool(client=client)  # type: ignore[arg-type]

    result = await tool.run({"workflow": "outreach-dispatch", "payload": {"x": 1}})

    assert result.ok is False
    assert result.error == "n8n dispatch failed"
    assert _HOST not in (result.error or "")
    assert _BODY not in (result.error or "")
    assert _SECRET not in (result.error or "")


async def test_dispatch_hides_tool_error_text_and_sanitizes_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingTool:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def run(self, input: dict[str, Any]) -> ToolResult:
            return ToolResult(ok=False, error=f"POST {_HOST} {_BODY} {_SECRET}")

    monkeypatch.setattr("app.tools.n8n_tool.N8nDispatchTool", _FailingTool)
    service = AIService(_NoOrgSession(), http_client=_CountingClient())  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc:
        await service.dispatch(workflow="outreach-dispatch", payload={"x": 1})

    assert exc.value.code == "ai.dispatch_failed"
    assert exc.value.message == "n8n dispatch failed"
    assert _HOST not in exc.value.message
    assert _BODY not in exc.value.message
    assert _SECRET not in exc.value.message


# -- lazy HTTP client lifecycle ---------------------------------------------


async def test_dispatch_closes_owned_client_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_CountingClient] = []

    def _factory(**kwargs: Any) -> _CountingClient:
        client = _CountingClient()
        created.append(client)
        return client

    monkeypatch.setattr(settings, "N8N_BASE_URL", _HOST)
    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", _factory)

    service = AIService(_NoOrgSession())
    # No client is allocated until a method actually needs one.
    assert service._http_client is None
    data = await service.dispatch(workflow="outreach-dispatch", payload={"x": 1})

    assert data == {"status": 200, "data": {"ok": True}}
    assert len(created) == 1
    assert created[0].closed == 1
    assert service._http_client is None


async def test_dispatch_closes_owned_client_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_CountingClient] = []

    def _factory(**kwargs: Any) -> _CountingClient:
        client = _CountingClient(fail=True)
        created.append(client)
        return client

    monkeypatch.setattr(settings, "N8N_BASE_URL", _HOST)
    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", _factory)

    service = AIService(_NoOrgSession())
    with pytest.raises(AppError) as exc:
        await service.dispatch(workflow="outreach-dispatch", payload={"x": 1})

    assert exc.value.code == "ai.dispatch_failed"
    assert len(created) == 1
    assert created[0].closed == 1
    assert service._http_client is None


async def test_injected_client_is_not_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.tools.n8n_tool import N8nDispatchTool

    monkeypatch.setattr(settings, "N8N_BASE_URL", _HOST)
    injected = _CountingClient()
    # Patch the tool to use the AIService-provided client directly.
    monkeypatch.setattr(
        N8nDispatchTool,
        "__init__",
        lambda self, client=None, base_url="": setattr(self, "_client", client),
    )
    original_run = N8nDispatchTool.run

    async def run(self: Any, input: dict[str, Any]) -> ToolResult:
        assert self._client is injected
        return ToolResult(ok=True, content={"status": 200, "data": {}})

    monkeypatch.setattr(N8nDispatchTool, "run", run)
    service = AIService(_NoOrgSession(), http_client=injected)  # type: ignore[arg-type]
    await service.dispatch(workflow="outreach-dispatch", payload={})
    assert injected.closed == 0
    assert original_run is not None  # keep a reference for clarity


async def test_aclose_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_CountingClient] = []

    def _factory(**kwargs: Any) -> _CountingClient:
        client = _CountingClient()
        created.append(client)
        return client

    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", _factory)
    service = AIService(_NoOrgSession())
    service._client()
    await service.aclose()
    await service.aclose()
    assert created[0].closed == 1


# -- provider client lifecycle ----------------------------------------------


class _ClosingProvider(ProviderClient):
    def __init__(self) -> None:
        self.closed = 0

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ANN002
        raise AssertionError("not used")

    async def embeddings(self, inputs):  # noqa: ANN001
        raise AssertionError("not used")

    async def aclose(self) -> None:
        self.closed += 1


async def test_llm_service_aclose_closes_provider_once() -> None:
    provider = _ClosingProvider()
    service = LLMService(provider)

    await service.aclose()
    await service.aclose()

    assert provider.closed == 1


async def test_aclose_llm_tolerates_sync_and_missing_close_hooks() -> None:
    class _SyncClose:
        def __init__(self) -> None:
            self.closed = 0

        def aclose(self) -> None:
            self.closed += 1

    sync = _SyncClose()
    await aclose_llm(sync)
    assert sync.closed == 1
    await aclose_llm(None)
    await aclose_llm(object())
    # Test doubles with auto-created MagicMock attributes must not break cleanup.
    await aclose_llm(MagicMock())


# -- brain sanitization ------------------------------------------------------


class _RaisingClient(ProviderClient):
    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-4o-mini"

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ANN002
        raise RuntimeError(f"POST {_HOST} {_SECRET} {_BODY}")

    async def embeddings(self, inputs):  # noqa: ANN001
        raise AssertionError("not used")


async def test_brain_llm_failure_never_leaks_provider_text() -> None:
    brain = Brain(LLMService(_RaisingClient()), ToolRegistry())
    result = await brain.run(goal="g", lead=None, research=None)

    assert result.success is False
    assert result.error == "LLM call failed"
    assert _HOST not in (result.error or "")
    assert _SECRET not in (result.error or "")


class _ExplodingTool:
    name = "explode"
    description = "explodes"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def run(self, input: dict[str, Any]) -> ToolResult:
        raise RuntimeError(f"connect to {_HOST} with {_SECRET}")


class _RawErrorTool:
    name = "raw_error"
    description = "returns raw text"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def run(self, input: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=False, error=f"GET {_HOST} {_BODY} {_SECRET}")


class _ToolCallOnceClient(ProviderClient):
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-4o-mini"

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ANN002
        return ChatResult(
            "",
            LLMUsage("openai", "gpt-4o-mini", 1, 1, 0.0),
            "gpt-4o-mini",
            "tool_calls",
            tool_calls=[ToolCall(id="c1", name=self.tool_name, arguments="{}")],
        )

    async def embeddings(self, inputs):  # noqa: ANN001
        raise AssertionError("not used")


@pytest.mark.parametrize(
    ("tool", "tool_name"),
    [(_ExplodingTool(), "explode"), (_RawErrorTool(), "raw_error")],
)
async def test_brain_tool_failures_never_leak_raw_text(tool: Any, tool_name: str) -> None:
    registry = ToolRegistry()
    registry.register(tool)
    brain = Brain(
        LLMService(_ToolCallOnceClient(tool_name)),
        registry,
        config=BrainConfig(max_steps=1),
    )

    result = await brain.run(goal="g", lead=None, research=None)

    assert result.tool_results is not None
    assert result.tool_results[0].ok is False
    assert result.tool_results[0].error == "tool execution failed"
    assert result.tool_trace
    assert result.tool_trace[0]["error"] == "tool execution failed"
    assert _HOST not in str(result.tool_trace)
    assert _SECRET not in str(result.tool_trace)
    assert _BODY not in str(result.tool_trace)


# -- agent executor closes its provider client ------------------------------


class _FakeLLM:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


def _executor_ctx() -> ExecutorContext:
    return ExecutorContext(
        session=MagicMock(),
        organization_id=ORG_ID,
        run_id=RUN_ID,
        goal="research_lead",
        input={},
        trace_id=TRACE_ID,
    )


async def test_brain_executor_closes_llm_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai.brain import BrainResult

    llm = _FakeLLM()
    executor = ResearchAgentExecutor(http_client=MagicMock())

    async def fake_deps(ctx: Any, client: Any) -> dict[str, Any]:
        return {"llm": llm, "registry": MagicMock(), "memory_context": None}

    monkeypatch.setattr(executor, "_runtime_deps", fake_deps)

    class _FakeBrain:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def run_with_plan(self, **kwargs: Any) -> BrainResult:
            return BrainResult(success=True, response="done")

    monkeypatch.setattr("app.ai.brain.Brain", _FakeBrain)

    result = await executor.execute(_executor_ctx())
    assert result.success is True
    assert llm.closed == 1


async def test_brain_executor_closes_llm_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _FakeLLM()
    executor = ResearchAgentExecutor(http_client=MagicMock())

    async def fake_deps(ctx: Any, client: Any) -> dict[str, Any]:
        return {"llm": llm, "registry": MagicMock(), "memory_context": None}

    monkeypatch.setattr(executor, "_runtime_deps", fake_deps)

    class _FakeBrain:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def run_with_plan(self, **kwargs: Any) -> None:
            raise RuntimeError("unexpected downstream failure")

    monkeypatch.setattr("app.ai.brain.Brain", _FakeBrain)

    with pytest.raises(RuntimeError):
        await executor.execute(_executor_ctx())
    assert llm.closed == 1
