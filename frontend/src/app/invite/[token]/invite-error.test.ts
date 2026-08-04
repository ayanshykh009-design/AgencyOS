import { describe, expect, it } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import { inviteError } from "@/app/invite/[token]/page";

describe("inviteError", () => {
  it("maps expired invites to a friendly message", () => {
    const err = new ApiRequestError(404, "team.invite_expired", "This invite has expired");
    expect(inviteError(err)).toContain("expired");
  });

  it("surfaces the backend message for used/revoked invites", () => {
    const err = new ApiRequestError(
      404,
      "team.invite_invalid",
      "This invite has already been used or revoked"
    );
    expect(inviteError(err)).toBe("This invite has already been used or revoked");
  });

  it("explains duplicate accounts", () => {
    const err = new ApiRequestError(
      409,
      "team.user_exists",
      "A user with that email already exists"
    );
    expect(inviteError(err)).toContain("already exists");
  });

  it("handles network failures", () => {
    const err = new ApiRequestError(0, "network.error", "Unable to reach the API");
    expect(inviteError(err)).toContain("Unable to reach");
  });

  it("falls back to the API message for other codes", () => {
    const err = new ApiRequestError(400, "request.failed", "Something broke");
    expect(inviteError(err)).toBe("Something broke");
  });

  it("falls back for non-API errors", () => {
    expect(inviteError(new Error("boom"))).toBe("Something went wrong. Please try again.");
  });
});
