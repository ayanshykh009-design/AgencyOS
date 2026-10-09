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


# =====================================================================
# Migration 0033 (backend RLS) — static contract (no database required).
#
# The Supabase policy files above only cover the managed PostgREST surface;
# 0033 is the canonical backend enforcement the API/workers rely on. These
# tests parse the numbered migrations and pin the contract the behavioral
# tests (test_tenant_isolation_rls.py) assume.
# =====================================================================

MIGRATIONS_DIR = (
    pathlib.Path(__file__).resolve().parents[3] / "database" / "migrations"
)
RLS_MIGRATION = MIGRATIONS_DIR / "0033_tenant_isolation_rls.sql"

# Tables that hold no tenant data (instance-global) and therefore carry
# whitelisting policies instead of org scoping.
GLOBAL_TABLES = {"system_settings", "credential_key_versions", "worker_health"}

# SECURITY DEFINER lookups that must resolve rows before identity exists.
DEFINER_LOOKUPS = (
    "app_get_user_by_id",
    "app_get_user_by_email",
    "app_find_active_user_by_email",
    "app_get_valid_refresh_token",
    "app_get_organization_by_slug",
    "app_slug_available",
    "app_get_team_invite_by_token_hash",
)

_ALL_FUNCTIONS = ("tenant_org_id", *DEFINER_LOOKUPS)

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE (?:IF NOT EXISTS )?public\.(\w+)\s*\(", re.IGNORECASE
)
_ADD_COLUMN_RE = re.compile(
    r"ALTER TABLE public\.(\w+)\s+ADD COLUMN\b([^;]*);",
    re.IGNORECASE | re.DOTALL,
)
_POLICY_RE = re.compile(
    r"CREATE\s+POLICY\s+(\w+)\s+ON\s+public\.(\w+)(.*?);",
    re.IGNORECASE | re.DOTALL,
)
_REVOKE_RE = re.compile(
    r"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.(\w+)\(([^)]*)\)\s+FROM\s+PUBLIC",
    re.IGNORECASE,
)
_GRANT_RE = re.compile(
    r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.(\w+)\(([^)]*)\)\s+TO\s+(\w+)",
    re.IGNORECASE,
)


def _numbered_migrations() -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    }


def _balanced_body(text: str, open_idx: int) -> str:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx : i + 1]
    return text[open_idx:]


def _org_column_tables(migrations: dict[str, str]) -> set[str]:
    """Tables defined with an ``organization_id`` column in any migration."""
    tables: set[str] = set()
    for text in migrations.values():
        for match in _CREATE_TABLE_RE.finditer(text):
            if re.search(r"\borganization_id\b", _balanced_body(text, match.end() - 1)):
                tables.add(match.group(1))
        for match in _ADD_COLUMN_RE.finditer(text):
            if re.search(r"\borganization_id\b", match.group(2)):
                tables.add(match.group(1))
    return tables


def _policies_by_table(rls_text: str) -> dict[str, dict[str, str]]:
    """``{table: {policy_name: normalized_chunk}}`` for migration 0033."""
    out: dict[str, dict[str, str]] = {}
    for match in _POLICY_RE.finditer(rls_text):
        name, table, chunk = match.group(1), match.group(2), match.group(3)
        out.setdefault(table, {})[name] = " ".join(chunk.split())
    return out


def test_migration_0033_present():
    assert RLS_MIGRATION.is_file(), "0033_tenant_isolation_rls.sql must exist"


def test_org_column_tables_are_tenant_scoped():
    """Every table carrying an organization_id column gets the full tenant
    policy set (SELECT/INSERT/UPDATE/DELETE pinned to tenant_org_id())."""
    migrations = _numbered_migrations()
    rls_text = RLS_MIGRATION.read_text(encoding="utf-8")
    policies = _policies_by_table(rls_text)
    org_tables = _org_column_tables(migrations)

    assert len(org_tables) >= 40, f"expected the org-table inventory, got {org_tables}"

    scoped = "organization_id = public.tenant_org_id()"
    failures = []
    for table in sorted(org_tables):
        table_policies = policies.get(table, {})
        expected = {
            f"{table}_select_tenant": ("FOR SELECT", f"USING ({scoped})"),
            f"{table}_insert_tenant": ("FOR INSERT", f"WITH CHECK ({scoped})"),
            f"{table}_update_tenant": (
                "FOR UPDATE",
                f"USING ({scoped})",
                f"WITH CHECK ({scoped})",
            ),
            f"{table}_delete_tenant": ("FOR DELETE", f"USING ({scoped})"),
        }
        for policy_name, needles in expected.items():
            chunk = table_policies.get(policy_name)
            if chunk is None:
                failures.append(f"{table}: missing policy {policy_name}")
                continue
            if "TO agencyos_app" not in chunk:
                failures.append(f"{policy_name}: not scoped TO agencyos_app")
            for needle in needles:
                if needle not in chunk:
                    failures.append(f"{policy_name}: missing `{needle}`")
    assert not failures, "tenant policy coverage gaps:\n" + "\n".join(failures)


