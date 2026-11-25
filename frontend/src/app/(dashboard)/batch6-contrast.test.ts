// Regression guard for the real-browser accessibility defect found during
// final QA: 12px muted metadata text used `text-gray-400` (#9ca3af) on white,
// which Lighthouse/axe reported at 2.53:1 against the required 4.5:1.
// Batch 6 surfaces must keep muted metadata at the darker AA-safe token.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const BATCH5_SURFACES = [
  "src/app/(dashboard)/ai/page.tsx",
  "src/app/(dashboard)/founder/page.tsx",
  "src/app/(dashboard)/founder/intelligence/page.tsx",
];

const BATCH6_SURFACES = [
  "src/app/(dashboard)/workflows/page.tsx",
  "src/app/(dashboard)/workflows/[id]/page.tsx",
  "src/app/(dashboard)/triggers/page.tsx",
  "src/app/(dashboard)/executions/page.tsx",
  "src/app/(dashboard)/credentials/page.tsx",
  "src/app/(dashboard)/deliveries/page.tsx",
  "src/components/automation/automation-states.tsx",
  // Shared components reachable from the six routes also carry muted text.
  "src/components/ui/field.tsx",
  "src/components/ui/modal.tsx",
  "src/components/layouts/site-nav.tsx",
];

describe("Batch 5 + Batch 6 muted-text contrast", () => {
  it("does not use the low-contrast gray-400 token on in-scope surfaces", () => {
    for (const surface of [...BATCH5_SURFACES, ...BATCH6_SURFACES]) {
      const source = readFileSync(resolve(process.cwd(), surface), "utf8");
      expect(source, surface).not.toContain("text-gray-400");
    }
  });
});
