import { describe, expect, it } from "vitest";

import {
  AGENT_RUNTIME_DISABLED_REASON,
  AI_BUDGET_UNCONFIGURED_REASON,
  CAPABILITY_UNVERIFIED_REASON,
  FOUNDER_ASSISTANT_DISABLED_REASON,
  INTELLIGENCE_NARRATIVE_DISABLED_REASON,
  INTELLIGENCE_TRIAGE_DISABLED_REASON,
  ORG_AI_DISABLED_REASON,
  aiCapabilityNotices,
  aiRunDisabledReason,
  founderChatDisabledReason,
  proposalDecisionDisabledReason,
  triageDisabledReason,
} from "@/lib/ai-capabilities";
import type { AICapabilities } from "@/types";

const READY: AICapabilities = {
  agent_runtime_enabled: true,
  founder_assistant_enabled: true,
  intelligence_triage_enabled: true,
  intelligence_narrative_enabled: true,
  ai_execution_enabled: true,
  ai_budget_configured: true,
};

describe("ai capability disabled reasons", () => {
  it("fails closed when capabilities could not be verified", () => {
    expect(aiRunDisabledReason(null)).toBe(CAPABILITY_UNVERIFIED_REASON);
    expect(founderChatDisabledReason(null)).toBe(CAPABILITY_UNVERIFIED_REASON);
    expect(triageDisabledReason(null)).toBe(CAPABILITY_UNVERIFIED_REASON);
    expect(proposalDecisionDisabledReason(null)).toBe(CAPABILITY_UNVERIFIED_REASON);
  });

  it("allows every action when all capabilities are enabled", () => {
    expect(aiRunDisabledReason(READY)).toBeNull();
    expect(founderChatDisabledReason(READY)).toBeNull();
    expect(triageDisabledReason(READY)).toBeNull();
    expect(proposalDecisionDisabledReason(READY)).toBeNull();
  });

  it("aiRunDisabledReason reports each flag and checks kill switch, budget, runtime in order", () => {
    expect(aiRunDisabledReason({ ...READY, ai_execution_enabled: false })).toBe(
      ORG_AI_DISABLED_REASON
    );
    expect(aiRunDisabledReason({ ...READY, ai_budget_configured: false })).toBe(
      AI_BUDGET_UNCONFIGURED_REASON
    );
    expect(aiRunDisabledReason({ ...READY, agent_runtime_enabled: false })).toBe(
      AGENT_RUNTIME_DISABLED_REASON
    );
    expect(
      aiRunDisabledReason({
        ...READY,
        ai_execution_enabled: false,
        ai_budget_configured: false,
        agent_runtime_enabled: false,
      })
    ).toBe(ORG_AI_DISABLED_REASON);
  });

  it("founderChatDisabledReason reports kill switch, budget, and founder flag", () => {
    expect(founderChatDisabledReason({ ...READY, ai_execution_enabled: false })).toBe(
      ORG_AI_DISABLED_REASON
    );
    expect(founderChatDisabledReason({ ...READY, ai_budget_configured: false })).toBe(
      AI_BUDGET_UNCONFIGURED_REASON
    );
    expect(founderChatDisabledReason({ ...READY, founder_assistant_enabled: false })).toBe(
      FOUNDER_ASSISTANT_DISABLED_REASON
    );
    expect(
      founderChatDisabledReason({
        ...READY,
        ai_budget_configured: false,
        founder_assistant_enabled: false,
      })
    ).toBe(AI_BUDGET_UNCONFIGURED_REASON);
  });

  it("triageDisabledReason only depends on the triage flag", () => {
    expect(triageDisabledReason({ ...READY, intelligence_triage_enabled: false })).toBe(
      INTELLIGENCE_TRIAGE_DISABLED_REASON
    );
    // Reads stay available while triage is off; other flags do not gate it.
    expect(
      triageDisabledReason({
        ...READY,
        intelligence_triage_enabled: true,
        ai_execution_enabled: false,
        ai_budget_configured: false,
      })
    ).toBeNull();
  });

  it("proposalDecisionDisabledReason depends on the org kill switch", () => {
    expect(proposalDecisionDisabledReason({ ...READY, ai_execution_enabled: false })).toBe(
      ORG_AI_DISABLED_REASON
    );
    expect(
      proposalDecisionDisabledReason({
        ...READY,
        ai_execution_enabled: true,
        ai_budget_configured: false,
      })
    ).toBeNull();
  });

  it("aiCapabilityNotices lists every active blocker for read-only notices", () => {
    expect(aiCapabilityNotices(READY)).toEqual([]);
    expect(aiCapabilityNotices(null)).toEqual([CAPABILITY_UNVERIFIED_REASON]);
    const notices = aiCapabilityNotices({
      ...READY,
      ai_execution_enabled: false,
      ai_budget_configured: false,
      agent_runtime_enabled: false,
      founder_assistant_enabled: false,
      intelligence_triage_enabled: false,
      intelligence_narrative_enabled: false,
    });
    expect(notices).toEqual([
      ORG_AI_DISABLED_REASON,
      AI_BUDGET_UNCONFIGURED_REASON,
      AGENT_RUNTIME_DISABLED_REASON,
      FOUNDER_ASSISTANT_DISABLED_REASON,
      INTELLIGENCE_TRIAGE_DISABLED_REASON,
      INTELLIGENCE_NARRATIVE_DISABLED_REASON,
    ]);
  });
});
