import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  addConversationMessage,
  createConversation,
  getConversation,
  listConversationMessages,
  listConversationsForLead,
  listOpenConversations,
  updateConversation,
} from "@/services/conversations";
import type { Conversation, ConversationMessage, User } from "@/types";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Owner",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const CONVERSATION: Conversation = {
  id: "33333333-3333-3333-3333-333333333333",
  organization_id: USER.organization_id,
  lead_id: "44444444-4444-4444-4444-444444444444",
  channel: "email",
  external_thread_id: null,
  subject: "Intro call follow-up",
  is_open: true,
  last_message_at: "2026-08-03T00:00:00Z",
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-03T00:00:00Z",
};

const MESSAGE: ConversationMessage = {
  id: "55555555-5555-5555-5555-555555555555",
  conversation_id: CONVERSATION.id,
  organization_id: USER.organization_id,
  sender_type: "agent",
  sender_user_id: USER.id,
  body: "Following up on our call.",
  external_id: null,
  metadata: {},
  sent_at: "2026-08-03T00:00:00Z",
  created_at: "2026-08-03T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("conversations service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    setSession({ accessToken: "access-123", expiresIn: 3600, user: USER });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("listConversationsForLead GETs the lead thread list", async () => {
    fetchMock.mockResolvedValue(jsonResponse([CONVERSATION]));

    const conversations = await listConversationsForLead(CONVERSATION.lead_id);

    expect(conversations).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/conversations/leads/${CONVERSATION.lead_id}`);
  });

  it("listOpenConversations sends pagination params", async () => {
    fetchMock.mockResolvedValue(jsonResponse([CONVERSATION]));

    await listOpenConversations(10, 20);

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/conversations/open?");
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=20");
  });

  it("getConversation fetches a single thread", async () => {
    fetchMock.mockResolvedValue(jsonResponse(CONVERSATION));

    const conversation = await getConversation(CONVERSATION.id);

    expect(conversation.id).toBe(CONVERSATION.id);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/conversations/${CONVERSATION.id}`);
  });

  it("createConversation POSTs the lead-scoped payload with auth header", async () => {
    fetchMock.mockResolvedValue(jsonResponse(CONVERSATION));

    const created = await createConversation({
      lead_id: CONVERSATION.lead_id,
      channel: "email",
      subject: "Intro call follow-up",
      organization_id: USER.organization_id,
    });

    expect(created.id).toBe(CONVERSATION.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/conversations");
    expect(init.method).toBe("POST");
    const payload = JSON.parse((init.body as string) ?? "{}") as Record<string, unknown>;
    expect(payload.lead_id).toBe(CONVERSATION.lead_id);
    expect(payload.channel).toBe("email");
    expect(init.headers && (init.headers as Record<string, string>).Authorization).toBe(
      "Bearer access-123"
    );
  });

  it("createConversation never accepts an organization override in the payload contract", async () => {
    // The backend overwrites organization_id with the authenticated
    // principal's organization; the service only forwards what the caller
    // passed (the session user's own org) and never invents a tenant.
    fetchMock.mockResolvedValue(jsonResponse(CONVERSATION));

    await createConversation({
      lead_id: CONVERSATION.lead_id,
      channel: "whatsapp",
      organization_id: USER.organization_id,
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const payload = JSON.parse((init.body as string) ?? "{}") as Record<string, unknown>;
    expect(payload.organization_id).toBe(USER.organization_id);
  });

  it("updateConversation PATCHes partial fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...CONVERSATION, is_open: false }));

    const updated = await updateConversation(CONVERSATION.id, { is_open: false });

    expect(updated.is_open).toBe(false);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/conversations/${CONVERSATION.id}`);
    expect(init.method).toBe("PATCH");
    expect((init.body as string) ?? "").toContain('"is_open":false');
  });

  it("listConversationMessages sends query params and preserves backend order", async () => {
    const older = {
      ...MESSAGE,
      id: "66666666-6666-6666-6666-666666666666",
      created_at: "2026-08-02T00:00:00Z",
    };
    fetchMock.mockResolvedValue(jsonResponse([older, MESSAGE]));

    const messages = await listConversationMessages(CONVERSATION.id, { limit: 50, offset: 10 });

    // Backend returns created_at-ascending order; the service must not re-sort.
    expect(messages[0].created_at <= messages[1].created_at).toBe(true);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/conversations/${CONVERSATION.id}/messages?`);
    expect(url).toContain("limit=50");
    expect(url).toContain("offset=10");
  });

  it("listConversationMessages omits empty query params", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listConversationMessages(CONVERSATION.id);

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://localhost:8000/api/v1/conversations/${CONVERSATION.id}/messages`);
  });

  it("addConversationMessage POSTs an agent message without sender identity fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse(MESSAGE));

    const message = await addConversationMessage(CONVERSATION.id, {
      conversation_id: CONVERSATION.id,
      sender_type: "agent",
      body: "Following up on our call.",
      organization_id: USER.organization_id,
    });

    expect(message.id).toBe(MESSAGE.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/conversations/${CONVERSATION.id}/messages`);
    expect(init.method).toBe("POST");
    const payload = JSON.parse((init.body as string) ?? "{}") as Record<string, unknown>;
    expect(payload.conversation_id).toBe(CONVERSATION.id);
    expect(payload.sender_type).toBe("agent");
    expect(payload.body).toBe("Following up on our call.");
    // Sender identity and timestamps are server-authoritative: the client
    // never sends sender_user_id, sent_at, or provider external ids.
    expect(payload).not.toHaveProperty("sender_user_id");
    expect(payload).not.toHaveProperty("sent_at");
    expect(payload).not.toHaveProperty("external_id");
    expect(payload).not.toHaveProperty("metadata");
  });

  it("surfaces backend error envelope", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "conversation.sender_not_allowed",
            message: "Only agent messages can be created through this endpoint",
          },
        },
        403
      )
    );

    await expect(
      addConversationMessage(CONVERSATION.id, {
        conversation_id: CONVERSATION.id,
        sender_type: "agent",
        body: "hi",
        organization_id: USER.organization_id,
      })
    ).rejects.toThrow("Only agent messages can be created through this endpoint");
  });

  it("surfaces cross-tenant not-found errors", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "conversation.not_found", message: "Conversation not found" } },
        404
      )
    );

    await expect(getConversation(CONVERSATION.id)).rejects.toThrow("Conversation not found");
  });
});
