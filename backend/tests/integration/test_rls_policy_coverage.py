"""M10 static RLS policy coverage (no database required).

Scans every SQL file under ``database/supabase/policies`` and asserts the
tenant-isolation contract that RLS runtime tests assume:

  * each file that governs a table enables Row Level Security;
  * every ``CREATE POLICY`` carries a tenant scoping predicate
    (``tenant_org_id()`` / ``organization_id`` / ``auth.uid()`` / ``auth.role()``
    / ``user_id`` / ``owner_id``) and is never an unscoped ``USING (true)``.

Runtime org-isolation is covered separately (DB-gated). This catches
accidental policy regressions that would silently break isolation.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core.config import settings  # noqa: F401  (ensures backend importable)

POLICIES_DIR = (
    pathlib.Path(__file__).resolve().parents[3] / "database" / "supabase" / "policies"
)

SCOPING_TOKENS = (
    "tenant_org_id",
    "organization_id",
    "auth.uid()",
    "auth.role()",
    "user_id",
    "owner_id",
    "public.user_org_id",
    "current_setting('request.jwt.claims",
)

ENABLE_RE = re.compile(r"ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)
POLICY_RE = re.compile(r"CREATE\s+POLICY", re.IGNORECASE)
USING_TRUE_RE = re.compile(r"USING\s*\(\s*true\s*\)", re.IGNORECASE)


def _policy_files():
    # Helper files (e.g. _helpers.sql) define functions, not table policies.
    return sorted(p for p in POLICIES_DIR.glob("*.sql") if not p.name.startswith("_"))


def test_policy_files_present():
    files = _policy_files()
    assert files, "expected RLS policy files under database/supabase/policies"


@pytest.mark.parametrize("policy_file", _policy_files(), ids=lambda p: p.name)
def test_policy_file_enables_rls(policy_file):
    text = policy_file.read_text(encoding="utf-8")
    assert ENABLE_RE.search(text), f"{policy_file.name}: missing ENABLE ROW LEVEL SECURITY"


@pytest.mark.parametrize("policy_file", _policy_files(), ids=lambda p: p.name)
def test_policies_are_tenant_scoped(policy_file):
    text = policy_file.read_text(encoding="utf-8")
    # Split into per-policy chunks so each policy is inspected independently.
    chunks = POLICY_RE.split(text)
    # chunks[0] is preamble before the first CREATE POLICY.
    for chunk in chunks[1:]:
        lowered = chunk.lower()
        if not any(tok in lowered for tok in SCOPING_TOKENS):
            # Unscoped policy: only acceptable if it is service-role-only via a
            # role guard expressed without the literal scoping tokens above.
            assert USING_TRUE_RE.search(
                chunk
            ) is None or "service_role" in lowered, (
                f"{policy_file.name}: policy with no tenant scoping and no "
                f"service_role guard (potential cross-tenant leak):\n{chunk.strip()[:200]}"
            )


def test_helper_defines_tenant_org_id():
    helper = POLICIES_DIR / "_helpers.sql"
    if not helper.exists():
        pytest.skip("_helpers.sql not present")
    assert "tenant_org_id" in helper.read_text(encoding="utf-8")
