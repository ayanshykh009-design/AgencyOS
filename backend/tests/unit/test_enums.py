"""Unit tests: enum value sets must match the database enum definitions."""
from app.models.enums import (
    ActivityEventType,
    AgentHealth,
    AgentRunStatus,
    AgentRunTrigger,
    AgentStateStatus,
    ApprovalLogAction,
    ApprovalRequestStatus,
    AssignmentMethod,
    AssignmentStrategy,
    BriefingType,
    ConversationSender,
    CredentialType,
    ExecutionEventType,
    ExecutionStatus,
    ImportStatus,
    InsightSeverity,
    InsightStatus,
    InsightType,
    InviteStatus,
    LeadStatus,
    MemoryScope,
    MemoryType,
    NotificationType,
    OutreachChannel,
    OutreachStatus,
    RecurrenceFrequency,
    StageLifecycle,
    TaskPriority,
    TaskStatus,
    UserRole,
    WorkflowStatus,
    WorkflowTriggerType,
)


def test_user_role_values() -> None:
    assert set(UserRole) == {
        "owner",
        "admin",
        "manager",
        "member",
        "sales_agent",
        "viewer",
    }


def test_invite_status_values() -> None:
    assert set(InviteStatus) == {"pending", "accepted", "revoked", "expired"}


def test_lead_status_values() -> None:
    assert set(LeadStatus) == {
        "new",
        "researching",
        "contacted",
        "meeting_booked",
        "proposal_sent",
        "won",
        "lost",
    }


def test_outreach_channel_values() -> None:
    assert set(OutreachChannel) == {
        "email",
        "whatsapp",
        "contact_form",
        "linkedin",
        "instagram",
        "facebook",
    }


def test_outreach_status_values() -> None:
    assert set(OutreachStatus) == {
        "queued",
        "sending",
        "sent",
        "delivered",
        "failed",
        "skipped",
        "manually_sent",
        "replied",
    }


def test_import_status_values() -> None:
    assert set(ImportStatus) == {"pending", "processing", "completed", "failed", "cancelled"}


def test_activity_event_type_values() -> None:
    assert set(ActivityEventType) == {
        "lead_imported",
        "research_completed",
        "score_generated",
        "email_sent",
        "whatsapp_sent",
        "manual_message_completed",
        "reply_received",
        "meeting_booked",
        "proposal_sent",
        "lead_won",
        "lead_lost",
        "user_invited",
        "invite_accepted",
        "invite_revoked",
        "user_role_changed",
        "user_status_changed",
        "lead_assigned",
        "task_created",
        "task_updated",
        "task_completed",
        "task_deleted",
        "note_created",
        "note_updated",
        "note_deleted",
        "workflow_created",
        "workflow_updated",
        "workflow_activated",
        "workflow_paused",
        "workflow_archived",
        "workflow_deleted",
        "execution_queued",
        "execution_started",
        "execution_completed",
        "execution_failed",
        "execution_retried",
        "execution_cancelled",
        "credential_created",
        "credential_updated",
        "credential_deleted",
        "trigger_created",
        "trigger_updated",
        "trigger_deleted",
        "automation_paused",
        "automation_resumed",
    }


def test_execution_event_type_values() -> None:
    assert set(ExecutionEventType) == {
        "queued",
        "started",
        "adapter_dispatched",
        "adapter_returned",
        "step_started",
        "step_completed",
        "step_failed",
        "retrying",
        "succeeded",
        "failed",
        "cancelled",
        "timed_out",
        "timeout_guard",
    }


def test_conversation_sender_values() -> None:
    assert set(ConversationSender) == {"lead", "agent", "system"}


def test_assignment_strategy_values() -> None:
    assert set(AssignmentStrategy) == {"manual", "round_robin", "rules"}


def test_assignment_method_values() -> None:
    assert set(AssignmentMethod) == {"manual", "round_robin", "rules", "bulk", "unassigned"}


def test_stage_lifecycle_values() -> None:
    assert set(StageLifecycle) == {"open", "won", "lost"}


