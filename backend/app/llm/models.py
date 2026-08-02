"""Data containers and enums for the LLM layer.

Provider-agnostic: these types are what services and the brain depend on, so a
new provider added later only needs to satisfy :class:`ProviderClient`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class ProviderType(StrEnum):
    """Supported LLM provider identifiers (selectable via config)."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


class MessageRole(StrEnum):
    """Roles in an LLM conversation (mapped to each provider's schema)."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class LLMMessage:
    """A single message in a chat conversation."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass(frozen=True)
class ToolCall:
    """A tool call requested by the model in a message."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolDefinition:
    """Description of a callable tool, translated into each provider's schema."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class LLMUsage:
    """Token + cost accounting for a single completion."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ChatResult:
    """Result of a single (non-streaming) chat completion."""

    text: str
    usage: LLMUsage
    model: str
    finish_reason: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    response_id: str = ""


@dataclass(frozen=True)
class EmbedResult:
    """Result of an embeddings request."""

    vectors: list[list[float]]
    usage: LLMUsage
    model: str


@dataclass(frozen=True)
class OrganizationContext:
    """Carries the org identity used for usage attribution + tool resolution."""

    organization_id: uuid.UUID
    user_id: uuid.UUID | None = None
