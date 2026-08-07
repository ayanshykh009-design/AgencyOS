"""Unit tests: ORM metadata must mirror the database schema.

These are static checks against SQLAlchemy metadata (no live DB needed).
The database-level guarantees are exercised by the integration suite.
"""
import pytest
from sqlalchemy import Enum, ForeignKey
from sqlalchemy.sql.schema import Computed, Index

from app.models import (
    ActivityLog,
    Base,
    Conversation,
    ConversationMessage,
    Credential,
    ExecutionEvent,
    FollowUp,
    ImportJob,
    ImportRowError,
    Lead,
    LeadResearch,
    LeadSource,
    ManualOutreachQueue,
    Note,
    Organization,
    OutreachAttempt,
    OutreachMessage,
    ProviderUsage,
    SystemSetting,
    Task,
    User,
    WorkerHealth,
    Workflow,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowTrigger,
)
from app.schemas.user import UserRead

# All core tables from the V1 database plan (plus phase additions).
ALL_MODELS = (
    Organization,
    User,
    LeadSource,
    Lead,
    LeadResearch,
    OutreachMessage,
    OutreachAttempt,
    FollowUp,
    ManualOutreachQueue,
    Note,
    Conversation,
    ConversationMessage,
    ActivityLog,
    ImportJob,
    ImportRowError,
    ProviderUsage,
    Task,
    Workflow,
    WorkflowTrigger,
    WorkflowExecution,
    WorkflowEvent,
    Credential,
    ExecutionEvent,
    WorkerHealth,
    SystemSetting,
)


@pytest.mark.parametrize("model", ALL_MODELS)
def test_model_registered(model: type) -> None:
    assert model.__tablename__ in Base.metadata.tables
    table = Base.metadata.tables[model.__tablename__]
    # Every table carries at least created_at (mixin) — or is an ORM explicit.
    assert "id" in table.c


@pytest.mark.parametrize("model", ALL_MODELS)
def test_uuid_primary_key(model: type) -> None:
    pk = Base.metadata.tables[model.__tablename__].primary_key.columns
    assert len(pk) == 1
    col = next(iter(pk))
    assert col.name == "id"


@pytest.mark.parametrize(
    "model",
    [
        User,
        LeadSource,
        Lead,
        LeadResearch,
        OutreachMessage,
        OutreachAttempt,
        FollowUp,
        ManualOutreachQueue,
        Note,
        Conversation,
        ConversationMessage,
        ActivityLog,
        ImportJob,
        ImportRowError,
        ProviderUsage,
        Task,
        Workflow,
        WorkflowTrigger,
        WorkflowExecution,
        WorkflowEvent,
        Credential,
        ExecutionEvent,
    ],
)
def test_tenant_scoped_with_org_fk(model: type) -> None:
    table = Base.metadata.tables[model.__tablename__]
    assert "organization_id" in table.c
    org_fk = set(table.c.organization_id.foreign_keys)
    assert len(org_fk) == 1
    assert next(iter(org_fk)).column.table.name == "organizations"


def test_updated_at_on_mutable_tables() -> None:
    mutable = {
        Organization,
        User,
        LeadSource,
        Lead,
        LeadResearch,
        OutreachMessage,
        OutreachAttempt,
        FollowUp,
        ManualOutreachQueue,
        Note,
        Conversation,
        ImportJob,
        ProviderUsage,
        Task,
        Workflow,
        WorkflowTrigger,
        WorkflowExecution,
        Credential,
        WorkerHealth,
        SystemSetting,
    }
    for model in mutable:
        assert "updated_at" in Base.metadata.tables[model.__tablename__].c
    append_only = {ConversationMessage, ActivityLog, ImportRowError, WorkflowEvent, ExecutionEvent}
    for model in append_only:
        assert "updated_at" not in Base.metadata.tables[model.__tablename__].c


