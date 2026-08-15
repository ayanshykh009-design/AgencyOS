"""Organization model — the multi-tenancy root."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.agent_state import AgentState
    from app.models.ai_memory import AiMemory
    from app.models.approval_log import ApprovalLog
    from app.models.approval_request import ApprovalRequest
    from app.models.briefing import Briefing
    from app.models.business_insight import BusinessInsight
    from app.models.credential import Credential
    from app.models.delivery import Delivery
    from app.models.growth_analysis import GrowthAnalysis
    from app.models.growth_forecast import GrowthForecast
    from app.models.growth_health_weight import GrowthHealthWeight
    from app.models.growth_metric import GrowthMetric
    from app.models.growth_recommendation import GrowthRecommendation
    from app.models.growth_scenario import GrowthScenario
    from app.models.intelligence_signal import IntelligenceSignal
    from app.models.knowledge_item import KnowledgeItem
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.workflow import Workflow
    from app.models.workflow_event import WorkflowEvent
    from app.models.workflow_execution import WorkflowExecution
    from app.models.workflow_trigger import WorkflowTrigger


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An agency tenant. All tenant-scoped rows reference ``organization_id``."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        CheckConstraint("length(btrim(name)) > 0", name="chk_organizations_name_not_blank"),
        CheckConstraint("slug ~ '^[a-z0-9][a-z0-9-]*$'", name="chk_organizations_slug_format"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    website: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="organization")
    workflows: Mapped[list[Workflow]] = relationship(back_populates="organization")
    workflow_triggers: Mapped[list[WorkflowTrigger]] = relationship(back_populates="organization")
    workflow_executions: Mapped[list[WorkflowExecution]] = relationship(
        back_populates="organization"
    )
    workflow_events: Mapped[list[WorkflowEvent]] = relationship(back_populates="organization")
    credentials: Mapped[list[Credential]] = relationship(back_populates="organization")
    ai_memories: Mapped[list[AiMemory]] = relationship(back_populates="organization")
    knowledge_items: Mapped[list[KnowledgeItem]] = relationship(back_populates="organization")
    agent_runs: Mapped[list[AgentRun]] = relationship(back_populates="organization")
    agent_states: Mapped[list[AgentState]] = relationship(back_populates="organization")
    notifications: Mapped[list[Notification]] = relationship(back_populates="organization")
    approval_requests: Mapped[list[ApprovalRequest]] = relationship(back_populates="organization")
    approval_logs: Mapped[list[ApprovalLog]] = relationship(back_populates="organization")
    briefings: Mapped[list[Briefing]] = relationship(back_populates="organization")
    growth_metrics: Mapped[list[GrowthMetric]] = relationship(back_populates="organization")
    growth_forecasts: Mapped[list[GrowthForecast]] = relationship(back_populates="organization")
    business_insights: Mapped[list[BusinessInsight]] = relationship(back_populates="organization")
    deliveries: Mapped[list[Delivery]] = relationship(back_populates="organization")
    growth_analyses: Mapped[list[GrowthAnalysis]] = relationship(back_populates="organization")
    growth_health_weights: Mapped[list[GrowthHealthWeight]] = relationship(
        back_populates="organization"
    )
    growth_scenarios: Mapped[list[GrowthScenario]] = relationship(back_populates="organization")
    growth_recommendations: Mapped[list[GrowthRecommendation]] = relationship(
        back_populates="organization"
    )
    intelligence_signals: Mapped[list[IntelligenceSignal]] = relationship(
        back_populates="organization"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Organization id={self.id} slug={self.slug!r}>"
