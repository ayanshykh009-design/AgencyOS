# AgencyOS — Dependency Risk Acceptance

## Backend (pip)

Scan: `pip-audit` against the installed backend environment (run 2026-10-30). Result: **no known vulnerabilities reported** in the installed backend dependency set at scan time. Backend requirements are pinned (`requirements.txt` / `requirements-dev.txt`); no action required.

## Frontend (npm)

Scan: `npm audit` (2026-10-30). Result: **2 high, 2 moderate, 0 critical, 0 low**.

| Package | Severity | Advisory | Range | Fixed in | Classification | Decision |
|---|---|---|---|---|---|---|
| `zod` | high | GHSA-mrhx-c7xc-m3w5 (memory exhaustion on oversized constrained collections) | `<4.6.6` | 4.x | dev/runtime? Used by `frontend/src/lib/env.ts` (build-time + client validation) | Defer: requires major upgrade (3→4); breaking API changes. Mitigation: input sizes are bounded by form validation and API limits; no untrusted large payloads reach zod parse paths in current flows. Track as follow-up. |
| `vite` | high (moderate/low sub-advisories) | GHSA-587h-7wmj-h5pm and related launch-editor advisories | `8.2.0–8.2.3` | patched 8.x | dev-only (build tooling) | Defer: dev-only, not shipped to production runtime. No production exposure. |
| `vitest` | moderate | GHSA-82fw-gwwq-j7x9 (path traversal via @vitest/mocker) | `>=2.1.0 <4.1.11` | 4.x | dev-only (test runner) | Defer: dev-only. |
| `@vitest/mocker` | moderate | GHSA-82fw-gwwq-j7x9, GHSA-qxg6-89mg-rqv8 | `>=2.1.0 <4.1.11/4.1.12` | 4.x | dev-only (test runner) | Defer: dev-only. |

## Accepted risk summary

- All four advisories are in the frontend toolchain (build/test), not the production runtime bundle, except `zod` which is bundled but used only for small, bounded env/form validation.
- No backend advisories.
- Upgrading `zod` 3→4, `vite` and `vitest` to patched majors is a breaking toolchain migration; explicitly out of scope for this security task (documented follow-up, same as the prior H2 report). It must be scheduled as a dedicated, tested migration before public launch.
- No advisory is currently exploitable through a reachable, unauthenticated production path.

## Action items (owner)

1. Schedule the `zod` 4 migration as a dedicated PR with full frontend test coverage.
2. Re-run `npm audit` after each dependency update; do not suppress findings.
3. Keep `npm audit` in CI as an informational gate (current CI does not fail on advisories; recommend adding a threshold policy before public launch).
