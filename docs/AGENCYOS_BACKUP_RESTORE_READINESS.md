# AgencyOS — Backup and Restore Readiness

## Current state

- **Backup mechanism in repository:** none. `scripts/db/` contains only `migrate.sh` and `seed.sh`. No `pg_dump`, `pg_restore`, snapshot, or retention configuration is present.
- **Database engine:** PostgreSQL 16 (per CI service image and migrations). Schema managed by numbered SQL migrations in `database/migrations/` plus `database/schema/` and `database/migrations/` (0001–0033+).
- **Storage:** local filesystem (`UPLOAD_DIR=../storage/uploads`, `LOG_FILE_PATH=../storage/logs/backend.log`) for uploads/logs; no object-storage adapter configured by default (Supabase optional).
- **Disaster-recovery documentation:** none found (`docs/` has no backup/DR doc prior to this report).

## What was verified

- The integration test harness (`tests/integration/test_services_integration.py`, `test_tenant_isolation_rls.py`, etc.) proves that a disposable database can be created, migrated, populated, and dropped — i.e. the schema is reproducible from migrations. This is a *schema reproducibility* proof, not a data backup/restore proof.
- No restore of a populated backup into an isolated target was demonstrated, because no backup tooling exists in the repository and no persistent non-production data store is configured in this audit environment.

## Gaps

1. No documented backup procedure.
2. No automated/scheduled backup.
3. No tested restore path.
4. No checksum/integrity verification of backup artifacts.
5. File uploads in `storage/uploads/` are not covered by any backup strategy.
6. Retention policy undefined.

## Recommendation (smallest safe mechanism)

Before real operational data is stored:
1. Add `scripts/db/backup.sh` using `pg_dump --format=custom` with a timestamped filename and `sha256sum` checksum, writing to a configurable directory (never into the repo working tree).
2. Add `scripts/db/restore.sh` that restores into a *fresh, explicitly-named* database only (refusing to overwrite `agencyos`), for isolated verification.
3. Document RPO/RTO expectations and test restore quarterly.
4. Include `storage/uploads/` in the same backup scope (tar + checksum).

## Verdict

Backup/restore is **not verified** for this repository today. This is a documented gap and an owner-operated prerequisite before storing real client data. It does not block Phase 6 development (which uses synthetic/test data), but it must be completed before production use of real data.