def test_tenant_policy_targets_exactly_match_org_tables():
    """No org table may lack a tenant policy and no policy may target an
    unknown table (typo protection)."""
    migrations = _numbered_migrations()
    policies = _policies_by_table(RLS_MIGRATION.read_text(encoding="utf-8"))
    tenant_targets = {
        table
        for table, named in policies.items()
        if any(name.endswith("_tenant") for name in named)
    }
    expected = _org_column_tables(migrations) | {"organizations"}
    assert tenant_targets == expected, (
        f"missing={sorted(expected - tenant_targets)} "
        f"unexpected={sorted(tenant_targets - expected)}"
    )


def test_every_policy_table_has_rls_enabled():
    """RLS must be enabled (by 0033 or the creating migration) for every
    table 0033 installs policies on — a policy without RLS is inert."""
    corpus = "\n".join(_numbered_migrations().values())
    policies = _policies_by_table(RLS_MIGRATION.read_text(encoding="utf-8"))
    missing = [
        table
        for table in policies
        if not re.search(
            rf"ALTER TABLE public\.{re.escape(table)} ENABLE ROW LEVEL SECURITY",
            corpus,
            re.IGNORECASE,
        )
    ]
    assert not missing, f"tables with policies but RLS not enabled: {missing}"


def test_organizations_policies_are_id_scoped():
    """`organizations` has no organization_id column: it must be scoped by
    primary key so an org row is only visible/insertable as itself."""
    policies = _policies_by_table(RLS_MIGRATION.read_text(encoding="utf-8"))["organizations"]
    scoped = "id = public.tenant_org_id()"
    assert f"USING ({scoped})" in policies["organizations_select_tenant"]
    assert f"WITH CHECK ({scoped})" in policies["organizations_insert_tenant"]
    assert f"USING ({scoped})" in policies["organizations_delete_tenant"]
    assert f"USING ({scoped})" in policies["organizations_update_tenant"]


def test_global_tables_whitelisted_without_tenant_scope():
    """system_settings / credential_key_versions are instance-global (no
    tenant data); worker_health is SELECT-only for the app role."""
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    policies = _policies_by_table(text)

    for table in ("system_settings", "credential_key_versions"):
        chunk = policies[table][f"{table}_global"]
        assert "FOR ALL TO agencyos_app" in chunk
        assert "USING (true)" in chunk and "WITH CHECK (true)" in chunk

    worker = policies["worker_health"]["worker_health_select_global"]
    assert "FOR SELECT TO agencyos_app" in worker
    assert "USING (true)" in worker
    assert not any(
        name != "worker_health_select_global" for name in policies["worker_health"]
    ), "worker_health must stay SELECT-only for the app role"


def test_no_force_row_level_security():
    """Pinned design decision: FORCE ROW LEVEL SECURITY is intentionally not
    applied so developer/CI owner connections keep working; production
    applies the agencyos_app connection role instead."""
    corpus = "\n".join(_numbered_migrations().values())
    sql_only = "\n".join(line.split("--", 1)[0] for line in corpus.splitlines())
    assert "FORCE ROW LEVEL SECURITY" not in sql_only


def test_roles_created_with_expected_attributes():
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    assert "CREATE ROLE agencyos_app NOLOGIN" in text
    assert "CREATE ROLE agencyos_worker NOLOGIN BYPASSRLS" in text
    # Converge guard: an accidentally pre-created worker role must be fixed.
    assert "ALTER ROLE agencyos_worker NOLOGIN BYPASSRLS" in text
    assert "IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles" in text


