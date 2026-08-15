import { afterEach, describe, expect, it, vi } from "vitest";

import { listSignals, getSummary, runTriage, updateSignal } from "@/services/intelligence";

const apiFetch = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

afterEach(() => {
  apiFetch.mockReset();
});

describe("intelligence service", () => {
  it("listSignals builds query string from filters", async () => {
    apiFetch.mockResolvedValue({ items: [], total: 0 });
    await listSignals({ status: "active", limit: 50, offset: 0 });

    expect(apiFetch).toHaveBeenCalledWith("/intelligence/signals?status=active&limit=50&offset=0");
  });

  it("listSignals omits query string when no filters", async () => {
    apiFetch.mockResolvedValue({ items: [], total: 0 });
    await listSignals({});

    expect(apiFetch).toHaveBeenCalledWith("/intelligence/signals");
  });

  it("getSummary hits the summary endpoint", async () => {
    apiFetch.mockResolvedValue({
      active: 1,
      acknowledged: 0,
      dismissed: 0,
      superseded: 0,
      high_priority: 1,
      medium_priority: 0,
      low_priority: 0,
      highest_priority_score: 0.8,
    });
    const summary = await getSummary();
    expect(apiFetch).toHaveBeenCalledWith("/intelligence/summary");
    expect(summary.active).toBe(1);
  });

  it("updateSignal PATCHes the signal", async () => {
    apiFetch.mockResolvedValue({ id: "s1", status: "acknowledged" });
    await updateSignal("s1", { status: "acknowledged" });
    expect(apiFetch).toHaveBeenCalledWith("/intelligence/signals/s1", {
      method: "PATCH",
      body: JSON.stringify({ status: "acknowledged" }),
    });
  });

  it("runTriage POSTs to the triage endpoint", async () => {
    apiFetch.mockResolvedValue({
      candidates: 2,
      created: 1,
      updated: 1,
      superseded: 0,
      high_priority: 1,
      narrative: "No significant signals today.",
    });
    const result = await runTriage();
    expect(apiFetch).toHaveBeenCalledWith("/intelligence/triage/run", { method: "POST" });
    expect(result.narrative).toBe("No significant signals today.");
  });
});
