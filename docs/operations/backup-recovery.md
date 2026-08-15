# Backup & Recovery (Operations Runbook)

Production data durability for AgencyOS. This runbook covers both the managed
Supabase path (recommended) and the self-hosted `docker-compose.prod.yml`
Postgres path.

## Targets

| Objective | Target |
| --------- | ------ |
| RPO (max data loss) | ≤ 5 minutes (PITR) / ≤ 24h (nightly dump) |
| RTO (max restore time) | ≤ 1 hour |
| Backup retention | ≥ 30 days, ≥ 4 weekly, ≥ 12 monthly |

## Managed Supabase (recommended)

1. Enable **Point-in-Time Recovery (PITR)** in the Supabase project settings
   (requires at least the Pro plan). PITR continuously archives WAL.
2. Confirm daily logical backups are retained per the project's retention
   policy.
3. Store the project's connection string in a secrets manager — **never** in
   the repo. Rotate the `postgres` role password on a schedule.
4. Document the Supabase project ref + region; restoration is performed from
   the Supabase dashboard (restore to a new branch/project, then repoint the
   `DATABASE_URL` secret).

## Self-hosted Postgres (docker-compose.prod.yml)

The bundled `postgres` service uses a named volume (`pgdata`) with **no
automated backup**. Add one of the following before handling real traffic.

### Option A — Scheduled logical dump (minimum viable)

Add a cron job (host-side) that dumps the cluster to object storage:

```sh
# Daily at 02:07, keep 30 days; encrypt at rest in the bucket.
7 2 * * * docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump --clean --if-exists --no-owner --format=custom \
  -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  > "/backups/agencyos-$(date +\%F).dump"
```

### Option B — Continuous PITR (preferred for production)

1. Enable WAL archiving on the `postgres` service:
   - Mount an archive volume and set
     `archive_mode = on`, `archive_command = 'test ! -f /wal_archive/%f && cp %p /wal_archive/%f'`.
2. Take a base backup (`pg_basebackup`) nightly to object storage.
3. Retain WAL segments for ≥ 30 days to satisfy the RPO target.

## Restore procedure

1. **Stop** the backend + worker services so no writes race the restore:
   ```sh
   docker compose -f docker-compose.prod.yml stop backend worker
   ```
2. **Provision** a clean target database (new Supabase branch, or a fresh
   `pg_restore` destination).
3. **Restore** the most recent backup *before* the desired recovery point:
   ```sh
   # Logical dump:
   pg_restore --clean --if-exists --no-owner \
     -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" /backups/agencyos-YYYY-MM-DD.dump
   # PITR: use the platform's PITR restore to the target timestamp.
   ```
4. **Verify** row counts on critical tables (`organizations`, `users`,
   `leads`, `conversations`, `credentials`) against the pre-incident baseline.
5. **Rotate** all secrets touched by the incident (`SECRET_KEY`,
   `CREDENTIALS_ENC_KEY`, webhook secrets) and **re-key credentials** via the
   credential worker before resuming writes.
6. **Resume** services: `docker compose -f docker-compose.prod.yml start backend worker`.

## Credentials & encryption

- Credential values are envelope-encrypted with `CREDENTIALS_ENC_KEY`
  (versioned; see `CREDENTIAL_KEY_VERSION`). A backup of the database without
  the key is **unrecoverable** — store the key in the same secrets manager,
  and include it in any disaster-recovery drill.
- On any suspected key exposure, run the re-key sweep
  (`CREDENTIAL_REKEY_ENABLED=true`) after restore.

## Drill

Run a full restore from backup into a throwaway database **quarterly** and
record RTO. A backup that has never been restored is not verified.
