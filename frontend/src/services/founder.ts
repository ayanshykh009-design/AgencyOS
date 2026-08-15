// Founder AI Assistant service (M8): chat, conversations, and approval-gated
// action proposals. All calls route through the shared apiFetch client.
import { apiFetch } from "@/lib/api-client";
import type {
  FounderChatRequest,
  FounderChatResponse,
  FounderConversation,
  FounderMessage,
  FounderProposal,
  FounderProposalDecision,
  Page,
} from "@/types";

export interface FounderConversationQuery {
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}

export interface FounderProposalQuery {
  status?: FounderProposal["status"];
  limit?: number;
  offset?: number;
}

export async function sendFounderMessage(input: FounderChatRequest): Promise<FounderChatResponse> {
  return apiFetch<FounderChatResponse>("/founder/chat", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listFounderConversations(
  query: FounderConversationQuery = {}
): Promise<Page<FounderConversation>> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.includeArchived) params.set("include_archived", "true");
  const qs = params.toString();
  return apiFetch<Page<FounderConversation>>(`/founder/conversations${qs ? `?${qs}` : ""}`);
}

export async function getFounderConversation(conversationId: string): Promise<{
  conversation: FounderConversation;
  messages: FounderMessage[];
}> {
  return apiFetch<{ conversation: FounderConversation; messages: FounderMessage[] }>(
    `/founder/conversations/${conversationId}`
  );
}

export async function deleteFounderConversation(conversationId: string): Promise<void> {
  await apiFetch<void>(`/founder/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export async function listFounderProposals(
  query: FounderProposalQuery = {}
): Promise<Page<FounderProposal>> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<FounderProposal>>(`/founder/proposals${qs ? `?${qs}` : ""}`);
}

export async function decideFounderProposal(
  proposalId: string,
  input: FounderProposalDecision
): Promise<FounderProposal> {
  return apiFetch<FounderProposal>(`/founder/proposals/${proposalId}/decide`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
