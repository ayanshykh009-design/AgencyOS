"""Unit tests: Pydantic schema validation for the V1 domains."""
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.activity import ActivityLogCreate
from app.schemas.conversation import ConversationCreate, ConversationMessageCreate
from app.schemas.imports import ImportJobCreate
from app.schemas.lead import LeadCreate, LeadRead
from app.schemas.lead_research import LeadResearchCreate
from app.schemas.lead_source import LeadSourceCreate
from app.schemas.organization import OrganizationCreate
from app.schemas.outreach import (
    FollowUpCreate,
    ManualOutreachQueueCreate,
    OutreachAttemptCreate,
    OutreachMessageCreate,
)
from app.schemas.provider import ProviderUsageCreate
from app.schemas.user import UserCreate

ORG_ID = "00000000-0000-0000-0000-000000000001"
LEAD_ID = "00000000-0000-0000-0000-000000000301"
USER_ID = "00000000-0000-0000-0000-000000000101"


def test_organization_create_valid() -> None:
    org = OrganizationCreate(name="Acme", slug="acme")
    assert org.slug == "acme"


def test_organization_create_slug_normalized() -> None:
    org = OrganizationCreate(name="Acme", slug="  ACME-Dev ")
    assert org.slug == "acme-dev"


def test_organization_create_invalid_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        OrganizationCreate(name="Acme", slug="Bad Slug!")


def test_user_create_valid_and_email_normalized() -> None:
    user = UserCreate(email="  Jane@Example.com ", full_name="Jane", organization_id=ORG_ID)
    assert user.email == "jane@example.com"


def test_user_create_bad_email_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", full_name="Jane", organization_id=ORG_ID)


def test_user_create_blank_name_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="jane@example.com", full_name="", organization_id=ORG_ID)


def test_lead_create_valid_contact() -> None:
    lead = LeadCreate(
        organization_id=ORG_ID,
        email=" Ada@Example.com ",
        first_name="Ada",
    )
    assert lead.email == "ada@example.com"


def test_lead_create_at_least_one_contact() -> None:
    with pytest.raises(ValidationError, match="at least one contact"):
        LeadCreate(organization_id=ORG_ID, first_name="No", last_name="Contact")


def test_lead_create_phone_normalized() -> None:
    lead = LeadCreate(organization_id=ORG_ID, phone="+44 (20) 1234-5678")
    assert lead.phone == "442012345678"


def test_lead_create_score_out_of_range() -> None:
    with pytest.raises(ValidationError):
        LeadCreate(organization_id=ORG_ID, email="a@b.com", score=150)


def test_lead_create_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        LeadCreate(organization_id=ORG_ID, email="a@b.com", status="not_a_status")


def test_lead_create_invalid_email_rejected() -> None:
    with pytest.raises(ValidationError):
        LeadCreate(organization_id=ORG_ID, email="definitely-not-email")


def test_lead_read_has_normalized_columns() -> None:
    read = LeadRead.model_validate(
        {
            "id": LEAD_ID,
            "organization_id": ORG_ID,
            "email": "ada@example.com",
            "email_normalized": "ada@example.com",
            "status": "new",
            "score": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )
    assert read.id == UUID(LEAD_ID)


def test_lead_source_create_valid() -> None:
    src = LeadSourceCreate(name="Website")
    assert src.channel == "contact_form"


def test_lead_source_create_invalid_channel_rejected() -> None:
    with pytest.raises(ValidationError):
        LeadSourceCreate(name="Website", channel="sms")


def test_outreach_message_create_valid() -> None:
    msg = OutreachMessageCreate(
        organization_id=ORG_ID,
        name="Cold #1",
        channel="email",
        body="Hi {{first_name}}",
    )
    assert msg.variables == []


def test_outreach_message_create_empty_body_rejected() -> None:
    with pytest.raises(ValidationError):
        OutreachMessageCreate(organization_id=ORG_ID, name="Cold #1", channel="email", body="")


def test_outreach_attempt_create_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        OutreachAttemptCreate(
            organization_id=ORG_ID, lead_id=LEAD_ID, channel="email", status="posted"
        )


def test_follow_up_sequence_position() -> None:
    with pytest.raises(ValidationError):
        FollowUpCreate(
            organization_id=ORG_ID,
            lead_id=LEAD_ID,
            channel="email",
            body="x",
            sequence_position=0,
        )


def test_manual_outreach_priority_non_negative() -> None:
    with pytest.raises(ValidationError):
        ManualOutreachQueueCreate(
            organization_id=ORG_ID, lead_id=LEAD_ID, channel="whatsapp", priority=-1
        )


def test_conversation_message_body_required() -> None:
    with pytest.raises(ValidationError):
        ConversationMessageCreate(
            conversation_id="00000000-0000-0000-0000-000000000401",
            organization_id=ORG_ID,
            sender_type="lead",
            body="",
        )


def test_conversation_create_valid() -> None:
    conv = ConversationCreate(organization_id=ORG_ID, lead_id=LEAD_ID, channel="email")
    assert conv.is_open is True


def test_activity_log_event_type_validation() -> None:
    with pytest.raises(ValidationError):
        ActivityLogCreate(organization_id=ORG_ID, event_type="not_an_event")


def test_activity_log_valid() -> None:
    log = ActivityLogCreate(organization_id=ORG_ID, event_type="lead_imported")
    assert log.event_type == "lead_imported"


def test_import_job_valid() -> None:
    job = ImportJobCreate(
        organization_id=ORG_ID,
        created_by_user_id=USER_ID,
        file_name="leads.csv",
        total_rows=10,
    )
    assert job.file_name == "leads.csv"


def test_import_job_negative_rows_rejected() -> None:
    with pytest.raises(ValidationError):
        ImportJobCreate(
            organization_id=ORG_ID,
            created_by_user_id=USER_ID,
            file_name="leads.csv",
            total_rows=-1,
        )


def test_provider_usage_valid() -> None:
    usage = ProviderUsageCreate(
        organization_id=ORG_ID, provider="openai", feature="research", usage_date="2026-08-01"
    )
    assert usage.cost_usd == 0


def test_provider_usage_negative_cost_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderUsageCreate(
            organization_id=ORG_ID,
            provider="openai",
            feature="research",
            usage_date="2026-08-01",
            cost_usd=-0.5,
        )


def test_lead_research_status_validation() -> None:
    with pytest.raises(ValidationError, match="invalid research status"):
        LeadResearchCreate(lead_id=LEAD_ID, organization_id=ORG_ID, status="bogus")
