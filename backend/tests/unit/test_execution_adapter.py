"""Unit tests: execution adapter selection and dispatch payload shape."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.metrics import get_counter, reset
from app.models.enums import ExecutionEventType
from app.services.builtin_execution import BuiltinExecutionError
from app.services.execution_adapter import (
    BuiltinAdapter,
    ExecutionAdapter,
    N8nAdapter,
    adapter_error_payload,
    get_adapter,
)
from app.services.n8n_client import N8nHttpError

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset()


def test_get_adapter_returns_expected_classes() -> None:
    assert isinstance(get_adapter("n8n"), N8nAdapter)
    assert isinstance(get_adapter("builtin"), BuiltinAdapter)


def test_get_adapter_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        get_adapter("unknown")


def test_adapter_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        ExecutionAdapter()  # type: ignore[abstract]


def test_adapter_error_payload_plain_exception_is_bounded() -> None:
    payload = adapter_error_payload(RuntimeError("boom " * 1000))

    assert payload["error"] == "adapter_error"
    assert len(payload["message"]) <= 2000


def test_adapter_error_payload_empty_exception_uses_class_name() -> None:
    payload = adapter_error_payload(ValueError())

    assert payload["error"] == "adapter_error"
    assert payload["message"] == "ValueError"


def test_adapter_error_payload_n8n_diagnostics() -> None:
    error = N8nHttpError(status_code=500, body="db unavailable", url="https://n8n/x")
    payload = adapter_error_payload(error)

    assert payload["provider"] == "n8n"
    assert payload["status_code"] == 500
    assert payload["body"] == "db unavailable"
    assert payload["error"] == "adapter_error"


async def test_n8n_adapter_posts_to_webhook(monkeypatch) -> None:
    client = MagicMock()
    client.trigger_webhook = AsyncMock(return_value={"output": "ok"})
    monkeypatch.setattr(
        "app.services.execution_adapter.N8nClient", lambda **kwargs: client
    )

    adapter = N8nAdapter()
    result = await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={"lead_id": "x"},
        config={},
        definition={"steps": []},
    )

    assert result == {"output": "ok"}
    assert client.trigger_webhook.await_count == 1
    path, payload = client.trigger_webhook.await_args.args
    assert path == f"/webhook/workflow-{WORKFLOW_ID}"
    assert payload["execution_id"] == str(EXECUTION_ID)
    assert payload["input"] == {"lead_id": "x"}


async def test_n8n_adapter_uses_custom_webhook_path() -> None:
    client = MagicMock()
    client.trigger_webhook = AsyncMock(return_value={})
    adapter = N8nAdapter(client)
    await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={},
        config={"webhook_path": "/webhook/custom"},
    )
    assert client.trigger_webhook.await_args.args[0] == "/webhook/custom"


async def test_builtin_adapter_runs_definition() -> None:
    adapter = BuiltinAdapter()
    result = await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={"lead": {"first_name": "Ada"}},
        config={},
        definition={
            "steps": [
                {"type": "set", "key": "greeting", "value": "Hi {{ input.lead.first_name }}"}
            ],
            "output_key": "greeting",
        },
    )
    assert result == {"greeting": "Hi Ada"}
    assert get_counter("builtin_execution_started").value == 1
    assert get_counter("builtin_execution_succeeded").value == 1
    assert get_counter("builtin_execution_failed").value == 0


async def test_builtin_adapter_empty_definition_returns_context() -> None:
    adapter = BuiltinAdapter()
    result = await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={"lead": {"id": "x"}},
        config={},
    )
    assert result == {"input": {"lead": {"id": "x"}}}


async def test_builtin_adapter_propagates_step_errors_and_counts_failed() -> None:
    adapter = BuiltinAdapter()
    with pytest.raises(BuiltinExecutionError):
        await adapter.execute(
            workflow_id=WORKFLOW_ID,
            execution_id=EXECUTION_ID,
            input_data={},
            config={},
            definition={"steps": [{"type": "copy", "from": "input.nope", "to": "x"}]},
        )
    assert get_counter("builtin_execution_failed").value == 1
    assert get_counter("builtin_execution_succeeded").value == 0


async def test_builtin_adapter_emits_step_events_to_sink() -> None:
    sink = AsyncMock()
    adapter = BuiltinAdapter(event_sink=sink)
    await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={"lead": {"first_name": "Ada"}},
        config={},
        definition={
            "steps": [
                {"type": "set", "key": "a", "value": "1", "id": "s1"},
                {"type": "copy", "from": "input.lead", "to": "lead", "id": "s2"},
            ],
            "output_key": "a",
        },
    )

    sink.assert_awaited_once()
    events = sink.await_args.args[0]
    assert events == [
        (ExecutionEventType.STEP_STARTED, {"step_index": 1, "step_id": "s1"}),
        (ExecutionEventType.STEP_COMPLETED, {"step_index": 1, "step_id": "s1"}),
        (ExecutionEventType.STEP_STARTED, {"step_index": 2, "step_id": "s2"}),
        (ExecutionEventType.STEP_COMPLETED, {"step_index": 2, "step_id": "s2"}),
    ]


async def test_builtin_adapter_flushes_step_events_on_failure() -> None:
    sink = AsyncMock()
    adapter = BuiltinAdapter(event_sink=sink)
    with pytest.raises(BuiltinExecutionError):
        await adapter.execute(
            workflow_id=WORKFLOW_ID,
            execution_id=EXECUTION_ID,
            input_data={},
            config={},
            definition={
                "steps": [
                    {"type": "set", "key": "a", "value": "1", "id": "s1"},
                    {"type": "copy", "from": "input.nope", "to": "x", "id": "s2"},
                ]
            },
        )

    sink.assert_awaited_once()
    events = sink.await_args.args[0]
    assert events[-1] == (ExecutionEventType.STEP_FAILED, {"step_index": 2, "step_id": "s2"})


async def test_builtin_adapter_sink_failure_is_best_effort() -> None:
    async def broken_sink(_events: object) -> None:
        raise RuntimeError("db down")

    adapter = BuiltinAdapter(event_sink=broken_sink)
    result = await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={"lead": {"first_name": "Ada"}},
        config={},
        definition={"steps": [{"type": "set", "key": "a", "value": "1"}]},
    )
    assert result == {"input": {"lead": {"first_name": "Ada"}}, "a": "1"}
