import { describe, expect, it } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import { inboxErrorMessage } from "@/app/(dashboard)/inbox/page";

describe("inboxErrorMessage", () => {
  it("surfaces the backend message for API errors", () => {
    const err = new ApiRequestError(401, "auth.invalid_token", "Invalid or expired token");
    expect(inboxErrorMessage(err)).toBe("Invalid or expired token");
  });

  it("explains network failures", () => {
    const err = new ApiRequestError(0, "network.error", "Unable to reach the API");
    expect(inboxErrorMessage(err)).toBe("Unable to reach the API");
  });

  it("falls back for non-API errors", () => {
    expect(inboxErrorMessage(new Error("boom"))).toBe("Failed to load notifications");
  });
});
