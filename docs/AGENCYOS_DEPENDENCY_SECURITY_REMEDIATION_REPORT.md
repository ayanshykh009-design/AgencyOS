# AgencyOS — Isolated Dependency Security Remediation Report

**Date:** 2026-11-22  
**Worktree:** `C:\Users\awan\.local\share\opencode\worktree\0ae653\security-advisory-audit`  
**Base HEAD:** `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0`  
**Original working tree:** `D:\AgencyOS` — not modified by this audit  
**Protected migration:** `database/migrations/0016_search_trigram_indexes.sql` — not opened, read, diffed, hashed, staged or modified

---

## 1. Scope and isolation

A dedicated Git worktree was created from the exact requested HEAD. All dependency inspection, remediation, tests and documentation were performed only inside that worktree. The original Batch 5/6 working tree was left in place with its pre-existing user-owned modifications and untracked artifacts. No commit, push, merge, deployment, reset, clean, stash or PR change was performed.

The frozen dependency policy was preserved: no canary, prerelease or major upgrade was applied merely to silence a notification. An upgrade was made only where a specific GitHub advisory applied to the installed version and a stable, compatible, same-line patch existed.

---

## 2. Exact installed versions

Source of truth: `frontend/package.json`, `frontend/package-lock.json` and `npm ls`.

| Package | Declared / installed version | Notes |
|---|---|---|
| `next` | `16.4.6` | Direct dependency; current stable registry version. |
| `eslint-config-next` | `16.4.0` | Direct devDependency; latest registry version is `16.4.6`, but `16.4.0` has no advisory and no peer contract requiring an exact Next.js match. |
| `@next/eslint-plugin-next` | `16.4.0` | Transitive from `eslint-config-next`; no advisory. |
| `@next/env` and `@next/swc-*` | `16.4.6` | Matched to `next@16.4.6`. |
| `react` / `react-dom` | `^19.0.0` range, resolved from lockfile | Satisfy `next@16.4.6` peer range. |
| `typescript` | `5.x` resolved from lockfile | Satisfies `eslint-config-next@16.4.0` peer requirement `>=3.3.1`. |
| `eslint` | `9.39.5` resolved | Satisfies `eslint-config-next@16.4.0` peer requirement `>=9.0.0`. |
| `vitest` | `4.1.10` → **`4.1.12`** | Patched in isolation. |
| `@vitest/mocker` | `4.1.10` → **`4.1.12`** | Patched transitively with Vitest. |
| `vite` | `8.2.0` → **`8.2.4`** | Pinned through `overrides` to the patched 8.2 line. |
| `zod` | `3.25.76` | Direct dependency; advisory present but not reachable in this app (see §5). |
| `minimatch` | `3.1.5` and `10.2.6` | Dev-tooling transitive versions; advisory present for `10.2.6` (see §5). |

---

## 3. `npm audit --json`

### Baseline

The first `npm audit --json` against the unmodified lockfile failed at the npm registry endpoint:

```text
npm warn audit 400 Bad Request - POST https://registry.npmjs.org/-/npm/v1/security/audits/quick
npm error audit endpoint returned an error
```

This was a tooling/registry endpoint failure, not a clean scan result.

### Post-lock-refresh scan

After refreshing the lockfile in the isolated worktree, `npm audit --json` completed successfully and reported:

- **8 vulnerabilities**: 7 moderate, 1 high, 0 critical.
- Full dependency count: 515.
- `npm audit --omit=dev --json`: **1 high** (`zod`), 0 moderate, 0 critical.
- No Vitest, `@vitest/mocker` or Vite advisories remained after the patch.

The remaining entries are:

1. `minimatch@10.2.6` plus its `@typescript-eslint/*` dependents — 7 moderate findings from GHSA-g3hv-75wg-m249.
2. `zod@3.25.76` — 1 high finding from GHSA-mrhx-c7xc-m3w5.

`npm audit --json` exits non-zero when findings exist; the scan itself succeeded.

---

## 4. Dependency tree and affected paths

Relevant installed paths from `npm ls`:

```text
next@16.4.6
eslint-config-next@16.4.0
  ├─ @next/eslint-plugin-next@16.4.0
  ├─ eslint-plugin-react-hooks@7.1.1
  │   └─ zod@3.25.76
  └─ typescript-eslint@8.65.0
      └─ @typescript-eslint/typescript-estree@8.65.0
          └─ minimatch@10.2.6

vitest@4.1.12
  ├─ @vitest/mocker@4.1.12
  │   └─ vite@8.2.4 deduped
  └─ vite@8.2.4 overridden

zod@3.25.76 (direct)
```