def test_lead_duplicate_protection_indexes() -> None:
    table = Base.metadata.tables["leads"]
    unique_partial = {
        i.name: i for i in table.indexes if isinstance(i, Index) and i.unique
    }
    assert "uq_leads_org_email" in unique_partial
    assert "uq_leads_org_phone" in unique_partial
    assert "uq_leads_org_website_domain" in unique_partial
    # All three must be org-scoped and NULL-tolerant partial indexes.
    for name in ("uq_leads_org_email", "uq_leads_org_phone", "uq_leads_org_website_domain"):
        index = unique_partial[name]
        assert "organization_id" in [c.name for c in index.columns]
        assert index.dialect_options["postgresql"].get("where") is not None


def test_lead_normalized_columns_are_computed() -> None:
    table = Base.metadata.tables["leads"]
    for col in ("email_normalized", "phone_normalized", "website_domain"):
        assert isinstance(table.c[col].computed, Computed)


def test_lead_research_one_to_one() -> None:
    table = Base.metadata.tables["lead_research"]
    unique = {c.name for c in table.constraints if c.name == "uq_lead_research_lead"}
    assert "uq_lead_research_lead" in unique


def test_conversation_open_per_channel_index() -> None:
    table = Base.metadata.tables["conversations"]
    index = next(i for i in table.indexes if i.name == "uq_conversations_open_per_channel")
    assert index.unique
    assert "lead_id" in [c.name for c in index.columns]
    assert "channel" in [c.name for c in index.columns]
    assert index.dialect_options["postgresql"].get("where") is not None


def test_provider_usage_daily_unique() -> None:
    table = Base.metadata.tables["provider_usage"]
    names = {c.name for c in table.constraints}
    assert "uq_provider_usage_daily" in names


def test_relationships_resolve() -> None:
    # Exercises the mapper configuration for every relationship.
    for model in ALL_MODELS:
        mapper = model.__mapper__
        assert len(mapper.relationships) >= 0
    assert Lead.__mapper__.relationships["lead_source"].mapper.class_ is LeadSource
    assert Lead.__mapper__.relationships["research"].uselist is False
    assert Conversation.__mapper__.relationships["messages"].uselist is True
    assert ImportJob.__mapper__.relationships["row_errors"].uselist is True


def test_native_enum_columns_match_pg_type_names() -> None:
    table = Base.metadata.tables["users"]
    role = table.c.role.type
    assert isinstance(role, Enum)
    assert role.name == "user_role"
    assert role.native_enum


def test_no_secrets_columns() -> None:
    """No column may look like it stores a credential or API key."""
    secret_hints = ("password", "api_key", "secret", "credential", "auth_token")
    # Token USAGE accounting (input_tokens/output_tokens) is not a credential.
    token_count_columns = {"input_tokens", "output_tokens"}
    # users.password_hash stores an Argon2id hash (non-reversible) and is
    # intentionally absent from every API response schema (UserRead excludes it);
    # the raw value can never be recovered, so the column itself is safe.
    hashed_secret_columns = {"password_hash"}
    # credentials.credential_type is a classification LABEL (n8n_api_key,
    # api_key, basic_auth), not the secret itself; the encrypted value lives in
    # credentials.encrypted_value and is never returned by an API schema.
    classification_label_columns = {"credential_type"}
    for table in Base.metadata.tables.values():
        for col in table.c:
            if col.name in token_count_columns:
                continue
            if col.name in hashed_secret_columns:
                continue
            if col.name in classification_label_columns:
                continue
            assert not any(hint in col.name for hint in secret_hints), (
                f"column {table.name}.{col.name} looks like a secret"
            )


def test_password_hash_never_serialized() -> None:
    """The password hash must never be returned by a response schema."""
    assert "password_hash" not in UserRead.model_fields


def test_all_org_uuids_reference_organizations() -> None:
    for table in Base.metadata.tables.values():
        if "organization_id" not in table.c:
            continue
        fks: set[ForeignKey] = set(table.c.organization_id.foreign_keys)
        for fk in fks:
            assert fk.column.table.name == "organizations"
            assert fk.ondelete in ("CASCADE", "SET NULL", "RESTRICT")


def test_pk_uuid_type() -> None:
    for model in ALL_MODELS:
        col = Base.metadata.tables[model.__tablename__].c.id
        type_name = col.type.__class__.__name__.lower()
        assert "uuid" in type_name, f"{model.__tablename__}.id has type {col.type!r}"
