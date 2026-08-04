"""Unit tests: execution adapter selection and dispatch payload shape."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.execution_adapter import (
    BuiltinAdapter,
    ExecutionAdapter,
    N8nAdapter,
    get_adapter,
)

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")


def test_get_adapter_returns_expected_classes() -> None:
    assert isinstance(get_adapter("n8n"), N8nAdapter)
    assert isinstance(get_adapter("builtin"), BuiltinAdapter)


def test_get_adapter_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        get_adapter("unknown")


def test_adapter_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        ExecutionAdapter()  # type: ignore[abstract]


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


async def test_builtin_adapter_returns_skipped() -> None:
    adapter = BuiltinAdapter()
    result = await adapter.execute(
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        input_data={},
        config={},
    )
    assert result == {"status": "skipped", "reason": "builtin execution not yet supported"}
