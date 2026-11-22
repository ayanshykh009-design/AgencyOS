// Pure, backend-authoritative capability gating for Batch 5 pages.
//
// These helpers never fetch and never mutate state. They turn the non-secret
// boolean surface from GET /ai/capabilities into truthful disabled reasons.
// A `null` capability object means the state could not be verified, so every
// capability-dependent action fails closed.
//
// Precedence (most fundamental precondition first): organization kill switch,
// budget configuration, then the feature-specific runtime/flag.

import type { AICapabilities } from "@/types";

export const CAPABILITY_UNVERIFIED_REASON =
  "Capability status could not be verified. This action is disabled.";
export const ORG_AI_DISABLED_REASON = "AI execution is disabled for this organization.";
export const AI_BUDGET_UNCONFIGURED_REASON =
  "AI budget is not configured. Ask an administrator to set a token or cost budget.";
export const AGENT_RUNTIME_DISABLED_REASON = "The agent runtime is disabled.";
export const FOUNDER_ASSISTANT_DISABLED_REASON = "The founder assistant is disabled.";
export const INTELLIGENCE_TRIAGE_DISABLED_REASON = "Intelligence triage is disabled.";
export const INTELLIGENCE_NARRATIVE_DISABLED_REASON =
  "Intelligence narrative generation is disabled.";

/** Why an AI run must be disabled, or `null` when it is capability-allowed. */
export function aiRunDisabledReason(capabilities: AICapabilities | null): string | null {
  if (!capabilities) return CAPABILITY_UNVERIFIED_REASON;
  if (!capabilities.ai_execution_enabled) return ORG_AI_DISABLED_REASON;
  if (!capabilities.ai_budget_configured) return AI_BUDGET_UNCONFIGURED_REASON;
  if (!capabilities.agent_runtime_enabled) return AGENT_RUNTIME_DISABLED_REASON;
  return null;
}

/** Why founder chat send must be disabled, or `null` when capability-allowed. */
export function founderChatDisabledReason(capabilities: AICapabilities | null): string | null {
  if (!capabilities) return CAPABILITY_UNVERIFIED_REASON;
  if (!capabilities.ai_execution_enabled) return ORG_AI_DISABLED_REASON;
  if (!capabilities.ai_budget_configured) return AI_BUDGET_UNCONFIGURED_REASON;
  if (!capabilities.founder_assistant_enabled) return FOUNDER_ASSISTANT_DISABLED_REASON;
  return null;
}

/**
 * Why manual triage must be disabled. Reads remain available while triage is
 * off — only the manual sweep control is gated (backend contract).
 */
export function triageDisabledReason(capabilities: AICapabilities | null): string | null {
  if (!capabilities) return CAPABILITY_UNVERIFIED_REASON;
  if (!capabilities.intelligence_triage_enabled) return INTELLIGENCE_TRIAGE_DISABLED_REASON;
  return null;
}

/** Why proposal decisions must be disabled (backend checks the org kill switch). */
export function proposalDecisionDisabledReason(capabilities: AICapabilities | null): string | null {
  if (!capabilities) return CAPABILITY_UNVERIFIED_REASON;
  if (!capabilities.ai_execution_enabled) return ORG_AI_DISABLED_REASON;
  return null;
}

/**
 * Every currently applicable read-only capability notice, in stable order.
 * Used by settings and run panels that should explain all blockers at once.
 */
export function aiCapabilityNotices(capabilities: AICapabilities | null): string[] {
  if (!capabilities) return [CAPABILITY_UNVERIFIED_REASON];
  const notices: string[] = [];
  if (!capabilities.ai_execution_enabled) notices.push(ORG_AI_DISABLED_REASON);
  if (!capabilities.ai_budget_configured) notices.push(AI_BUDGET_UNCONFIGURED_REASON);
  if (!capabilities.agent_runtime_enabled) notices.push(AGENT_RUNTIME_DISABLED_REASON);
  if (!capabilities.founder_assistant_enabled) notices.push(FOUNDER_ASSISTANT_DISABLED_REASON);
  if (!capabilities.intelligence_triage_enabled) notices.push(INTELLIGENCE_TRIAGE_DISABLED_REASON);
  if (!capabilities.intelligence_narrative_enabled) {
    notices.push(INTELLIGENCE_NARRATIVE_DISABLED_REASON);
  }
  return notices;
}
