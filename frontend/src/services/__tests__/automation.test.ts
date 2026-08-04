import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  createCredential,
  deleteCredential,
  listCredentials,
  rotateCredential,
  updateCredential,
} from "@/services/credentials";
import { listWorkflowEvents, publishWorkflowEvent } from "@/services/workflow-events";
import type { Credential, User, WorkflowEvent } from "@/types";

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

const CREDENTIAL: Credential = {
  id: "88888888-8888-8888-8888-888888888888",
  organization_id: USER.organization_id,
  name: "n8n production",
  credential_type: "n8n_api_key",
  value_preview: "abc…wxyz",
  description: null,
  expires_at: null,
  created_by_user_id: USER.id,
  last_used_at: null,
  key_version: "1",
  last_rotated_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const EVENT: WorkflowEvent = {
  id: "99999999-9999-9999-9999-999999999999",
  organization_id: USER.organization_id,
  event_type: "lead_created",
  payload: { lead_id: "1234" },
  consumed: false,
  consumed_at: null,
  occurred_at: "2026-08-01T00:00:00Z",
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("credentials service", () => {
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

  it("listCredentials encodes the type filter", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [CREDENTIAL], total: 1 }));

    const page = await listCredentials({ credentialType: "n8n_api_key" });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("credential_type=n8n_api_key");
  });

  it("createCredential POSTs the secret payload", async () => {
    fetchMock.mockResolvedValue(jsonResponse(CREDENTIAL));

    await createCredential({
      name: "n8n production",
      credential_type: "n8n_api_key",
      encrypted_value: "secret",
      value_preview: "abc…wxyz",
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/credentials");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"encrypted_value":"secret"');
  });

  it("updateCredential never sends an encrypted_value patch", async () => {
    fetchMock.mockResolvedValue(jsonResponse(CREDENTIAL));

    await updateCredential(CREDENTIAL.id, { description: "prod" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("PATCH");
    expect((init.body as string) ?? "").not.toContain("encrypted_value");
  });

  it("deleteCredential issues a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await deleteCredential(CREDENTIAL.id);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("DELETE");
  });

  it("rotateCredential POSTs to the rotate route", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ...CREDENTIAL, key_version: "2", last_rotated_at: "2026-08-02T00:00:00Z" })
    );

    const rotated = await rotateCredential(CREDENTIAL.id);

    expect(rotated.key_version).toBe("2");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/credentials/${CREDENTIAL.id}/rotate`);
    expect(init.method).toBe("POST");
  });
});

describe("workflow-events service", () => {
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

  it("listWorkflowEvents encodes event_type + consumed filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [EVENT], total: 1 }));

    const page = await listWorkflowEvents({ eventType: "lead_created", consumed: false });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("event_type=lead_created");
    expect(url).toContain("consumed=false");
  });

  it("publishWorkflowEvent POSTs the event", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ event_id: EVENT.id, consumed: false }));

    const result = await publishWorkflowEvent({
      event_type: "lead_created",
      payload: { lead_id: "1234" },
    });

    expect(result.event_id).toBe(EVENT.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/workflow-events");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"event_type":"lead_created"');
  });
});
