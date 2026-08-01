"""Centralized enum definitions mirroring the PostgreSQL enum types.

Source of truth for the label set: ``database/migrations/enums/`` (SQL).
Keep the values here in sync with the DDL — they are used by both the ORM
models and the Pydantic schemas.
"""
from enum import StrEnum


class UserRole(StrEnum):
    """Access level of a user within their organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class LeadStatus(StrEnum):
    """Lifecycle stage of a lead."""

    NEW = "new"
    RESEARCHING = "researching"
    CONTACTED = "contacted"
    MEETING_BOOKED = "meeting_booked"
    PROPOSAL_SENT = "proposal_sent"
    WON = "won"
    LOST = "lost"


class OutreachChannel(StrEnum):
    """Channel used by an outreach message or attempt."""

    EMAIL = "email"
    WHATSAPP = "whatsapp"
    CONTACT_FORM = "contact_form"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"


class OutreachStatus(StrEnum):
    """Lifecycle of a single outreach message / follow-up."""

    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"
    MANUALLY_SENT = "manually_sent"
    REPLIED = "replied"


class ImportStatus(StrEnum):
    """Lifecycle of a CSV import job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivityEventType(StrEnum):
    """Closed set of business events recorded in ``activity_logs``."""

    LEAD_IMPORTED = "lead_imported"
    RESEARCH_COMPLETED = "research_completed"
    SCORE_GENERATED = "score_generated"
    EMAIL_SENT = "email_sent"
    WHATSAPP_SENT = "whatsapp_sent"
    MANUAL_MESSAGE_COMPLETED = "manual_message_completed"
    REPLY_RECEIVED = "reply_received"
    MEETING_BOOKED = "meeting_booked"
    PROPOSAL_SENT = "proposal_sent"
    LEAD_WON = "lead_won"
    LEAD_LOST = "lead_lost"


class ConversationSender(StrEnum):
    """Who authored a conversation message."""

    LEAD = "lead"
    AGENT = "agent"
    SYSTEM = "system"
