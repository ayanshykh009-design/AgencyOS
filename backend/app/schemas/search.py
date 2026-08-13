"""Search API schemas: unified results across leads, tasks, and notes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.lead import LeadRead
from app.schemas.note import NoteRead
from app.schemas.task import TaskRead


class SearchCounts(BaseModel):
    """Per-type and total result counts."""

    leads: int = 0
    tasks: int = 0
    notes: int = 0
    total: int = 0


class SearchResponse(BaseModel):
    """Combined search results for one organization."""

    query: str = Field(max_length=255)
    leads: list[LeadRead] = Field(default_factory=list)
    tasks: list[TaskRead] = Field(default_factory=list)
    notes: list[NoteRead] = Field(default_factory=list)
    counts: SearchCounts = Field(default_factory=SearchCounts)
