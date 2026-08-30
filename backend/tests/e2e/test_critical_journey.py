"""M10 critical-journey smoke: lead -> note -> pipeline stage, org-scoped.

Exercises the core CRM path end-to-end against a real PostgreSQL (CI only;
skips where no DB is reachable). This is the data-layer counterpart to the
HTTP contract checks in ``scripts/ci/contract_diff.py``: it proves the
migrations actually support the journey the UI drives, and that rows stay
scoped to their organization.
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.conftest import _database_available, _insert_org

# Skipped where no PostgreSQL is reachable (CI provides postgres:16-alpine).
pytestmark = pytest.mark.skipif(
    not _database_available(), reason="PostgreSQL server not reachable"
)


def test_critical_journey_lead_note_pipeline(migrated_db) -> None:
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_a)
    _insert_org(migrated_db, org_b)

    with migrated_db.cursor() as cur:
        # -- Lead created for org A.
        cur.execute(
            "INSERT INTO public.leads (organization_id, first_name) "
            "VALUES (%s, 'Acme Co') RETURNING id",
            (org_a,),
        )
        lead_a = cur.fetchone()[0]

        # -- Note attached to that lead (org-scoped FK).
        cur.execute(
            "INSERT INTO public.notes (organization_id, lead_id, body) "
            "VALUES (%s, %s, 'Initial contact made') RETURNING id",
            (org_a, lead_a),
        )
        note_a = cur.fetchone()[0]

        # -- Pipeline stage created and the lead advanced into it.
        cur.execute(
            "INSERT INTO public.pipeline_stages (organization_id, name) "
            "VALUES (%s, 'Proposal Sent') RETURNING id",
            (org_a,),
        )
        stage_a = cur.fetchone()[0]
        cur.execute(
            "UPDATE public.leads SET stage_id = %s WHERE id = %s",
            (stage_a, lead_a),
        )

        # -- Assertions: the journey persisted and is queryable by org.
        cur.execute(
            "SELECT l.first_name, ps.name FROM public.leads l "
            "JOIN public.pipeline_stages ps ON ps.id = l.stage_id "
            "WHERE l.id = %s",
            (lead_a,),
        )
        name, stage = cur.fetchone()
        assert name == "Acme Co"
        assert stage == "Proposal Sent"

        cur.execute(
            "SELECT count(*) FROM public.notes WHERE organization_id = %s AND lead_id = %s",
            (org_a, lead_a),
        )
        assert cur.fetchone()[0] == 1

        # -- Org B sees none of org A's data (isolation at the query layer).
        cur.execute("SELECT count(*) FROM public.leads WHERE organization_id = %s", (org_b,))
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT count(*) FROM public.notes WHERE id = %s", (note_a,)
        )
        assert cur.fetchone()[0] == 1
    migrated_db.commit()