Lockfile path analysis confirmed the same chains before remediation:

- `vitest -> @vitest/mocker`
- `vitest -> vite`
- `eslint-config-next -> typescript-eslint -> @typescript-eslint/eslint-plugin -> @typescript-eslint/type-utils -> @typescript-eslint/typescript-estree -> minimatch`
- `eslint-config-next -> eslint-plugin-react-hooks -> zod`

---

## 5. GitHub Security Advisory review

### Next.js

The GitHub Advisory API was queried with `ecosystem=npm&affects=next` and returned **84 advisories**. Each vulnerable version range was evaluated against the installed `next@16.4.6`.

**Applicable advisories: 0.**

The newest November 2026 advisories (GHSA-f3mh-rxg3-f5g2, GHSA-7qx7-33qx-rqx2, GHSA-pc58-hwjq-p385, GHSA-rhh4-g77r-r9qj, GHSA-vvgp-ww4w-46vf, GHSA-vc7v-qv4w-wrv8) affect `next` ranges ending at `<= 16.4.4` and were first patched in `16.4.5`. The installed `16.4.6` is above that patch line. Older critical advisories affect ranges such as `<=16.4.0` or `<16.3.8`, also not applicable.

**Decision:** no Next.js upgrade. `16.4.6` is already the current stable registry version; no canary, prerelease or major upgrade is justified.

### `eslint-config-next` and `@next/eslint-plugin-next`

GitHub Advisory API queries for both package names returned empty result sets (`[]`). No security advisory applies to `eslint-config-next@16.4.0` or `@next/eslint-plugin-next@16.4.0`.

Compatibility was verified from registry metadata and the lockfile:

- `eslint-config-next@16.4.0` peers: `eslint >=9.0.0`, `typescript >=3.3.1` (optional).
- Installed `eslint@9.39.5` and TypeScript 5.x satisfy those peers.
- No peer dependency requires an exact version match with `next`.
- npm registry current stable is `eslint-config-next@16.4.6`, but the difference is a version-alignment opportunity, not a security patch.

**Decision:** no upgrade. Changing it would be a non-security version bump outside the remediation rule.

### Full OSV/GitHub cross-check

All unique npm package/version pairs in the lockfile were queried through OSV (`querybatch`) and candidate GHSA IDs were resolved through the GitHub Advisory API.

- Before remediation: **502 package/version pairs queried, 5 matched** (`minimatch`, `@vitest/mocker`, `vite`, `vitest`, `zod`).
- After remediation: **504 package/version pairs queried, 2 matched** (`minimatch`, `zod`).

#### Remediated advisories

| Advisory | Package / installed version | Severity | Patched version | Action |
|---|---|---:|---|---|
| GHSA-82fw-gwwq-j7x9 | `vitest` / `@vitest/mocker` `4.1.10` | Medium | `4.1.11` | Upgraded to `4.1.12`, covering this and the following advisory. |
| GHSA-qxg6-89mg-rqv8 | `@vitest/mocker` `4.1.10` | Medium | `4.1.12` | Upgraded to `4.1.12`. |
| GHSA-587h-7wmj-h5pm | `vite` `8.2.0` | High | `8.2.4` | Pinned `vite@8.2.4`. |
| GHSA-698v-4r3x-3vcv | `vite` `8.2.0` | Medium | `8.2.4` | Pinned `vite@8.2.4`. |
| GHSA-9jrq-w75r-8gcw | `vite` `8.2.0` | Low | `8.2.4` | Pinned `vite@8.2.4`. |
| GHSA-r825-w8mm-5pxw | `vite` `8.2.0` | Medium | `8.2.4` | Pinned `vite@8.2.4`. |
| GHSA-rq7h-c2jc-7f22 | `vite` `8.2.0` | Medium | `8.2.4` | Pinned `vite@8.2.4`. |
| GHSA-vfpm-58rq-9qcg | `vite` `8.2.0` | Medium | `8.2.4` | Pinned `vite@8.2.4`. |

These are development-tooling advisories, but each had a specific applicable version range and a stable patch within the same major/minor line, so remediation was applied.

#### Documented, not upgraded

