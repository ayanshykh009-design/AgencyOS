"""Founder context builder — assembles the grounded snapshot the assistant uses.

Every founder answer is grounded in this snapshot. The builder reads from the
existing repositories (no new data stores) and degrades gracefully: a failing
sub-source is logged and skipped rather than breaking the whole answer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalRequestStatus, FounderProposalStatus
from app.repositories.approval_request import ApprovalRequestRepository
from app.repositories.founder_action_proposal import FounderActionProposalRepository
from app.repositories.lead import LeadRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.task import TaskRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository
from app.services.base import utcnow
from app.services.growth_analytics_service import GrowthAnalyticsService

logger = logging.getLogger("agencyos.founder.context")


@dataclass
class FounderContext:
    """An immutable, serializable snapshot of the org for one founder turn."""

    organization_id: uuid.UUID
    organization_name: str | None
    as_of: datetime
    leads: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    executions: list[dict] = field(default_factory=list)
    pending_approvals: list[dict] = field(default_factory=list)
    open_proposals: list[dict] = field(default_factory=list)
    kpi: dict | None = None

    def to_dict(self) -> dict:
        """Return a JSON-safe snapshot (stored on assistant messages)."""
        return {
            "organization_id": str(self.organization_id),
            "organization_name": self.organization_name,
            "as_of": self.as_of.isoformat(),
            "leads": self.leads,
            "tasks": self.tasks,
            "executions": self.executions,
            "pending_approvals": self.pending_approvals,
            "open_proposals": self.open_proposals,
            "kpi": self.kpi,
        }

    def summary(self) -> str:
        """A compact, human-readable block the system prompt can embed."""
        lines: list[str] = []
        org = self.organization_name or str(self.organization_id)
        lines.append(f"Organization: {org}")
        lines.append(f"As of: {self.as_of.isoformat()}")

        if self.kpi:
            lines.append("KPI snapshot:")
            for key, value in self.kpi.items():
                lines.append(f"  - {key}: {value}")

        if self.leads:
            lines.append(f"Recent leads ({len(self.leads)}):")
            for lead in self.leads[:5]:
                lines.append(
                    f"  - {lead.get('name', 'unknown')} "
                    f"({lead.get('company', '-')}) [{lead.get('status', '-')}]"
                )

        if self.tasks:
            lines.append(f"Open tasks ({len(self.tasks)}):")
            for task in self.tasks[:5]:
                lines.append(f"  - {task.get('title')} [{task.get('status', '-')}]")

        if self.executions:
            lines.append(f"Recent workflow executions ({len(self.executions)}):")
            for exec_ in self.executions[:5]:
                lines.append(f"  - {exec_.get('status', '-')} ({exec_.get('id')})")

        if self.pending_approvals:
            lines.append(f"Pending approvals ({len(self.pending_approvals)}):")
            for ap in self.pending_approvals[:5]:
                lines.append(f"  - {ap.get('title')}")

        if self.open_proposals:
            lines.append(f"Open founder proposals ({len(self.open_proposals)}):")
            for p in self.open_proposals[:5]:
                lines.append(f"  - [{p.get('action_type')}] {p.get('title')}")

        return "\n".join(lines)


class FounderContextBuilder:
    """Builds a :class:`FounderContext` from existing org-scoped repositories."""

    def __init__(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        *,
        include_kpi: bool = True,
        now: datetime | None = None,
    ) -> None:
        self._session = session
        self._organization_id = organization_id
        self._include_kpi = include_kpi
        self._now = now or utcnow()

    async def build(self) -> FounderContext:
        org_name = await self._safe(self._org_name, None)
        leads = await self._safe(self._recent_leads, [])
        tasks = await self._safe(self._open_tasks, [])
        executions = await self._safe(self._recent_executions, [])
        approvals = await self._safe(self._pending_approvals, [])
        proposals = await self._safe(self._open_proposals, [])
        kpi = await self._safe(self._kpi, None) if self._include_kpi else None
        return FounderContext(
            organization_id=self._organization_id,
            organization_name=org_name,
            as_of=self._now,
            leads=leads,
            tasks=tasks,
            executions=executions,
            pending_approvals=approvals,
            open_proposals=proposals,
            kpi=kpi,
        )

    async def _safe(self, coro, default):
        try:
            return await coro()
        except Exception:  # noqa: BLE001 - best-effort context assembly
            logger.exception("founder context sub-source %s failed", coro.__name__)
            return default

    async def _org_name(self) -> str | None:
        org = await OrganizationRepository(self._session).get(self._organization_id)
        return getattr(org, "name", None) if org is not None else None

    async def _recent_leads(self) -> list[dict]:
        leads = await LeadRepository(self._session).search(
            self._organization_id, limit=5
        )
        return [
            {
                "id": str(lead.id),
                "name": (
                    f"{getattr(lead, 'first_name', '')} "
                    f"{getattr(lead, 'last_name', '')}"
                ).strip()
                or "unknown",
                "company": getattr(lead, "company", None),
                "status": getattr(lead, "status", None),
                "score": getattr(lead, "score", None),
            }
            for lead in leads
        ]

    async def _open_tasks(self) -> list[dict]:
        from app.models.enums import TaskStatus

        tasks = await TaskRepository(self._session).list_tasks(
            self._organization_id,
            status=TaskStatus.TODO,
            limit=5,
        )
        return [
            {
                "id": str(task.id),
                "title": task.title,
                "status": task.status.value if task.status else None,
                "priority": task.priority.value if task.priority else None,
                "due_at": task.due_at.isoformat() if task.due_at else None,
            }
            for task in tasks
        ]

    async def _recent_executions(self) -> list[dict]:
        executions = await WorkflowExecutionRepository(self._session).list(
            self._organization_id, limit=5
        )
        return [
            {
                "id": str(exec_.id),
                "workflow_id": str(exec_.workflow_id) if exec_.workflow_id else None,
                "status": exec_.status.value if exec_.status else None,
                "created_at": exec_.created_at.isoformat() if exec_.created_at else None,
            }
            for exec_ in executions
        ]

    async def _pending_approvals(self) -> list[dict]:
        requests = await ApprovalRequestRepository(self._session).list_by_status(
            self._organization_id, status=ApprovalRequestStatus.PENDING, limit=10
        )
        return [
            {
                "id": str(req.id),
                "title": req.title,
                "expires_at": req.expires_at.isoformat() if req.expires_at else None,
            }
            for req in requests
        ]

    async def _open_proposals(self) -> list[dict]:
        proposals = await FounderActionProposalRepository(self._session).list_by_status(
            self._organization_id, status=FounderProposalStatus.PROPOSED, limit=10
        )
        return [
            {
                "id": str(p.id),
                "title": p.title,
                "action_type": p.action_type.value if p.action_type else None,
            }
            for p in proposals
        ]

    async def _kpi(self) -> dict | None:
        from app.models.enums import GrowthAnalysisType

        try:
            service = GrowthAnalyticsService(self._session)
            period_end = datetime.utcnow()
            period_start = period_end - timedelta(days=30)
            result = await service.preview_analysis(
                self._organization_id,
                analysis_type=GrowthAnalysisType.KPIS,
                period_start=period_start,
                period_end=period_end,
            )
        except Exception:  # noqa: BLE001 - KPI is supplementary
            logger.exception("founder kpi snapshot failed")
            return None
        if not isinstance(result, dict):
            return None
        # Keep the snapshot small and JSON-safe.
        return {
            key: result[key]
            for key in (
                "total_leads",
                "active_leads",
                "pipeline_value",
                "revenue",
                "conversion_rate",
                "open_tasks",
            )
            if key in result
        }
