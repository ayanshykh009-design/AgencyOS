"""Centralized enum definitions mirroring the PostgreSQL enum types.

Source of truth for the label set: ``database/migrations/enums/`` (SQL).
Keep the values here in sync with the DDL — they are used by both the ORM
models and the Pydantic schemas.
"""
from enum import StrEnum


class UserRole(StrEnum):
    """Access level of a user within their organization.

    Ordered from least to most privileged: VIEWER < MEMBER ~ SALES_AGENT <
    MANAGER < ADMIN < OWNER. Keep this ordering in sync with the role
    hierarchy in ``app/core/permissions.py``.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    SALES_AGENT = "sales_agent"
    VIEWER = "viewer"


class InviteStatus(StrEnum):
    """Lifecycle of a team invite."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


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
    USER_INVITED = "user_invited"
    INVITE_ACCEPTED = "invite_accepted"
    INVITE_REVOKED = "invite_revoked"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_STATUS_CHANGED = "user_status_changed"
    LEAD_ASSIGNED = "lead_assigned"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_COMPLETED = "task_completed"
    TASK_DELETED = "task_deleted"
    NOTE_CREATED = "note_created"
    NOTE_UPDATED = "note_updated"
    NOTE_DELETED = "note_deleted"
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_UPDATED = "workflow_updated"
    WORKFLOW_ACTIVATED = "workflow_activated"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_ARCHIVED = "workflow_archived"
    WORKFLOW_DELETED = "workflow_deleted"
    EXECUTION_QUEUED = "execution_queued"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_RETRIED = "execution_retried"
    EXECUTION_CANCELLED = "execution_cancelled"
    CREDENTIAL_CREATED = "credential_created"
    CREDENTIAL_UPDATED = "credential_updated"
    CREDENTIAL_DELETED = "credential_deleted"
    TRIGGER_CREATED = "trigger_created"
    TRIGGER_UPDATED = "trigger_updated"
    TRIGGER_DELETED = "trigger_deleted"


class ConversationSender(StrEnum):
    """Who authored a conversation message."""

    LEAD = "lead"
    AGENT = "agent"
    SYSTEM = "system"


class StageLifecycle(StrEnum):
    """Coarse bucket of a pipeline stage: open (active), won, or lost."""

    OPEN = "open"
    WON = "won"
    LOST = "lost"


class AssignmentStrategy(StrEnum):
    """How leads are auto-assigned to team members."""

    MANUAL = "manual"
    ROUND_ROBIN = "round_robin"
    RULES = "rules"


class AssignmentMethod(StrEnum):
    """How a specific lead assignment was made."""

    MANUAL = "manual"
    ROUND_ROBIN = "round_robin"
    RULES = "rules"
    BULK = "bulk"
    UNASSIGNED = "unassigned"


class TaskStatus(StrEnum):
    """Lifecycle of a task."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    """Urgency of a task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RecurrenceFrequency(StrEnum):
    """Cadence for repeating tasks (advanced on completion)."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class WorkflowStatus(StrEnum):
    """Lifecycle of a workflow definition."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class WorkflowTriggerType(StrEnum):
    """How a workflow is triggered."""

    MANUAL = "manual"
    EVENT = "event"
    SCHEDULE = "schedule"


class ExecutionStatus(StrEnum):
    """Lifecycle of a workflow execution."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CredentialType(StrEnum):
    """Type of stored credential."""

    N8N_API_KEY = "n8n_api_key"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
