import { describe, expect, it } from "vitest";

import { shouldClearComposerAfter } from "@/lib/reply-draft";

describe("shouldClearComposerAfter", () => {
  it("clears when still in the same context AND draft unchanged", () => {
    expect(shouldClearComposerAfter(true, "hello", "hello")).toBe(true);
  });

  it("never clears when the user navigated away from the mutation's context", () => {
    expect(shouldClearComposerAfter(false, "hello", "hello")).toBe(false);
  });

  it("never clears when the draft was replaced after submission", () => {
    // User submitted "hello", the request resolves later, but by then the user
    // typed "hello world".
    expect(shouldClearComposerAfter(true, "hello world", "hello")).toBe(false);
  });

  it("never clears when the composer belongs to a newer draft entirely", () => {
    expect(shouldClearComposerAfter(true, "another draft", "hello")).toBe(false);
  });

  it("requires both conditions — mismatch in either keeps the draft", () => {
    expect(shouldClearComposerAfter(false, "other", "hello")).toBe(false);
    expect(shouldClearComposerAfter(true, "other", "hello")).toBe(false);
    expect(shouldClearComposerAfter(false, "hello", "hello")).toBe(false);
  });
});
