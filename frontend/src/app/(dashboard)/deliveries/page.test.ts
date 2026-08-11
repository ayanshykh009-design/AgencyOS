import { describe, expect, it } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import { deliveryErrorMessage } from "@/app/(dashboard)/deliveries/page";

describe("deliveryErrorMessage", () => {
  it("surfaces the backend message for API errors", () => {
    const err = new ApiRequestError(
      403,
      "insufficient_permissions",
      "Insufficient permissions for this operation"
    );
    expect(deliveryErrorMessage(err)).toBe("Insufficient permissions for this operation");
  });

  it("explains network failures", () => {
    const err = new ApiRequestError(0, "network.error", "Unable to reach the API");
    expect(deliveryErrorMessage(err)).toBe("Unable to reach the API");
  });

  it("falls back for non-API errors", () => {
    expect(deliveryErrorMessage(new Error("boom"))).toBe("Failed to load deliveries");
  });
});
