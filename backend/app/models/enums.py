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
    AUTOMATION_PAUSED = "automation_paused"
    AUTOMATION_RESUMED = "automation_resumed"


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


class ExecutionEventType(StrEnum):
    """Closed set of append-only technical timeline labels.

    Mirrors ``public.execution_event_type`` (database/migrations/enums/).
    ``queued``/``started``/``retrying``/``succeeded``/``failed``/
    ``cancelled``/``timed_out`` are the state-machine transitions; the rest
    are worker/adapter/step instrumentation points.
    """

    QUEUED = "queued"
    STARTED = "started"
    ADAPTER_DISPATCHED = "adapter_dispatched"
    ADAPTER_RETURNED = "adapter_returned"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    TIMEOUT_GUARD = "timeout_guard"


class CredentialType(StrEnum):
    """Type of stored credential."""

    N8N_API_KEY = "n8n_api_key"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"


class MemoryType(StrEnum):
    """Persistence class of an AI memory row.

    ``working`` memories are ephemeral (pruned after ``MEMORY_WORKING_TTL_DAYS``);
    ``long_term`` memories are durable and never auto-deleted.
    """

    WORKING = "working"
    LONG_TERM = "long_term"


class MemoryScope(StrEnum):
    """Where an AI memory came from / applies to."""

    CONVERSATION = "conversation"
    RESEARCH = "research"
    WORKFLOW = "workflow"
    SHARED_CONTEXT = "shared_context"
    KNOWLEDGE = "knowledge"
    MANUAL = "manual"


class AgentRunStatus(StrEnum):
    """Lifecycle of a single agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunTrigger(StrEnum):
    """How an agent run was started."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    WORKFLOW = "workflow"
    EVENT = "event"


class AgentStateStatus(StrEnum):
    """Lifecycle of an agent definition."""

    ACTIVE = "active"
    PAUSED = "paused"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class AgentHealth(StrEnum):
    """Rolling health signal for an agent."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class NotificationType(StrEnum):
    """Category of an in-app notification."""

    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESULT = "approval_result"
    WORKFLOW_EVENT = "workflow_event"
    AGENT_EVENT = "agent_event"
    SYSTEM = "system"
    BRIEFING = "briefing"
    INSIGHT = "insight"


class ApprovalRequestStatus(StrEnum):
    """Lifecycle of a gated approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalLogAction(StrEnum):
    """Action recorded in the immutable approval audit log."""

    REQUESTED = "requested"
    NOTIFIED = "notified"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BriefingType(StrEnum):
    """Cadence of a generated founder briefing."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MANUAL = "manual"


class InsightType(StrEnum):
    """Category of a generated business insight."""

    OPPORTUNITY = "opportunity"
    RISK = "risk"
    TREND = "trend"
    ANOMALY = "anomaly"
    RECOMMENDATION = "recommendation"


class InsightSeverity(StrEnum):
    """Urgency of a business insight."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InsightStatus(StrEnum):
    """Triage lifecycle of a business insight."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class DeliveryChannel(StrEnum):
    """Transport a delivery is sent over.

    M6 ships the ``dashboard`` provider only; ``email``/``whatsapp``/``push``
    are declared for the frozen M1 surface and fail closed until their
    providers land in later milestones.
    """

    DASHBOARD = "dashboard"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    PUSH = "push"


class DeliveryStatus(StrEnum):
    """Lifecycle of a single delivery (outbox state machine).

    Mirrors ``public.delivery_status``. The state machine is
    ``queued -> processing -> delivered/failed/cancelled`` with
    ``processing -> retrying -> queued/cancelled`` for scheduled retries;
    ``failed``/``cancelled`` re-enter ``queued`` only through an explicit
    manual retry. Transitions are owned by the delivery worker and its
    guarded transitions, not by callers.
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    RETRYING = "retrying"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeliveryEventType(StrEnum):
    """Closed set of append-only delivery timeline labels.

    Mirrors ``public.delivery_event_type`` (database/migrations/enums/13_delivery.sql).
    ``queued``/``claimed``/``delivered``/``retrying``/``failed``/``cancelled``
    are the state-machine transitions; ``provider_dispatched``/
    ``provider_returned`` bracket a provider attempt; ``timed_out`` marks an
    attempt that exceeded the active provider timeout; ``recovery_guard`` is
    stamped before a stale row is recovered. ``superseded`` is reserved for a
    later milestone (a newer delivery replacing an older one).
    """

    QUEUED = "queued"
    CLAIMED = "claimed"
    PROVIDER_DISPATCHED = "provider_dispatched"
    PROVIDER_RETURNED = "provider_returned"
    DELIVERED = "delivered"
    RETRYING = "retrying"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    RECOVERY_GUARD = "recovery_guard"
    SUPERSEDED = "superseded"


class GrowthAnalysisType(StrEnum):
    """What a ``growth_analyses`` snapshot measures (M7).

    Mirrors ``public.growth_analysis_type``. Each value is produced by exactly
    one deterministic analysis engine.
    """

    HEALTH = "health"
    KPIS = "kpis"
    PIPELINE = "pipeline"
    FUNNEL = "funnel"
    CONVERSION = "conversion"
    REVENUE = "revenue"
    ACTIVITY = "activity"
    BOTTLENECKS = "bottlenecks"
    OPPORTUNITIES = "opportunities"
    TRENDS = "trends"


class GrowthAnalysisStatus(StrEnum):
    """Lifecycle of a ``growth_analyses`` snapshot (M7)."""

    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationPriority(StrEnum):
    """Urgency / qualitative confidence of a growth recommendation (M7).

    ``high``/``medium``/``low`` is used both for actionable priority and for
    the qualitative confidence score (mirrors ``recommendation_priority``).
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationStatus(StrEnum):
    """Triage lifecycle of a growth recommendation (M7).

    ``active`` -> ``acknowledged`` | ``applied`` (or ``dismissed``).
    """

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    APPLIED = "applied"
    DISMISSED = "dismissed"
