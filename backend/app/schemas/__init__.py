"""Schemas package: Pydantic v2 API contracts.

Request/response models that define the public JSON shape of the API.
Keep them independent from ORM models (map explicitly, avoid dumping models).
"""
from app.schemas.activity import ActivityLogCreate, ActivityLogRead
from app.schemas.conversation import (
    ConversationCreate,
    ConversationMessageCreate,
    ConversationMessageRead,
    ConversationRead,
    ConversationUpdate,
)
from app.schemas.imports import (
    ImportJobCreate,
    ImportJobRead,
    ImportJobUpdate,
    ImportRowErrorCreate,
    ImportRowErrorRead,
)
from app.schemas.lead import LeadCreate, LeadRead, LeadUpdate
from app.schemas.lead_research import (
    LeadResearchCreate,
    LeadResearchRead,
    LeadResearchUpdate,
)
from app.schemas.lead_source import LeadSourceCreate, LeadSourceRead, LeadSourceUpdate
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.schemas.outreach import (
    FollowUpCreate,
    FollowUpRead,
    FollowUpUpdate,
    ManualOutreachQueueCreate,
    ManualOutreachQueueRead,
    ManualOutreachQueueUpdate,
    OutreachAttemptCreate,
    OutreachAttemptRead,
    OutreachAttemptUpdate,
    OutreachMessageCreate,
    OutreachMessageRead,
    OutreachMessageUpdate,
)
from app.schemas.provider import ProviderUsageCreate, ProviderUsageRead, ProviderUsageUpdate
from app.schemas.user import UserCreate, UserRead, UserUpdate

__all__ = [
    "ActivityLogCreate",
    "ActivityLogRead",
    "ConversationCreate",
    "ConversationMessageCreate",
    "ConversationMessageRead",
    "ConversationRead",
    "ConversationUpdate",
    "FollowUpCreate",
    "FollowUpRead",
    "FollowUpUpdate",
    "ImportJobCreate",
    "ImportJobRead",
    "ImportJobUpdate",
    "ImportRowErrorCreate",
    "ImportRowErrorRead",
    "LeadCreate",
    "LeadRead",
    "LeadResearchCreate",
    "LeadResearchRead",
    "LeadResearchUpdate",
    "LeadSourceCreate",
    "LeadSourceRead",
    "LeadSourceUpdate",
    "LeadUpdate",
    "ManualOutreachQueueCreate",
    "ManualOutreachQueueRead",
    "ManualOutreachQueueUpdate",
    "OrganizationCreate",
    "OrganizationRead",
    "OrganizationUpdate",
    "OutreachAttemptCreate",
    "OutreachAttemptRead",
    "OutreachAttemptUpdate",
    "OutreachMessageCreate",
    "OutreachMessageRead",
    "OutreachMessageUpdate",
    "ProviderUsageCreate",
    "ProviderUsageRead",
    "ProviderUsageUpdate",
    "UserCreate",
    "UserRead",
    "UserUpdate",
]
