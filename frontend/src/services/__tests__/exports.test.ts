import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import { buildExportUrl, downloadExport } from "@/services/exports";
import type { User } from "@/types";

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

describe("exports service", () => {
  it("buildExportUrl defaults to csv", () => {
    const url = buildExportUrl("csv");
    expect(url).toContain("/exports/leads?fmt=csv");
  });

  it("buildExportUrl encodes filters", () => {
    const url = buildExportUrl("json", { status: "won", minScore: 50, ownerUserId: "u1" });
    expect(url).toContain("fmt=json");
    expect(url).toContain("status=won");
    expect(url).toContain("min_score=50");
    expect(url).toContain("owner_user_id=u1");
  });

  it("downloadExport fetches with auth and triggers a blob download", async () => {
    clearSession();
    setSession({ accessToken: "access-123", refreshToken: "r", expiresIn: 3600, user: USER });

    const click = vi.fn();
    const anchor = { href: "", download: "", click, remove: vi.fn() };
    vi.stubGlobal("document", {
      createElement: vi.fn(() => anchor),
      body: { appendChild: vi.fn() },
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(new Blob(["a,b\n1,2"], { type: "text/csv" }), { status: 200 })
      );
    vi.stubGlobal("fetch", fetchMock);

    await downloadExport("csv", { status: "new" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/exports/leads?fmt=csv");
    expect(url).toContain("status=new");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-123");
    expect(anchor.download).toBe("leads.csv");
    expect(click).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });

  it("downloadExport throws when the export request fails", async () => {
    clearSession();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("boom", { status: 500 })));

    await expect(downloadExport("csv")).rejects.toThrow("Export failed with status 500");

    vi.unstubAllGlobals();
    clearSession();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    clearSession();
  });

  beforeEach(() => {
    clearSession();
  });
});
