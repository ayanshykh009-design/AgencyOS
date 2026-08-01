import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("joins truthy class names", () => {
    expect(cn("a", "b", false, null, undefined, "c")).toBe("a b c");
  });

  it("returns an empty string when nothing is truthy", () => {
    expect(cn(false, null)).toBe("");
  });
});
