import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  cancelDelivery,
  createDelivery,
  getDelivery,
  listDeliveries,
  listDeliveryEvents,
  retryDelivery,
} from "@/services/deliveries";
import type { Delivery, DeliveryEvent, User } from "@/types";

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

const DELIVERY: Delivery = {
  id: "33333333-3333-3333-3333-333333333333",
  organization_id: USER.organization_id,
  channel: "dashboard",
  recipient_user_id: USER.id,
  notification_id: null,
  approval_request_id: null,
  subject: "New meeting booked",
  body: "A meeting was booked with a prospect.",
  action_url: null,
  status: "queued",
  attempts: 0,
  max_attempts: 3,
  next_attempt_at: null,
  attempt_started_at: null,
  cancel_requested_at: null,
  cancelled_by_user_id: null,
  last_error: null,
  provider_metadata: {},
  payload: {},
  idempotency_key: null,
  scheduled_for: "2026-08-01T00:00:00Z",
  delivered_at: null,
  failed_at: null,
  cancelled_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const EVENT: DeliveryEvent = {
  id: "44444444-4444-4444-4444-444444444444",
  organization_id: USER.organization_id,
  delivery_id: DELIVERY.id,
  event_type: "queued",
  attempt: 0,
  metadata: {},
  occurred_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("deliveries service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    setSession({ accessToken: "access-123", refreshToken: "r", expiresIn: 3600, user: USER });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("listDeliveries encodes filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [DELIVERY], total: 1 }));

    const page = await listDeliveries({ status: "failed", channel: "email" });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("status=failed");
    expect(url).toContain("channel=email");
  });

  it("getDelivery fetches one delivery", async () => {
    fetchMock.mockResolvedValue(jsonResponse(DELIVERY));

    const delivery = await getDelivery(DELIVERY.id);

    expect(delivery.subject).toBe("New meeting booked");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/deliveries/${DELIVERY.id}`);
  });

  it("createDelivery POSTs the payload", async () => {
    fetchMock.mockResolvedValue(jsonResponse(DELIVERY));

    const result = await createDelivery({
      channel: "dashboard",
      subject: "New meeting booked",
      body: "A meeting was booked with a prospect.",
      max_attempts: 5,
    });

    expect(result.id).toBe(DELIVERY.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/deliveries");
    expect(init.method).toBe("POST");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"channel":"dashboard"');
    expect(body).toContain('"max_attempts":5');
  });

  it("listDeliveryEvents fetches the timeline", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [EVENT], total: 1 }));

    const page = await listDeliveryEvents(DELIVERY.id, { limit: 50 });

    expect(page.items[0].event_type).toBe("queued");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/deliveries/${DELIVERY.id}/events`);
    expect(url).toContain("limit=50");
  });

  it("retry/cancel POST to lifecycle endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(DELIVERY))
      .mockResolvedValueOnce(jsonResponse(DELIVERY));

    await retryDelivery(DELIVERY.id);
    let [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/deliveries/${DELIVERY.id}/retry`);
    expect(init.method).toBe("POST");

    await cancelDelivery(DELIVERY.id);
    [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain(`/deliveries/${DELIVERY.id}/cancel`);
    expect(init.method).toBe("POST");
  });
});
