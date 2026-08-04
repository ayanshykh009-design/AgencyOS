"""Workflow execution adapters — strategy pattern for dispatching executions.

Phase 5A ships two adapters:
- N8nAdapter: dispatches to an n8n workflow via webhook.
- BuiltinAdapter: placeholder for future in-process execution.

The adapter is selected based on the workflow's ``execution_mode`` field.
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.services.n8n_client import N8nClient

logger = logging.getLogger("agencyos.automation.adapter")


class ExecutionAdapter(ABC):
    """Base class for workflow execution adapters."""

    @abstractmethod
    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the workflow and return the result payload."""
        ...


class N8nAdapter(ExecutionAdapter):
    """Dispatch workflow execution to an n8n instance via webhook."""

    def __init__(self, client: N8nClient | None = None) -> None:
        self._client = client or N8nClient()

    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
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
    """In-process workflow execution (Phase 5B+ placeholder)."""

    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        logger.warning(
            "BuiltinAdapter.execute called for workflow %s — not yet implemented",
            workflow_id,
        )
        return {"status": "skipped", "reason": "builtin execution not yet supported"}


def get_adapter(execution_mode: str) -> ExecutionAdapter:
    """Return the appropriate adapter for the given execution mode."""
    adapters: dict[str, type[ExecutionAdapter]] = {
        "n8n": N8nAdapter,
        "builtin": BuiltinAdapter,
    }
    adapter_cls = adapters.get(execution_mode)
    if adapter_cls is None:
        raise ValueError(f"Unknown execution mode: {execution_mode}")
    return adapter_cls()
