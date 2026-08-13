"""Shared data types for the M7 deterministic growth analytics engines.

Engines are pure functions over a :class:`GrowthContext` (no DB access). The
:class:`GrowthContextRepository` assembles one per organization from the
repositories so every engine can run on a consistent snapshot.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class StagePoint:
    """A pipeline stage as seen by the analytics engines."""

    id: uuid.UUID
    name: str
    position: int
    lifecycle: str  # 'open' | 'won' | 'lost'


@dataclass(frozen=True)
class LeadPoint:
    """A lead row reduced to the fields analytics engines need."""

    id: uuid.UUID
    status: str
    stage_id: uuid.UUID | None
    deal_value: Decimal | None
    won_at: datetime | None
    lost_at: datetime | None
    created_at: datetime | None
    owner_user_id: uuid.UUID | None
    name: str = ""


@dataclass(frozen=True)
class MetricPoint:
    """A growth_metrics row reduced for the engines."""

    metric_type: str
    period_start: datetime
    period_end: datetime
    value: Decimal


@dataclass(frozen=True)
class AttemptPoint:
    """An outreach attempt reduced for the engines."""

    status: str
    channel: str
    created_at: datetime


@dataclass(frozen=True)
class TaskPoint:
    """A task row reduced for the engines."""

    status: str
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class ActivityPoint:
    """An activity log event reduced for the engines."""

    event_type: str
    created_at: datetime


@dataclass(frozen=True)
class HealthWeightPoint:
    """A growth_health_weights row reduced for the engines."""

    dimension: str
    weight: float
    position: int


@dataclass
class GrowthContext:
    """The full, org-scoped analytics snapshot fed to every engine."""

    organization_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    stages: list[StagePoint] = field(default_factory=list)
    leads: list[LeadPoint] = field(default_factory=list)
    metrics: list[MetricPoint] = field(default_factory=list)
    attempts: list[AttemptPoint] = field(default_factory=list)
    tasks: list[TaskPoint] = field(default_factory=list)
    activity: list[ActivityPoint] = field(default_factory=list)
    health_weights: list[HealthWeightPoint] = field(default_factory=list)
