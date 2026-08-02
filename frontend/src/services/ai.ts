// AI service: brain runs, tool manifest, n8n dispatch, and per-org AI settings.
import { apiFetch } from "@/lib/api-client";
import type {
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
}

export async function listAITools(): Promise<ToolManifestEntry[]> {
  return apiFetch<ToolManifestEntry[]>("/ai/tools");
}

export async function runBrain(input: BrainRunInput): Promise<BrainRunResponse> {
  return apiFetch<BrainRunResponse>("/ai/run", {
    method: "POST",
    body: JSON.stringify({
      goal: input.goal,
      lead_id: input.leadId,
      channel: input.channel,
      recent_messages: input.recentMessages,
    }),
  });
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