def test_task_status_values() -> None:
    assert set(TaskStatus) == {"todo", "in_progress", "completed", "cancelled"}


def test_task_priority_values() -> None:
    assert set(TaskPriority) == {"low", "medium", "high", "urgent"}


def test_recurrence_frequency_values() -> None:
    assert set(RecurrenceFrequency) == {"daily", "weekly", "monthly"}


def test_workflow_status_values() -> None:
    assert set(WorkflowStatus) == {"draft", "active", "paused", "archived"}


def test_workflow_trigger_type_values() -> None:
    assert set(WorkflowTriggerType) == {"manual", "event", "schedule"}


def test_execution_status_values() -> None:
    assert set(ExecutionStatus) == {
        "queued",
        "running",
        "succeeded",
        "failed",
        "retrying",
        "cancelled",
        "timed_out",
    }


def test_credential_type_values() -> None:
    assert set(CredentialType) == {"n8n_api_key", "api_key", "basic_auth"}


def test_memory_type_values() -> None:
    assert set(MemoryType) == {"working", "long_term"}


def test_memory_scope_values() -> None:
    assert set(MemoryScope) == {
        "conversation",
        "research",
        "workflow",
        "shared_context",
        "knowledge",
        "manual",
    }


def test_agent_run_status_values() -> None:
    assert set(AgentRunStatus) == {
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }


def test_agent_run_trigger_values() -> None:
    assert set(AgentRunTrigger) == {"manual", "schedule", "workflow", "event", "ai_run"}


def test_agent_state_status_values() -> None:
    assert set(AgentStateStatus) == {"active", "paused", "degraded", "disabled"}


def test_agent_health_values() -> None:
    assert set(AgentHealth) == {"healthy", "degraded", "unhealthy"}


def test_notification_type_values() -> None:
    assert set(NotificationType) == {
        "approval_request",
        "approval_result",
        "workflow_event",
        "agent_event",
        "system",
        "briefing",
        "insight",
    }


def test_approval_request_status_values() -> None:
    assert set(ApprovalRequestStatus) == {
        "pending",
        "approved",
        "denied",
        "expired",
        "cancelled",
    }


def test_approval_log_action_values() -> None:
    assert set(ApprovalLogAction) == {
        "requested",
        "notified",
        "approved",
        "denied",
        "expired",
        "cancelled",
    }


def test_briefing_type_values() -> None:
    assert set(BriefingType) == {"daily", "weekly", "manual"}


def test_insight_type_values() -> None:
    assert set(InsightType) == {
        "opportunity",
        "risk",
        "trend",
        "anomaly",
        "recommendation",
    }


def test_insight_severity_values() -> None:
    assert set(InsightSeverity) == {"info", "low", "medium", "high", "critical"}


def test_insight_status_values() -> None:
    assert set(InsightStatus) == {"active", "acknowledged", "dismissed"}


def test_all_enums_are_str_enums() -> None:
    for enum_cls in (
        UserRole,
        InviteStatus,
        LeadStatus,
        OutreachChannel,
        OutreachStatus,
        ImportStatus,
        ActivityEventType,
        ConversationSender,
        AssignmentStrategy,
        AssignmentMethod,
        StageLifecycle,
        TaskStatus,
        TaskPriority,
        RecurrenceFrequency,
        WorkflowStatus,
        WorkflowTriggerType,
        ExecutionStatus,
        ExecutionEventType,
        CredentialType,
        MemoryType,
        MemoryScope,
        AgentRunStatus,
        AgentRunTrigger,
        AgentStateStatus,
        AgentHealth,
        NotificationType,
        ApprovalRequestStatus,
        ApprovalLogAction,
        BriefingType,
        InsightType,
        InsightSeverity,
        InsightStatus,
    ):
        assert all(isinstance(member.value, str) for member in enum_cls)
        # Round-trip: constructing from the raw label must yield the member.
        for member in enum_cls:
            assert enum_cls(member.value) is member
