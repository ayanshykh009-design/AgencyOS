"""Lead assignment engine: rules, round-robin, manual, history.

Strategies (one per org, stored in ``lead_assignment_rules``):
  * MANUAL      — never auto-assign; leads stay unassigned until assigned.
  * ROUND_ROBIN — distribute new/unassigned leads evenly across assignable
    users (optionally restricted to ``target_user_ids``).
  * RULES       — assign only when the lead matches ``conditions`` (e.g. a
    set of lead-source ids); distribution is still round-robin within the
    rule's targets.

Every ownership change appends a ``LeadAssignmentLog`` and an activity
entry, so reassignment history is fully auditable.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.assignment import LeadAssignmentLog, LeadAssignmentRule
from app.models.enums import (
    ActivityEventType,
    AssignmentMethod,
    AssignmentStrategy,
)
from app.models.lead import Lead
from app.models.user import User
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.assignment import AssignmentLogRepository, AssignmentRuleRepository
from app.repositories.lead import LeadRepository
from app.repositories.user import UserRepository
from app.services.base import commit_with_retry, utcnow


class AssignmentService:
    """Owns assignment business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._rules = AssignmentRuleRepository(session)
        self._logs = AssignmentLogRepository(session)
        self._leads = LeadRepository(session)
        self._users = UserRepository(session)
        self._activity = ActivityLogRepository(session)

    # -- rule management ------------------------------------------------

    async def get_rule(self, organization_id: uuid.UUID) -> LeadAssignmentRule | None:
        return await self._rules.get(organization_id)

    async def upsert_rule(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        name: str,
        strategy: AssignmentStrategy,
        enabled: bool,
        target_user_ids: list[uuid.UUID],
    ) -> LeadAssignmentRule:
        targets = await self._users.list_assignable(
            organization_id, user_ids=target_user_ids or None
        )
        if target_user_ids and len(targets) != len(set(target_user_ids)):
            raise AppError(
                code="assignment.invalid_targets",
                message="One or more assignee targets are invalid or inactive",
                status_code=400,
            )
        rule = await self._rules.get(organization_id)
        if rule is None:
            rule = LeadAssignmentRule(organization_id=organization_id)
            self._rules.add(rule)
        rule.name = name
        rule.strategy = strategy
        rule.enabled = enabled
        rule.target_user_ids = [str(uid) for uid in target_user_ids]
        await commit_with_retry(self._session)
        return rule

    # -- assignment -----------------------------------------------------

    async def auto_assign(self, organization_id: uuid.UUID, lead: Lead) -> None:
        """Apply the org's rule to a lead without an owner (no-op otherwise)."""
        if lead.owner_user_id is not None:
            return
        rule = await self._rules.get(organization_id)
        if rule is None or not rule.enabled or rule.strategy is AssignmentStrategy.MANUAL:
            return
        if rule.strategy is AssignmentStrategy.RULES and not self._matches_conditions(rule, lead):
            return
        to_user = await self._next_candidate(organization_id, rule)
        if to_user is None:
            return
        lead.owner_user_id = to_user.id
        self._log_assignment(
            organization_id,
            lead_id=lead.id,
            from_user_id=None,
            to_user_id=to_user.id,
            method=AssignmentMethod(rule.strategy.value),
            assigned_by_user_id=None,
            reason="auto-assignment",
        )
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                lead_id=lead.id,
                event_type=ActivityEventType.LEAD_ASSIGNED,
                entity_type="lead",
                entity_id=lead.id,
                description=f"Auto-assigned to {to_user.full_name}",
                metadata_={
                    "to_user_id": str(to_user.id),
                    "strategy": rule.strategy.value,
                },
                occurred_at=utcnow(),
            )
        )

    async def assign(
        self,
        organization_id: uuid.UUID,
        actor: User,
        lead: Lead,
        *,
        to_user_id: uuid.UUID | None,
        reason: str | None = None,
    ) -> Lead:
        """Manually (re)assign a lead or clear its owner."""
        if to_user_id is not None:
            candidates = await self._users.list_assignable(organization_id, user_ids=[to_user_id])
            if not candidates:
                raise AppError(
                    code="assignment.invalid_target",
                    message="Target user is not an assignable active member",
                    status_code=400,
                )
        if lead.owner_user_id == to_user_id:
            return lead
        self._log_assignment(
            organization_id,
            lead_id=lead.id,
            from_user_id=lead.owner_user_id,
            to_user_id=to_user_id,
            method=AssignmentMethod.MANUAL,
            assigned_by_user_id=actor.id,
            reason=reason,
        )
        lead.owner_user_id = to_user_id
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                lead_id=lead.id,
                event_type=ActivityEventType.LEAD_ASSIGNED,
                entity_type="lead",
                entity_id=lead.id,
                description=("Reassigned lead" if to_user_id is not None else "Unassigned lead"),
                metadata_={
                    "to_user_id": str(to_user_id) if to_user_id else None,
                    "method": "manual",
                },
                occurred_at=utcnow(),
            )
        )
        return lead

    async def assign_unassigned(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 500,
    ) -> int:
        """Round-robin sweep: assign every unassigned lead (e.g. post-import)."""
        rule = await self._rules.get(organization_id)
        if rule is None or not rule.enabled or rule.strategy is AssignmentStrategy.MANUAL:
            return 0
        candidates = await self._candidates(organization_id, rule)
        if not candidates:
            return 0
        leads = await self._leads.list_unassigned(organization_id, limit=limit)
        count = 0
        for lead in leads:
            if rule.strategy is AssignmentStrategy.RULES and not self._matches_conditions(
                rule, lead
            ):
                continue
            to_user = self._next_from_candidates(rule, candidates)
            if to_user is None:  # pragma: no cover - candidates checked above
                continue
            lead.owner_user_id = to_user.id
            self._log_assignment(
                organization_id,
                lead_id=lead.id,
                from_user_id=None,
                to_user_id=to_user.id,
                method=AssignmentMethod.BULK,
                assigned_by_user_id=None,
                reason="bulk assignment sweep",
            )
            count += 1
        if count:
            await commit_with_retry(self._session)
        return count

    async def history(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LeadAssignmentLog]:
        return await self._logs.list(organization_id, lead_id=lead_id, limit=limit, offset=offset)

    # -- helpers --------------------------------------------------------

    async def _next_candidate(
        self, organization_id: uuid.UUID, rule: LeadAssignmentRule
    ) -> User | None:
        candidates = await self._candidates(organization_id, rule)
        return self._next_from_candidates(rule, candidates)

    async def _candidates(self, organization_id: uuid.UUID, rule: LeadAssignmentRule) -> list[User]:
        return await self._users.list_assignable(
            organization_id,
            user_ids=[uuid.UUID(str(uid)) for uid in (rule.target_user_ids or [])] or None,
        )

    @staticmethod
    def _next_from_candidates(rule: LeadAssignmentRule, candidates: list[User]) -> User | None:
        if not candidates:
            return None
        idx = (rule.last_assigned_index + 1) % len(candidates)
        rule.last_assigned_index = idx
        return candidates[idx]

    @staticmethod
    def _matches_conditions(rule: LeadAssignmentRule, lead: Lead) -> bool:
        conditions: dict[str, Any] = rule.conditions or {}
        source_ids = conditions.get("source_ids")
        if source_ids:
            return str(lead.lead_source_id) in [str(s) for s in source_ids]
        return False

    def _log_assignment(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID,
        from_user_id: uuid.UUID | None,
        to_user_id: uuid.UUID | None,
        method: AssignmentMethod,
        assigned_by_user_id: uuid.UUID | None,
        reason: str | None,
    ) -> None:
        self._logs.add(
            LeadAssignmentLog(
                organization_id=organization_id,
                lead_id=lead_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                method=method,
                assigned_by_user_id=assigned_by_user_id,
                reason=reason,
            )
        )
