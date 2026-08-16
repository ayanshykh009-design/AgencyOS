// AI service: brain runs, tool manifest, n8n dispatch, and per-org AI settings.
import { apiFetch } from "@/lib/api-client";
import type {
  AgentRunRead,
  BrainRunResponse,
  DispatchResponse,
  OrganizationAISettings,
  OutreachChannel,
  ToolManifestEntry,
} from "@/types";

export interface BrainRunInput {
  goal: string;
  leadId: string;
  channel?: OutreachChannel;
  recentMessages?: Array<Record<string, unknown>>;
  idempotencyKey?: string;
}

/**
 * Queue an AI run (M11-C). Returns the created run; the caller polls its status
 * via {@link getAgentRun} and may cancel it via {@link cancelAgentRun}.
 */
export async function runBrain(input: BrainRunInput): Promise<AgentRunRead> {
  return apiFetch<AgentRunRead>("/ai/run", {
    method: "POST",
    body: JSON.stringify({
      goal: input.goal,
      lead_id: input.leadId,
      channel: input.channel,
      recent_messages: input.recentMessages,
      idempotency_key: input.idempotencyKey,
    }),
  });
}

/** Fetch a single agent run by id (polling for AI run completion). */
export async function getAgentRun(runId: string): Promise<AgentRunRead> {
  return apiFetch<AgentRunRead>(`/agents/runs/${runId}`);
}

/** Cancel a queued or running agent run. */
export async function cancelAgentRun(runId: string): Promise<AgentRunRead> {
  return apiFetch<AgentRunRead>(`/agents/runs/${runId}/cancel`, {
    method: "POST",
  });
}

export async function listAITools(): Promise<ToolManifestEntry[]> {
  return apiFetch<ToolManifestEntry[]>("/ai/tools");
}

export async function dispatchDraft(
  workflow: string,
  payload: Record<string, unknown>
): Promise<DispatchResponse> {
  return apiFetch<DispatchResponse>("/ai/dispatch", {
    method: "POST",
    body: JSON.stringify({ workflow, payload }),
  });
}

export async function getAISettings(): Promise<OrganizationAISettings> {
  return apiFetch<OrganizationAISettings>("/ai/settings");
}

export async function updateAISettings(
  patch: Partial<Pick<OrganizationAISettings, "provider" | "model">>
): Promise<OrganizationAISettings> {
  return apiFetch<OrganizationAISettings>("/ai/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}
