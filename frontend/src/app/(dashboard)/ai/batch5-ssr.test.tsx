// Static-markup coverage for Batch 5 AI routes. This test renders the real
// client page components to HTML in a node environment with mocked auth and
// services. It verifies the initial, fail-closed permission/capability state;
// it does NOT verify hydration, event handlers, or browser interactivity.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { Session } from "@/lib/session";
import type { User, UserRole } from "@/types";

const state = vi.hoisted(() => ({
  session: null as Session | null,
}));

vi.mock("@/hooks/use-auth", () => ({ useAuth: () => state.session }));

vi.mock("@/services/ai", () => ({
  getAICapabilities: vi.fn(async () => null),
  getAISettings: vi.fn(async () => ({
    provider: "openai",
    model: "gpt-4o-mini",
    overridden: false,
    kill_switch: false,
  })),
  getAgentRun: vi.fn(),
  cancelAgentRun: vi.fn(),
  dispatchDraft: vi.fn(),
  runBrain: vi.fn(),
  listAITools: vi.fn(async () => []),
  updateAISettings: vi.fn(),
}));

vi.mock("@/services/leads", () => ({
  listLeads: vi.fn(async () => ({ items: [], total: 0 })),
}));

import AIPage, { AIRunControls } from "@/app/(dashboard)/ai/page";
import AISettingsPage from "@/app/(dashboard)/ai/settings/page";
import { CAPABILITY_UNVERIFIED_REASON, ORG_AI_DISABLED_REASON } from "@/lib/ai-capabilities";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Test User",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function setRole(role: UserRole): void {
  state.session = { accessToken: "token", expiresIn: 3600, user: { ...USER, role } };
}

function buttonTag(html: string, label: string): string | null {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return html.match(new RegExp(`<button[^>]*>[^<]*${escaped}[^<]*</button>`))?.[0] ?? null;
}

function isDisabled(tag: string | null): boolean {
  return !!tag && /\sdisabled(?:="")?(?:\s|>)/.test(tag);
}

describe("/ai static markup", () => {
  it("viewer gets the permission panel with no run or cancel controls", () => {
    setRole("viewer");
    const html = renderToStaticMarkup(<AIPage />);

    expect(html).toContain("You do not have permission to run AI.");
    expect(html).not.toContain(">Run AI</button>");
    expect(html).not.toContain(">Re-run AI</button>");
    expect(html).not.toContain(">Cancel</button>");
  });

  it("member cannot cancel and cannot run while capabilities are unverified", () => {
    setRole("member");
    const html = renderToStaticMarkup(<AIPage />);

    expect(html).not.toContain(">Cancel</button>");
    const run = buttonTag(html, "Run AI");
    expect(run).not.toBeNull();
    expect(isDisabled(run)).toBe(true);
    expect(html).toContain(CAPABILITY_UNVERIFIED_REASON);
  });

  it("admin run controls hide Cancel until a run is non-terminal and show capability reasons", () => {
    setRole("admin");
    const initial = renderToStaticMarkup(<AIPage />);
    expect(initial).not.toContain(">Cancel</button>");

    const blocked = renderToStaticMarkup(
      <AIRunControls
        canRun={false}
        canCancel
        busy={false}
        hasRun={false}
        nonTerminal={false}
        disabledReason={ORG_AI_DISABLED_REASON}
        onRun={() => undefined}
        onCancel={() => undefined}
      />
    );
    expect(isDisabled(buttonTag(blocked, "Run AI"))).toBe(true);
    expect(blocked).toContain(ORG_AI_DISABLED_REASON);

    const running = renderToStaticMarkup(
      <AIRunControls
        canRun
        canCancel
        busy={false}
        hasRun
        nonTerminal
        disabledReason={null}
        onRun={() => undefined}
        onCancel={() => undefined}
      />
    );
    expect(buttonTag(running, "Cancel")).not.toBeNull();
    // A second run cannot be started while the current one is non-terminal.
    expect(isDisabled(buttonTag(running, "Re-run AI"))).toBe(true);

    const ready = renderToStaticMarkup(
      <AIRunControls
        canRun
        canCancel
        busy={false}
        hasRun
        nonTerminal={false}
        disabledReason={null}
        onRun={() => undefined}
        onCancel={() => undefined}
      />
    );
    expect(isDisabled(buttonTag(ready, "Re-run AI"))).toBe(false);
    expect(ready).not.toContain(">Cancel</button>");

    const memberRunning = renderToStaticMarkup(
      <AIRunControls
        canRun
        canCancel={false}
        busy={false}
        hasRun
        nonTerminal
        disabledReason={null}
        onRun={() => undefined}
        onCancel={() => undefined}
      />
    );
    expect(memberRunning).not.toContain(">Cancel</button>");
  });
});

describe("/ai/settings static markup", () => {
  it("shows the permission panel to non-managers", () => {
    setRole("member");
    const html = renderToStaticMarkup(<AISettingsPage />);

    expect(html).toContain("You do not have permission to manage AI settings.");
    expect(html).not.toContain("Capability status");
    expect(html).not.toContain(">Save</button>");
  });

  it("shows read-only capability notices to admins and keeps save/clear controls", () => {
    setRole("admin");
    const html = renderToStaticMarkup(<AISettingsPage />);

    expect(html).toContain("Capability status");
    expect(html).toContain(CAPABILITY_UNVERIFIED_REASON);
    expect(html).toContain(">Save</button>");
    expect(html).toContain(">Clear override</button>");
  });
});
