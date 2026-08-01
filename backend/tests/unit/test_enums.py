"""Unit tests: enum value sets must match the database enum definitions."""
from app.models.enums import (
    ActivityEventType,
    ConversationSender,
    ImportStatus,
    LeadStatus,
    OutreachChannel,
    OutreachStatus,
    UserRole,
)


def test_user_role_values() -> None:
    assert set(UserRole) == {"owner", "admin", "member", "viewer"}


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
    }


def test_conversation_sender_values() -> None:
    assert set(ConversationSender) == {"lead", "agent", "system"}


def test_all_enums_are_str_enums() -> None:
    for enum_cls in (
        UserRole,
        LeadStatus,
        OutreachChannel,
        OutreachStatus,
        ImportStatus,
        ActivityEventType,
        ConversationSender,
    ):
        assert all(isinstance(member.value, str) for member in enum_cls)
        # Round-trip: constructing from the raw label must yield the member.
        for member in enum_cls:
            assert enum_cls(member.value) is member
