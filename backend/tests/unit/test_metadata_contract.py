"""Unit tests: the ``metadata`` field contract on activity/import/provider/
outreach schemas.

Every schema that maps to an ORM column named ``metadata_`` must:
- accept the wire name ``metadata`` (field name),
- accept the internal/ORM alias ``metadata_`` without silently dropping it,
- serialize back under the wire name ``metadata``.

This mirrors the canonical pattern already used by the *Create/*Read classes
(``alias="metadata_"`` + ``populate_by_name=True`` +
``serialization_alias="metadata"``). Without it, callers passing ``metadata_``
lose the payload silently (extra fields are ignored), which is data loss.
"""
from app.schemas.activity import ActivityLogCreate
from app.schemas.imports import ImportJobUpdate
from app.schemas.outreach import OutreachAttemptUpdate
from app.schemas.provider import ProviderUsageUpdate

ORG_ID = "00000000-0000-0000-0000-000000000001"
LEAD_ID = "00000000-0000-0000-0000-000000000301"


def test_activity_log_create_accepts_metadata_alias() -> None:
    log = ActivityLogCreate(
        organization_id=ORG_ID, event_type="lead_imported", metadata_={"x": 1}
    )
    assert log.metadata == {"x": 1}
    assert log.model_dump()["metadata"] == {"x": 1}


def test_activity_log_create_accepts_wire_name_metadata() -> None:
    log = ActivityLogCreate(
        organization_id=ORG_ID, event_type="lead_imported", metadata={"x": 1}
    )
    assert log.metadata == {"x": 1}


def test_outreach_attempt_update_accepts_metadata_alias() -> None:
    upd = OutreachAttemptUpdate(metadata_={"a": 1})
    assert upd.metadata == {"a": 1}
    assert upd.model_dump()["metadata"] == {"a": 1}


def test_import_job_update_accepts_both_metadata_spellings() -> None:
    by_name = ImportJobUpdate(metadata={"x": 1})
    by_alias = ImportJobUpdate(metadata_={"x": 1})
    assert by_name.metadata == by_alias.metadata == {"x": 1}
    assert by_alias.model_dump(by_alias=True)["metadata"] == {"x": 1}


def test_provider_usage_update_accepts_metadata_alias() -> None:
    upd = ProviderUsageUpdate(metadata_={"cost_bucket": "high"})
    assert upd.metadata == {"cost_bucket": "high"}
    assert upd.model_dump()["metadata"] == {"cost_bucket": "high"}


def test_metadata_dump_key_always_wire_name() -> None:
    cases = [
        ActivityLogCreate(organization_id=ORG_ID, event_type="lead_imported", metadata={"k": 1}),
        OutreachAttemptUpdate(metadata={"k": 1}),
        ImportJobUpdate(metadata={"k": 1}),
        ProviderUsageUpdate(metadata={"k": 1}),
    ]
    for model in cases:
        dumped = model.model_dump()
        assert "metadata" in dumped
        assert dumped["metadata"] == {"k": 1}


def test_metadata_accepts_none_on_update_models() -> None:
    assert OutreachAttemptUpdate(metadata=None).metadata is None
    assert ImportJobUpdate(metadata=None).metadata is None
    assert ProviderUsageUpdate(metadata=None).metadata is None
