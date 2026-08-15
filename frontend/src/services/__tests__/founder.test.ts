import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  decideFounderProposal,
  listFounderConversations,
  listFounderProposals,
  sendFounderMessage,
} from "@/services/founder";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("founder service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sendFounderMessage POSTs to /founder/chat and maps the reply", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        conversation_id: "c-1",
        message: { id: "m-1", sender: "assistant", body: "Hi founder", metadata: {} },
        proposals: [
          {
            id: "p-1",
            action_type: "create_task",
            title: "Create task: Follow up",
            status: "proposed",
            payload: {},
          },
        ],
        intent: { intent_type: "status" },
        ok: true,
        error: null,
      })
    );

    const res = await sendFounderMessage({ message: "What is our pipeline?" });

    expect(res.conversation_id).toBe("c-1");
    expect(res.message.body).toBe("Hi founder");
    expect(res.proposals).toHaveLength(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/founder/chat");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"message":"What is our pipeline?"');
  });

  it("listFounderConversations GETs /founder/conversations", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [{ conversation_id: "c-1", title: "T", is_archived: false }],
        total: 1,
      })
    );

    const page = await listFounderConversations({ limit: 10 });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/founder/conversations?");
    expect(url).toContain("limit=10");
  });

  it("listFounderProposals passes a status filter", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0 }));

    await listFounderProposals({ status: "proposed" });

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/founder/proposals?");
    expect(url).toContain("status=proposed");
  });

  it("decideFounderProposal POSTs the decision", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "p-1",
        action_type: "create_task",
        title: "t",
        status: "approved",
        payload: {},
      })
    );

    const updated = await decideFounderProposal("p-1", { approve: true });

    expect(updated.status).toBe("approved");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/founder/proposals/p-1/decide");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"approve":true');
  });
});
