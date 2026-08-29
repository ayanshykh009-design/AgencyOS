"""Founder action proposal model — every assistant action is gated by approval."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FounderActionType, FounderProposalStatus

if TYPE_CHECKING:
    from app.models.approval_request import ApprovalRequest
    from app.models.founder_conversation import FounderConversation


class FounderActionProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A founder-initiated action awaiting approval before execution.

    The founder assistant never mutates org data directly. Any action it wants
    to take is recorded here and linked to a shared :class:`ApprovalRequest`;
    only once that request is approved does :meth:`FounderActionService.apply`
    execute the action.
    """

    __tablename__ = "founder_action_proposals"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) > 0",
            name="chk_founder_action_proposals_title_not_blank",
        ),
        CheckConstraint(
            "jsonb_array_length(payload) <= 100",
            name="chk_founder_action_proposals_payload_size",
        ),
        Index("idx_founder_action_proposals_org_status", "organization_id", "proposal_status"),
        Index("idx_founder_action_proposals_org_created", "organization_id", "created_at"),
        Index(
            "idx_founder_action_proposals_approval_request",
            "approval_request_id",
            postgresql_where="approval_request_id IS NOT NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("founder_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    proposal_status: Mapped[FounderProposalStatus] = mapped_column(
        Enum(
            FounderProposalStatus,
            name="founder_proposal_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=FounderProposalStatus.PROPOSED,
        nullable=False,
    )
    action_type: Mapped[FounderActionType] = mapped_column(
        Enum(
            FounderActionType,
            name="founder_action_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    execution_reference: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    conversation: Mapped[FounderConversation | None] = relationship(
        back_populates="action_proposals"
    )
    approval_request: Mapped[ApprovalRequest | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FounderActionProposal id={self.id} status={self.proposal_status}>"
