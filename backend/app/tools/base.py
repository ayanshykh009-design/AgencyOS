"""AI Tool Registry — a single, versioned interface for agent tool calls.

A :class:`Tool` is a stateless, async callable with a JSON-schema-ish ``parameters``
descriptor so the AI brain can emit tool-use requests generically. Each tool
maps a JSON input (``dict``) to a :class:`ToolResult`; the caller inspects
``ok``/``is_error``/``content`` to decide next steps.

Tools are registered in :mod:`app.tools.registry` (via the manifest) and looked
up by name. New tools are added by subclassing :class:`Tool` and appending one
line to the manifest — no orchestration code touches a concrete tool directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    """Minimal contract every AI-callable tool must satisfy."""

    name: str
    description: str
    parameters: dict[str, Any]

    async def run(self, input: dict[str, Any]) -> ToolResult: ...


@dataclass(frozen=True)
class ToolResult:
    """Structured result returned by a tool.

    ``ok`` is False on any failure; ``error`` carries a human-readable message and
    ``content`` holds the success payload (a dict, list, or scalar). Exactly one
    of ``content``/``error`` is meaningful per result.
    """

    ok: bool
    content: Any = None
    error: str | None = None
    is_error: bool = False

    def __post_init__(self) -> None:
        if not self.ok and self.is_error is False:
            object.__setattr__(self, "is_error", True)

    @property
    def text(self) -> str:
        """Best-effort string form of the result, for prompts/logs."""
        if not self.ok and self.error:
            return self.error
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        try:
            return json.dumps(self.content, default=str)
        except (TypeError, ValueError):
            return str(self.content)


@dataclass
class ToolInput:
    """A tool invocation parsed from an LLM ``ToolCall``."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """A tool-use request emitted by the brain (mirrors ``LLMMessage``/provider)."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


class ToolError(Exception):
    """Raised by a tool when it fails and wants its error surfaced to the brain."""
