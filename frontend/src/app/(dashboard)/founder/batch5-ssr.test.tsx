// Static-markup coverage for Batch 5 founder routes. Renders the real client
// page components and exported testable controls to HTML in node with mocked
// auth/services. Hydration, click handlers, and browser interactivity are NOT
// verified here.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Session } from "@/lib/session";
import type { User, UserRole } from "@/types";
import type { IntelligenceSignal } from "@/types/intelligence";

const state = vi.hoisted(() => ({
  session: null as Session | null,
  signals: {
    data: { items: [], total: 0 } as { items: unknown[]; total: number } | undefined,
    isLoading: false,
    isError: false,
    error: undefined as Error | undefined,
    refetch: undefined as (() => void) | undefined,
  },
}));

beforeEach(() => {
  state.session = null;
  state.signals = {
    data: { items: [], total: 0 },
    isLoading: false,
    isError: false,
    error: undefined,
    refetch: undefined,
  };
});

vi.mock("@/hooks/use-auth", () => ({ useAuth: () => state.session }));

vi.mock("@/services/ai", () => ({
  getAICapabilities: vi.fn(async () => null),
  getAISettings: vi.fn(),
  getAgentRun: vi.fn(),
  cancelAgentRun: vi.fn(),
  dispatchDraft: vi.fn(),
  runBrain: vi.fn(),
  updateAISettings: vi.fn(),
}));

vi.mock("@/services/founder", () => ({
  listFounderConversations: vi.fn(async () => ({ items: [], total: 0 })),
  getFounderConversation: vi.fn(),
  deleteFounderConversation: vi.fn(),
  sendFounderMessage: vi.fn(),
  listFounderProposals: vi.fn(async () => ({ items: [], total: 0 })),
  decideFounderProposal: vi.fn(),
}));

vi.mock("@/services/intelligence", () => ({
  useSignals: () => state.signals,
  useSignalSummary: () => ({ data: undefined }),
  useAcknowledgeSignal: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRunTriage: () => ({ mutateAsync: vi.fn(), isPending: false, data: undefined }),
}));

import FounderChatPage, {
  ConversationListItem,
  FounderComposer,
  ProposalCard,
} from "@/app/(dashboard)/founder/page";
import FounderIntelligencePage, {
  SignalCard,
  TriageControl,
} from "@/app/(dashboard)/founder/intelligence/page";
import FounderProposalsPage, {
  ProposalDecisionControls,
} from "@/app/(dashboard)/founder/proposals/page";
import {
  CAPABILITY_UNVERIFIED_REASON,
  FOUNDER_ASSISTANT_DISABLED_REASON,
  INTELLIGENCE_TRIAGE_DISABLED_REASON,
  ORG_AI_DISABLED_REASON,
} from "@/lib/ai-capabilities";
import type { FounderConversation, FounderProposal } from "@/types";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "manager@example.com",
  full_name: "Test User",
  role: "manager",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const CONVERSATION: FounderConversation = {
  conversation_id: "c-1",
  title: "Pipeline review",
  is_archived: false,
};

const PROPOSAL: FounderProposal = {
  id: "p-1",
  action_type: "create_task",
  title: "Create follow-up task",
  status: "proposed",
  payload: {},
};

