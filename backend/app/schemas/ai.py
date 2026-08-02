"""AI automation API schemas (brain run + tool manifest + dispatch)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ToolManifestEntry(BaseModel):
    """Static description of a callable AI tool (name/description/parameters)."""

    name: str
    description: str
    parameters: dict[str, Any]


class BrainRunRequest(BaseModel):
    """Payload to execute the AI brain for a single goal on a lead."""

    goal: str = Field(min_length=1, max_length=100)
    lead_id: UUID
    channel: Literal["email", "linkedin"] | None = None
    recent_messages: list[dict[str, Any]] | None = None


class ToolCallRead(BaseModel):
    """A tool call the brain executed."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultRead(BaseModel):
    """Outcome of a single tool execution."""

    ok: bool
    error: str | None = None
    text: str = ""


class BrainRunResponse(BaseModel):
    """Outcome of a brain run (mirrors ``BrainResult``)."""

    success: bool
    response: str | None = None
    error: str | None = None
    steps_taken: int = 0
    tool_calls: list[ToolCallRead] = Field(default_factory=list)
    tool_results: list[ToolResultRead] = Field(default_factory=list)


class DispatchRequest(BaseModel):
    """Payload to hand a draft to the n8n automation platform."""

    workflow: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class DispatchResponse(BaseModel):
    """Result of an n8n dispatch."""

    workflow: str
    status: int
    data: dict[str, Any] = Field(default_factory=dict)
