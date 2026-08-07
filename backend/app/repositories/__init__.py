"""Repositories package: data-access layer.

The ONLY place that talks to the persistence layer (SQLAlchemy / Supabase).
Routers and services never touch SQL or ORM sessions directly.

Naming convention: <domain>_repository.py (e.g. prospect_repository.py).
"""
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.base import TenantRepository
from app.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
)
from app.repositories.credential import CredentialRepository
from app.repositories.execution_event import ExecutionEventRepository
from app.repositories.import_job import ImportJobRepository, ImportRowErrorRepository
from app.repositories.lead import LeadRepository
from app.repositories.lead_source import LeadSourceRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.outreach import (
    FollowUpRepository,
    ManualOutreachQueueRepository,
    OutreachAttemptRepository,
    OutreachMessageRepository,
)
from app.repositories.provider_usage import ProviderUsageRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.system_settings import SystemSettingRepository
from app.repositories.user import UserRepository
from app.repositories.worker_health import WorkerHealthRepository
from app.repositories.workflow import WorkflowRepository
from app.repositories.workflow_event import WorkflowEventRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository
from app.repositories.workflow_trigger import WorkflowTriggerRepository

__all__ = [
    "ActivityLogRepository",
    "ConversationMessageRepository",
    "ConversationRepository",
    "CredentialRepository",
    "ExecutionEventRepository",
    "FollowUpRepository",
    "ImportJobRepository",
    "ImportRowErrorRepository",
    "LeadRepository",
    "LeadSourceRepository",
    "ManualOutreachQueueRepository",
    "OrganizationRepository",
    "OutreachAttemptRepository",
    "OutreachMessageRepository",
    "ProviderUsageRepository",
    "RefreshTokenRepository",
    "SystemSettingRepository",
    "TenantRepository",
    "UserRepository",
    "WorkerHealthRepository",
    "WorkflowRepository",
    "WorkflowEventRepository",
    "WorkflowExecutionRepository",
    "WorkflowTriggerRepository",
]
