// Conversations service: lead message threads + thread messages (Batch 3).
//
// Security model (backend is authoritative — see app/api/v1/endpoints/
// conversations.py and app/services/conversation_service.py):
// - Organization context always comes from the authenticated principal; the
//   required ``organization_id`` field in create payloads is overwritten
//   server-side, so the client never controls tenant scoping.
// - Sender attribution is server-authoritative: only ``sender_type: "agent"`
//   messages may be created through the HTTP endpoint, ``sender_user_id`` is
//   forced to the authenticated user, and ``sent_at`` is set to the server
//   clock. No sender identity fields are ever sent by this service.
// - LEAD/SYSTEM messages are persisted only through the trusted inbound
//   service path, which ordinary HTTP clients cannot reach.
// - Message ordering comes from the backend (``created_at`` ascending) and is
//   preserved as returned; no client-side re-sorting.
import { apiFetch } from "@/lib/api-client";
import type {
  Conversation,
  ConversationCreateInput,
  ConversationMessage,
  ConversationMessageCreateInput,
  ConversationUpdateInput,
} from "@/types";

/** List open conversations for the organization (backend default limit 50). */
export async function listOpenConversations(limit = 50, offset = 0): Promise<Conversation[]> {
  return apiFetch<Conversation[]>(`/conversations/open?limit=${limit}&offset=${offset}`);
}

/** List every conversation thread on a lead (backend order: updated_at desc). */
export async function listConversationsForLead(leadId: string): Promise<Conversation[]> {
  return apiFetch<Conversation[]>(`/conversations/leads/${leadId}`);
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  return apiFetch<Conversation>(`/conversations/${conversationId}`);
}

export async function createConversation(input: ConversationCreateInput): Promise<Conversation> {
  return apiFetch<Conversation>("/conversations", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateConversation(
  conversationId: string,
  patch: ConversationUpdateInput
): Promise<Conversation> {
  return apiFetch<Conversation>(`/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export interface ConversationMessageQuery {
  /** Backend accepts 1–1000 (default 200). */
  limit?: number;
  offset?: number;
}

/** List messages in a thread (backend order: created_at ascending). */
export async function listConversationMessages(
  conversationId: string,
  query: ConversationMessageQuery = {}
): Promise<ConversationMessage[]> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<ConversationMessage[]>(
    `/conversations/${conversationId}/messages${qs ? `?${qs}` : ""}`
  );
}

/**
 * Add an AGENT message to a thread as the authenticated user. The backend
 * rejects non-agent senders (403), ignores any client sender identity, and
 * stamps the timestamp itself.
 */
export async function addConversationMessage(
  conversationId: string,
  input: ConversationMessageCreateInput
): Promise<ConversationMessage> {
  return apiFetch<ConversationMessage>(`/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