| Advisory | Package / version | Why no upgrade |
|---|---|---|
| GHSA-g3hv-75wg-m249 | `minimatch@10.2.6` | Version is in range `>=7.0.0 <11.0.1`, but the only patched line is `11.0.1`, a major-version jump. The affected copy is dev-only, reachable through ESLint/TypeScript-ESLint static configuration, with no untrusted glob-pattern input from this application. No compatible same-line patch exists, and upgrading the whole ESLint chain would be a breaking change unrelated to a reachable vulnerability. |
| GHSA-mrhx-c7xc-m3w5 | `zod@3.25.76` | Version is in range `<4.6.6`; the fix is a major upgrade to `4.6.6`/`4.6.7`. The advisory requires an array schema without a length constraint (`handleArrayResult` in `$ZodArray`). This application uses `z.object`, `z.string`, `z.enum`, `z.boolean`, `.refine`, `.superRefine` and `.transform` only; there is no `z.array` or `ZodArray` usage in `frontend/src`. The vulnerable code path is therefore not reachable. No major upgrade was applied merely to silence the audit. |

---

## 6. Changes made in the isolated worktree

1. `frontend/package.json`
   - `vitest`: `4.1.10` → `4.1.12`.
   - Added `overrides.vite`: `8.2.4`.
2. `frontend/package-lock.json`
   - Regenerated with `npm install --package-lock-only --ignore-scripts --legacy-peer-deps`.
   - `vitest`, all `@vitest/*` internal packages and `@vitest/mocker` resolved to `4.1.12`.
   - `vite` resolved to `8.2.4` via override.
3. `frontend/src/lib/dependency-security.test.ts`
   - New regression test asserting the audited `next`/`eslint-config-next` versions remain unchanged and the patched `vitest`/`@vitest/mocker`/`vite` versions are locked.
4. This report.

No application runtime source, backend code, schema, migration, RLS policy or CI configuration was changed. Regenerating the lockfile for the patched Vite line also refreshed Vite's allowed transitive toolchain entries (for example `rolldown` bindings and `@napi-rs`/`@oxc-project` helpers) within their existing semver ranges; no direct runtime dependency was changed.

The lock refresh required `--legacy-peer-deps` because npm 10.9.8 hit an Arborist peer-resolution error while resolving optional Vitest browser/coverage peer packages. The resulting lockfile was installed and all application gates passed.

---

## 7. Verification

### Dependency security scanning after remediation

- `npm audit --json`: 8 findings remain — 7 moderate (`minimatch` chain), 1 high (`zod`); no Vitest/Vite findings.
- `npm audit --omit=dev --json`: 1 high (`zod`) only.
- OSV/GitHub cross-check: 504 package/version pairs queried, 2 matched (`minimatch`, `zod`); Vitest/Vite no longer matched.
- `npm ls next eslint-config-next vitest @vitest/mocker vite zod minimatch --all` confirmed `next@16.4.6`, `eslint-config-next@16.4.0`, `vitest@4.1.12`, `@vitest/mocker@4.1.12`, `vite@8.2.4` and `zod@3.25.76`.

### Frontend gates (isolated worktree baseline)

- `npm test`: **43 test files, 306 tests passed** with Vitest `4.1.12`, including the new dependency-security regression.
- `npm run typecheck`: clean.
- `npm run lint`: 0 errors; 1 pre-existing `postcss.config.mjs` anonymous-default-export warning.
- `npm run build`: successful production build, 38 pages generated with Next.js `16.4.6`.
- `npx prettier --check package.json package-lock.json src/lib/dependency-security.test.ts`: all matched files use Prettier style.

The worktree is based on committed HEAD and therefore contains the repository's committed test set, not the uncommitted Batch 5/6 test additions in the original working tree.

---

## 8. Preservation and prohibited actions

- Worktree created from `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0`.
- Original `D:\AgencyOS` working tree was not edited by this audit.
- No commit, push, merge, deploy, reset, clean, stash or PR change occurred.
- Protected migration `database/migrations/0016_search_trigram_indexes.sql` was not accessed.
- No direct canary, prerelease or major dependency upgrade was applied. The unavoidable transitive refresh for patched Vite retained Vite's existing optional WASI-helper pattern (`@emnapi` alpha → beta), but that was not an upgrade chosen to suppress an advisory.

---

## 9. Conclusion

The Next.js security notification did not correspond to an applicable GitHub advisory for the installed `next@16.4.6`; no Next.js upgrade was justified. `eslint-config-next@16.4.0` has no advisory and remains compatible with the installed ESLint/TypeScript versions, so it was also left unchanged.

Specific applicable advisories did exist for the development test toolchain. Those were remediated with stable same-line patches: Vitest and `@vitest/mocker` to `4.1.12`, and Vite to `8.2.4`. A regression test and a full local frontend gate run verified the change. Remaining audit findings are either dev-only with no same-line patch (`minimatch`) or version-applicable but not reachable because the vulnerable schema feature is unused (`zod`); both are documented rather than silently force-upgraded.
