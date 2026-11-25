# AgencyOS — Dependency Risk Acceptance

## Backend (pip)

Scan: `pip-audit` against the installed backend environment (run 2026-10-30). Result: **no known vulnerabilities reported** in the installed backend dependency set at scan time. Backend requirements are pinned (`requirements.txt` / `requirements-dev.txt`); no action required.

## Frontend (npm)

**Current status (2026-11-22):** `npm audit --audit-level=moderate` exits 0 with **0 vulnerabilities**. The uncommitted local `frontend/package-lock.json` in the reviewed worktree pins `zod@4.6.7`, `vite@8.2.4`, `vitest@4.1.12`, `@vitest/mocker@4.1.12`, and the `@typescript-eslint` 8.73.0 chain that resolves the nested `minimatch` advisory. It is not part of the committed baseline and must be staged explicitly if accepted. CI now uses `npm ci`, checks that the lockfile is unchanged, and fails on any moderate-or-higher advisory.

### Historical 2026-10-30 scan

Scan: `npm audit` (2026-10-30). Result: **2 high, 2 moderate, 0 critical, 0 low**.

| Package | Severity | Advisory | Range | Fixed in | Classification | Historical decision |
|---|---|---|---|---|---|---|
| `zod` | high | GHSA-mrhx-c7xc-m3w5 (memory exhaustion on oversized constrained collections) | `<4.6.6` | 4.x | production validation code; vulnerable array path not used | Deferred historically; now upgraded to 4.6.7. |
| `vite` | high (moderate/low sub-advisories) | GHSA-587h-7wmj-h5pm and related launch-editor advisories | `8.2.0–8.2.3` | patched 8.x | dev-only (build tooling) | Pinned to 8.2.4. |
| `vitest` | moderate | GHSA-82fw-gwwq-j7x9 (path traversal via @vitest/mocker) | `>=2.1.0 <4.1.11` | 4.x | dev-only (test runner) | Pinned to 4.1.12. |
| `@vitest/mocker` | moderate | GHSA-82fw-gwwq-j7x9, GHSA-qxg6-89mg-rqv8 | `>=2.1.0 <4.1.11/4.1.12` | 4.x | dev-only (test runner) | Pinned to 4.1.12. |

### Resolved risk summary

- The `zod` upgrade is complete and covered by `frontend/src/lib/dependency-security.test.ts`; the previous claim that validation code was "not reachable" was too strong, but the vulnerable `$ZodArray` path was not used.
- The transitive `minimatch` advisory is resolved by the compatible `@typescript-eslint` 8.73.0 patch line; the prior claim that no compatible patch existed is superseded.
- No backend advisories were reported in the historical scan.
- There is no remaining accepted frontend advisory at moderate-or-higher severity.

## Action items (owner)

1. Keep `npm ci`, lockfile-diff verification, and `npm audit --audit-level=moderate` enabled in CI.
2. Re-run the audit after every dependency update and review lockfile diffs deliberately.
3. Reassess this document before public launch if the dependency set changes.