def test_tenant_org_id_is_security_definer_with_pinned_search_path():
    match = re.search(
        r"CREATE OR REPLACE FUNCTION public\.tenant_org_id\(\)(.*?)\$\$;",
        RLS_MIGRATION.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match, "tenant_org_id() must be defined in 0033"
    body = match.group(1)
    assert "SECURITY DEFINER" in body
    assert "SET search_path = pg_catalog, public" in body
    assert "current_setting('app.current_organization_id'" in body


def test_definer_lookups_are_security_definer_with_pinned_search_path():
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    for fn in DEFINER_LOOKUPS:
        match = re.search(
            rf"CREATE OR REPLACE FUNCTION public\.{fn}\((.*?)\$\$;",
            text,
            re.DOTALL,
        )
        assert match, f"{fn}() missing from 0033"
        body = match.group(1)
        assert "SECURITY DEFINER" in body, f"{fn}() must be SECURITY DEFINER"
        assert "SET search_path = pg_catalog, public" in body, (
            f"{fn}() must pin search_path"
        )


def test_definer_functions_revoked_from_public_and_granted():
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    revoked = {m.group(1) for m in _REVOKE_RE.finditer(text)}
    grants = {(m.group(1), m.group(3)) for m in _GRANT_RE.finditer(text)}

    assert set(_ALL_FUNCTIONS) <= revoked, (
        f"missing REVOKE FROM PUBLIC: {set(_ALL_FUNCTIONS) - revoked}"
    )
    for fn in DEFINER_LOOKUPS:
        assert (fn, "agencyos_app") in grants, f"{fn} must be granted to agencyos_app"
        assert (fn, "agencyos_worker") in grants, f"{fn} must be granted to agencyos_worker"

    # tenant_org_id additionally keeps the Supabase policy surface working:
    # anon/authenticated call it from database/supabase/policies, but those
    # roles may not exist on a plain PostgreSQL deployment (guarded grant).
    assert ("tenant_org_id", "agencyos_app") in grants
    assert ("tenant_org_id", "agencyos_worker") in grants
    assert re.search(
        r"IF EXISTS \(SELECT 1 FROM pg_catalog\.pg_roles WHERE rolname = 'anon'\)"
        r".*?GRANT EXECUTE ON FUNCTION public\.tenant_org_id\(\) TO anon",
        text,
        re.DOTALL,
    ), "guarded anon EXECUTE grant missing (breaks Supabase policy files)"
    assert re.search(
        r"IF EXISTS \(SELECT 1 FROM pg_catalog\.pg_roles WHERE rolname = 'authenticated'\)"
        r".*?GRANT EXECUTE ON FUNCTION public\.tenant_org_id\(\) TO authenticated",
        text,
        re.DOTALL,
    ), "guarded authenticated EXECUTE grant missing (breaks Supabase policy files)"


def test_privilege_grants_cover_both_roles():
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    for role in ("agencyos_app", "agencyos_worker"):
        assert (
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
            f"TO {role}" in text
        ), f"table grants missing for {role}"
        assert (
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}" in text
        ), f"sequence grants missing for {role}"
        assert (
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public\n"
            f"  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}" in text
        ), f"default table grants missing for {role}"


def test_rollback_section_lists_every_created_function():
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    rollback = text.split("-- ROLLBACK", 1)[-1]
    for fn in _ALL_FUNCTIONS:
        assert f"DROP FUNCTION IF EXISTS public.{fn}(" in rollback, (
            f"rollback must list DROP FUNCTION for {fn}"
        )


def test_guc_name_matches_backend_contract():
    """The migration, the backend ContextVar layer, and the begin-listener
    must agree on the GUC name — a rename in any one layer silently disables
    RLS scoping."""
    from app.core.tenant_context import ORG_GUC_NAME

    assert ORG_GUC_NAME == "app.current_organization_id"
    assert f"'{ORG_GUC_NAME}'" in RLS_MIGRATION.read_text(encoding="utf-8")
    assert not any(
        name != ORG_GUC_NAME for name in re.findall(
            r"'(app\.[a-z_]+)'", RLS_MIGRATION.read_text(encoding="utf-8")
        )
    ), "0033 must only reference the canonical tenant GUC name"
