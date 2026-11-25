// Static regressions for defects found in the final Batch 5/6 audit. Dynamic
// behavior is covered by service/SSR tests; these guards keep the fixing code
// shape in place without requiring a browser runtime in this environment.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

function source(relativePath: string): string {
  return readFileSync(resolve(process.cwd(), relativePath), "utf8");
}

function quotedValues(text: string): string[] {
  const values: string[] = [];
  const pattern = /"([^"]+)"/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) values.push(match[1]);
  return values;
}

function filterValues(text: string): string[] {
  const values: string[] = [];
  const pattern = /value:\s*"([^"]+)"/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) values.push(match[1]);
  return values;
}

function stringUnion(text: string, typeName: string): string[] {
  const match = text.match(new RegExp(`export type ${typeName}\\s*=\\s*([\\s\\S]*?);`));
  if (!match) throw new Error(`Missing exported type ${typeName}`);
  return quotedValues(match[1]);
}

describe("Batch 5 audit defect regressions", () => {
  it("invalidates AI polling when cancel succeeds", () => {
    const aiPage = source("src/app/(dashboard)/ai/page.tsx");
    expect(aiPage).toMatch(
      /const updated = await cancelAgentRun\(runId\);[\s\S]{0,300}setRunId\(null\);[\s\S]{0,120}setRun\(updated\);/
    );
    expect(aiPage).toContain("if (!active) return;");
  });

  it("keeps the modal focus trap and trigger restoration", () => {
    const modal = source("src/components/ui/modal.tsx");
    expect(modal).toContain("FOCUSABLE_SELECTOR");
    expect(modal).toContain("tabIndex={-1}");
    expect(modal).toContain("triggerRef.current?.focus()");
    expect(modal).toContain('if (e.key !== "Tab") return;');
  });

  it("does not fetch credentials for roles the backend would deny", () => {
    const credentials = source("src/app/(dashboard)/credentials/page.tsx");
    expect(credentials).toContain("shouldFetchCredentials");
    expect(credentials).toContain("if (!shouldFetchCredentials(!!session, canManage)) return;");
  });

  it("keeps every backend proposal and signal status available as a filter", () => {
    const proposalTypes = source("src/types/index.ts");
    const signalTypes = source("src/types/intelligence.ts");
    const proposals = source("src/app/(dashboard)/founder/proposals/page.tsx");
    const intelligence = source("src/app/(dashboard)/founder/intelligence/page.tsx");

    const proposalBlock = proposals.match(/const STATUSES:[^=]*=\s*\[([\s\S]*?)\];/);
    const signalBlock = intelligence.match(/const STATUS_FILTERS:[^=]*=\s*\[([\s\S]*?)\];/);
    expect(proposalBlock, "proposal STATUSES array").not.toBeNull();
    expect(signalBlock, "signal STATUS_FILTERS array").not.toBeNull();

    const expectedProposals = stringUnion(proposalTypes, "FounderProposalStatus").sort();
    const expectedSignals = stringUnion(signalTypes, "IntelligenceSignalStatus").sort();
    const actualProposals = quotedValues(proposalBlock![1])
      .filter((value) => value !== "all")
      .sort();
    const actualSignals = filterValues(signalBlock![1])
      .filter((value) => value !== "all")
      .sort();

    expect(actualProposals, "proposal filter statuses").toEqual(expectedProposals);
    expect(actualSignals, "intelligence filter statuses").toEqual(expectedSignals);
  });

  it("uses Zod 4 top-level email format instead of deprecated string .email()", () => {
    const auth = source("src/lib/validation/auth.ts");
    const marketing = source("src/lib/validation/marketing.ts");
    expect(auth).not.toContain(".email(EMAIL_MESSAGE)");
    expect(marketing).not.toContain(".email(EMAIL_MESSAGE)");
    expect(auth).toContain("z.email({ error: EMAIL_MESSAGE })");
    expect(marketing).toContain("z.email({ error: EMAIL_MESSAGE })");
  });
});
