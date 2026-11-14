import { describe, expect, it } from "vitest";

import {
  getPendingVerificationEmail,
  setPendingVerificationEmail,
} from "@/lib/pending-verification";

describe("pending-verification store", () => {
  it("is empty by default", () => {
    setPendingVerificationEmail(null);
    expect(getPendingVerificationEmail()).toBeNull();
  });

  it("round-trips a trimmed email in memory", () => {
    setPendingVerificationEmail("  owner@example.com  ");
    expect(getPendingVerificationEmail()).toBe("owner@example.com");
  });

  it("clears on null or blank input", () => {
    setPendingVerificationEmail("owner@example.com");
    setPendingVerificationEmail("");
    expect(getPendingVerificationEmail()).toBeNull();
  });
});
