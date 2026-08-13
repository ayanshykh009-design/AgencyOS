"""Workflow execution adapters — strategy pattern for dispatching executions.

Phase 5A ships two adapters:
- N8nAdapter: dispatches to an n8n workflow via webhook.
- BuiltinAdapter: runs a declarative step definition in-process (Phase 5B).

The adapter is selected based on the workflow's ``execution_mode`` field.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.metrics import get_counter
from app.models.enums import ExecutionEventType
from app.services.builtin_execution import (
    BuiltinExecutionError,
    run_builtin_definition,
)
from app.services.n8n_client import N8nClient, N8nHttpError

logger = logging.getLogger("agencyos.automation.adapter")

# Cap on the serialized size of a stored adapter error (defense in depth on
# top of the service-level payload cap).
_MAX_ERROR_BYTES = 65536

# Async sink that persists a batch of timeline events (see
# ``ExecutionEventService.record_many``). The worker wires it; adapters treat
# it as best-effort and never let a sink failure fail an execution.
EventSink = Callable[[list[tuple[ExecutionEventType, dict[str, Any]]]], Awaitable[None]]


def adapter_error_payload(exc: Exception) -> dict[str, Any]:
    """Build a bounded, sanitized error payload from an adapter exception.

    Never includes a stack trace or upstream credentials: n8n diagnostics are
    attached only when the exception carries a sanitized body, and free-form
    messages are truncated.
    """
    if isinstance(exc, N8nHttpError):
        payload: dict[str, Any] = {
            "error": "adapter_error",
            "message": str(exc),
            **exc.diagnostics,
        }
    else:
        message = str(exc) or exc.__class__.__name__
        payload = {
            "error": "adapter_error",
            "message": message[:2000],
        }
    serialized = len(str(payload).encode("utf-8"))
    if serialized > _MAX_ERROR_BYTES:
        payload["message"] = "adapter error (message truncated)"
    return payload


class ExecutionAdapter(ABC):
    """Base class for workflow execution adapters."""

    def __init__(self, event_sink: EventSink | None = None) -> None:
        self._event_sink = event_sink

    @abstractmethod
    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the workflow and return the result payload."""
        ...


class N8nAdapter(ExecutionAdapter):
    """Dispatch workflow execution to an n8n instance via webhook."""

    def __init__(
        self,
        client: N8nClient | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        super().__init__(event_sink=event_sink)
        self._client = client or N8nClient()

    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        webhook_path = config.get("webhook_path", f"/webhook/workflow-{workflow_id}")
        payload = {
            "execution_id": str(execution_id),
            "workflow_id": str(workflow_id),
            "input": input_data,
        }
        logger.info("Dispatching to n8n: %s", webhook_path)
        result = await self._client.trigger_webhook(webhook_path, payload)
        logger.info("n8n response for execution %s: %s", execution_id, result)
        return result


class BuiltinAdapter(ExecutionAdapter):
    """In-process execution via the declarative step engine.

    Runs ``definition`` against ``input_data`` deterministically and returns
    the produced result payload. Failures surface as exceptions so the
    execution worker's existing retry/timeout machinery applies unchanged;
    the engine itself leaves no state behind, keeping retries restart-safe.

    When an ``event_sink`` is wired (by the worker) each executed step emits
    ``step_started``/``step_completed``/``step_failed`` timeline events. The
    sink is best-effort: a sink failure is logged and never fails the run.
    """

    def __init__(self, event_sink: EventSink | None = None) -> None:
        super().__init__(event_sink=event_sink)

    async def _flush_step_events(
        self,
        events: list[tuple[ExecutionEventType, dict[str, Any]]],
    ) -> None:
        if self._event_sink is None or not events:
            return
        try:
            await self._event_sink(events)
        except Exception:  # pragma: no cover - best-effort contract
            logger.exception("failed to persist builtin step timeline events")

    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definition = definition or {}
        get_counter(
            "builtin_execution_started",
            description="Builtin workflow executions started",
        ).add()
        logger.info(
            "builtin execution start: execution=%s workflow=%s",
            execution_id,
            workflow_id,
        )
        pending: list[tuple[ExecutionEventType, dict[str, Any]]] = []

        def _on_step(event: str, index: int, step_id: str | None) -> None:
            event_type = {
                "started": ExecutionEventType.STEP_STARTED,
                "completed": ExecutionEventType.STEP_COMPLETED,
                "failed": ExecutionEventType.STEP_FAILED,
            }.get(event)
            if event_type is not None:
                pending.append((event_type, {"step_index": index, "step_id": step_id}))

        try:
            result = run_builtin_definition(definition, input_data, on_step=_on_step)
        except BuiltinExecutionError as exc:
            get_counter(
                "builtin_execution_failed",
                description="Builtin workflow executions that failed",
            ).add()
            logger.warning(
                "builtin execution failed: execution=%s error=%s",
                execution_id,
                exc,
            )
            await self._flush_step_events(pending)
            raise
        except Exception:
            get_counter(
                "builtin_execution_failed",
                description="Builtin workflow executions that failed",
            ).add()
            logger.exception("builtin execution errored: execution=%s", execution_id)
            await self._flush_step_events(pending)
            raise
        get_counter(
            "builtin_execution_succeeded",
            description="Builtin workflow executions that succeeded",
        ).add()
        logger.info(
            "builtin execution success: execution=%s workflow=%s",
            execution_id,
            workflow_id,
        )
        await self._flush_step_events(pending)
        return result


def get_adapter(execution_mode: str, event_sink: EventSink | None = None) -> ExecutionAdapter:
    """Return the appropriate adapter for the given execution mode."""
    adapters: dict[str, type[ExecutionAdapter]] = {
        "n8n": N8nAdapter,
        "builtin": BuiltinAdapter,
    }
    adapter_cls = adapters.get(execution_mode)
    if adapter_cls is None:
        raise ValueError(f"Unknown execution mode: {execution_mode}")
    return adapter_cls(event_sink=event_sink)
