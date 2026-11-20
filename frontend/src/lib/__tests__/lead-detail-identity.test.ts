import { describe, expect, it } from "vitest";

import { createGenerationGuard, detailIdentityKey } from "@/lib/lead-detail-identity";

const ORG_A = "00000000-0000-0000-0000-00000000000a";
const ORG_B = "00000000-0000-0000-0000-00000000000b";
const USER_A = "11111111-1111-1111-1111-111111111111";
const USER_B = "22222222-2222-2222-2222-222222222222";

const userA = { id: USER_A, organization_id: ORG_A };
const userB = { id: USER_B, organization_id: ORG_A };
const userAOrgB = { id: USER_A, organization_id: ORG_B };

describe("detailIdentityKey", () => {
  it("is stable for identical identity + lead", () => {
    expect(detailIdentityKey(userA, "lead-1")).toBe(detailIdentityKey(userA, "lead-1"));
  });

  it("changes when the lead route changes (Lead A → Lead B)", () => {
    expect(detailIdentityKey(userA, "lead-A")).not.toBe(detailIdentityKey(userA, "lead-B"));
  });

  it("changes when the organization changes (Org A → Org B, same user)", () => {
    expect(detailIdentityKey(userA, "lead-1")).not.toBe(detailIdentityKey(userAOrgB, "lead-1"));
  });

  it("changes when the user changes within one organization", () => {
    expect(detailIdentityKey(userA, "lead-1")).not.toBe(detailIdentityKey(userB, "lead-1"));
  });

  it("returns null without an authenticated principal", () => {
    expect(detailIdentityKey(null, "lead-1")).toBeNull();
  });
});

describe("createGenerationGuard", () => {
  it("isCurrent is true only for the latest captured generation", () => {
    const guard = createGenerationGuard();
    const gen1 = guard.capture();
    expect(guard.isCurrent(gen1)).toBe(true);
    const gen2 = guard.capture();
    expect(guard.isCurrent(gen1)).toBe(false);
    expect(guard.isCurrent(gen2)).toBe(true);
  });

  it("invalidate() makes every earlier generation stale", () => {
    const guard = createGenerationGuard();
    const gen = guard.capture();
    guard.invalidate(); // route/principal change or unmount
    expect(guard.isCurrent(gen)).toBe(false);
    const fresh = guard.capture();
    expect(guard.isCurrent(fresh)).toBe(true);
  });

  it("a response issued before an identity change cannot be applied after it", () => {
    const guard = createGenerationGuard();
    const issued = guard.capture(); // request issued on lead A / principal A
    guard.invalidate(); // identity change (remount/logout/new route)
    expect(guard.isCurrent(issued)).toBe(false); // its setState must be dropped
  });
});