const SIGNAL: IntelligenceSignal = {
  id: "s-1",
  organization_id: USER.organization_id,
  signal_category: "pipeline_risk",
  source_type: "pipeline_fact",
  source_row_id: null,
  title: "Pipeline risk",
  summary: "Deals stalled",
  severity: "high",
  business_impact: {},
  priority_score: 0.75,
  priority_components: {},
  evidence: [],
  recommended_next_step: null,
  confidence: "high",
  status: "active",
  first_seen_at: "2026-08-01T00:00:00Z",
  last_triaged_at: null,
  acknowledged_by_user_id: null,
  acknowledged_at: null,
  last_notified_at: null,
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

describe("founder chat static markup", () => {
  it("non-managers see no Send, Delete, Approve, or Deny controls", () => {
    setRole("member");
    const page = renderToStaticMarkup(<FounderChatPage />);

    expect(page).toContain("Founder assistant");
    expect(page).not.toContain("<textarea");
    expect(page).not.toContain(">Send</button>");
    expect(page).not.toContain('aria-label="Delete conversation"');

    const item = renderToStaticMarkup(
      <ConversationListItem
        conversation={CONVERSATION}
        canManage={false}
        active={false}
        onOpen={() => undefined}
        onDelete={() => undefined}
      />
    );
    expect(item).toContain("Pipeline review");
    expect(item).not.toContain('aria-label="Delete conversation"');

    const card = renderToStaticMarkup(
      <ProposalCard
        proposal={PROPOSAL}
        canManage={false}
        decisionDisabledReason={null}
        onDecide={() => undefined}
      />
    );
    expect(card).toContain("Create follow-up task");
    expect(card).not.toContain(">Approve</button>");
    expect(card).not.toContain(">Deny</button>");
  });

  it("uses sibling native buttons for open and delete with AA-safe muted text", () => {
    const item = renderToStaticMarkup(
      <ConversationListItem
        conversation={CONVERSATION}
        canManage
        active={false}
        onOpen={() => undefined}
        onDelete={() => undefined}
      />
    );

    expect(item).toContain('aria-label="Delete conversation"');
    expect(item.match(/<button/g)).toHaveLength(2);
    expect(item).not.toContain('role="button"');
    expect(item).not.toContain("text-gray-400");
  });

  it("shows a loading list instead of a false empty state on first render", () => {
    setRole("manager");
    const page = renderToStaticMarkup(<FounderChatPage />);

    expect(page).toContain("Loading conversations…");
    expect(page).not.toContain("No conversations yet.");
  });

  it("disables both decision buttons while a decision is in flight", () => {
    const card = renderToStaticMarkup(
      <ProposalCard
        proposal={PROPOSAL}
        canManage
        decisionDisabledReason={null}
        busy
        onDecide={() => undefined}
      />
    );

    expect(isDisabled(buttonTag(card, "Approve"))).toBe(true);
    expect(isDisabled(buttonTag(card, "Deny"))).toBe(true);
  });

  it("managers see a disabled Send with a truthful reason when the assistant is unavailable", () => {
    setRole("manager");
    const composer = renderToStaticMarkup(
      <FounderComposer
        busy={false}
        disabledReason={FOUNDER_ASSISTANT_DISABLED_REASON}
        draft="hello"
        onDraftChange={() => undefined}
        onSend={() => undefined}
      />
    );

    expect(isDisabled(buttonTag(composer, "Send"))).toBe(true);
    expect(composer).toContain(FOUNDER_ASSISTANT_DISABLED_REASON);

    // On first render the capability state is unverified: fail closed.
    const page = renderToStaticMarkup(<FounderChatPage />);
    expect(isDisabled(buttonTag(page, "Send"))).toBe(true);
    expect(page).toContain(CAPABILITY_UNVERIFIED_REASON);
  });
});

describe("founder proposals static markup", () => {
  it("shows loading before rendering a false empty-filter state", () => {
    setRole("manager");
    const page = renderToStaticMarkup(<FounderProposalsPage />);

    expect(page).toContain("Loading proposals…");
    expect(page).not.toContain("No proposals match this filter.");
  });

  it("keeps reads available and disables decisions when the org kill switch is on", () => {
    setRole("manager");
    const page = renderToStaticMarkup(<FounderProposalsPage />);
    expect(page).toContain("Founder actions");
    expect(page).toContain(CAPABILITY_UNVERIFIED_REASON);

    const blocked = renderToStaticMarkup(
      <ProposalDecisionControls
        canManage
        disabledReason={ORG_AI_DISABLED_REASON}
        busy={false}
        onDecide={() => undefined}
      />
    );
    expect(blocked).toBe("");

    const card = renderToStaticMarkup(
      <ProposalCard
        proposal={PROPOSAL}
        canManage
        decisionDisabledReason={ORG_AI_DISABLED_REASON}
        onDecide={() => undefined}
      />
    );
    expect(card).toContain(ORG_AI_DISABLED_REASON);
    expect(card).not.toContain(">Approve</button>");
    expect(card).not.toContain(">Deny</button>");

    const allowed = renderToStaticMarkup(
      <ProposalDecisionControls
        canManage
        disabledReason={null}
        busy={false}
        onDecide={() => undefined}
      />
    );
    expect(buttonTag(allowed, "Approve")).not.toBeNull();
    expect(buttonTag(allowed, "Deny")).not.toBeNull();
  });
});

describe("founder intelligence static markup", () => {
  it("renders a real error state with retry instead of a false empty feed", () => {
    setRole("manager");
    state.signals = {
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Signals service unavailable"),
      refetch: vi.fn(),
    };

    const page = renderToStaticMarkup(<FounderIntelligencePage />);

    expect(page).toContain("Signals service unavailable");
    expect(page).toContain(">Retry</button>");
    expect(page).not.toContain("No signals in this view.");
  });

  it("hides triage and signal transitions from non-managers but keeps reads", () => {
    setRole("member");
    const page = renderToStaticMarkup(<FounderIntelligencePage />);

    expect(page).toContain("Intelligence signals");
    expect(page).not.toContain("Run triage now");

    const card = renderToStaticMarkup(
      <SignalCard signal={SIGNAL} canManage={false} onTransition={() => undefined} busy={false} />
    );
    expect(card).toContain("Pipeline risk");
    expect(card).not.toContain(">Acknowledge</button>");
    expect(card).not.toContain(">Dismiss</button>");
  });

  it("shows a disabled, truthful Run triage control to managers when triage is unavailable", () => {
    setRole("manager");
    const control = renderToStaticMarkup(
      <TriageControl
        disabledReason={INTELLIGENCE_TRIAGE_DISABLED_REASON}
        isPending={false}
        onRun={() => undefined}
      />
    );

    expect(isDisabled(buttonTag(control, "Run triage now"))).toBe(true);
    expect(control).toContain(INTELLIGENCE_TRIAGE_DISABLED_REASON);

    const page = renderToStaticMarkup(<FounderIntelligencePage />);
    expect(isDisabled(buttonTag(page, "Run triage now"))).toBe(true);
    expect(page).toContain(CAPABILITY_UNVERIFIED_REASON);

    const ackAllowed = renderToStaticMarkup(
      <SignalCard signal={SIGNAL} canManage onTransition={() => undefined} busy={false} />
    );
    expect(buttonTag(ackAllowed, "Acknowledge")).not.toBeNull();
    expect(buttonTag(ackAllowed, "Dismiss")).not.toBeNull();
  });
});
