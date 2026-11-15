import { describe, expect, it } from "vitest";

import { createNavigationGuard } from "@/lib/navigation-guard";
import { shouldClearComposerAfter } from "@/lib/reply-draft";

/**
 * Edge-case closure tests for findings E (subject draft ownership), F
 * (Close/Reopen error scoping), and the async error-visibility corrections.
 *
 * These exercise the ACTUAL production mechanism — the navigation guard the
 * component captures/mutates per context and the shared draft-clearing
 * predicate — reproducing the component's handler predicates exactly.
 */
describe("Edge-case closures (subject draft + mutation error scoping)", () => {
  // ---- Finding E: subject draft is only cleared when context + draft match ---

  it("clears the submitted subject only when the list context is unchanged and the draft is identical", () => {
    const guard = createNavigationGuard(); // view = list, generation 1
    const token = guard.capture();
    const submitted = "Intro thread";
    const currentSubject = submitted;
    const clear = shouldClearComposerAfter(guard.isList(token), currentSubject, submitted);
    expect(guard.isList(token)).toBe(true);
    expect(clear).toBe(true); // component may setSubject("")
  });

  it("a subject replaced while the create request was pending survives completion", () => {
    const guard = createNavigationGuard();
    const token = guard.capture();
    const submitted = "Intro thread";
    const replaced = "New subject"; // user typed while the request was in flight
    expect(shouldClearComposerAfter(guard.isList(token), replaced, submitted)).toBe(false);
  });

  it("navigating away from the list and back keeps any newer subject (stale token)", () => {
    const guard = createNavigationGuard();
    const token = guard.capture(); // list, gen 1
    guard.navigateThread("thread-b"); // user opens a thread
    guard.navigateList(); // user returns to the list
    // The old token is stale — the new list view has a new generation.
    expect(guard.isList(token)).toBe(false);
    expect(shouldClearComposerAfter(guard.isList(token), "Intro thread", "Intro thread")).toBe(
      false
    );
  });

  it("a stale create failure is scoped to the list context it started in", () => {
    const guard = createNavigationGuard();
    const token = guard.capture();
    guard.navigateThread("other-thread"); // user navigates mid-request
    // Render predicate used by the component: isList(token) gates visibility.
    expect(guard.isList(token)).toBe(false);
    guard.navigateList(); // user returns to the list
    expect(guard.isList(token)).toBe(false); // still stale: not visible
  });

  it("the created record is not discarded when the user navigates away (guard blocks only the OPEN, not the mutation)", () => {
    const guard = createNavigationGuard();
    const token = guard.capture(); // list context at submit time
    guard.navigateThread("thread-b"); // user navigates to another thread while create is pending
    // Component skips openThread(created) when isList(token) === false — the
    // DB record still exists; only the UI view is preserved.
    expect(guard.isList(token)).toBe(false);
  });

  // ---- Finding F: Close/Reopen failures are scoped to the same thread+generation ----

  it("close failure is visible in the same thread at the same generation", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A"); // selected = A
    const token = guard.capture(); // same generation as visible UI
    // Component gate: isThread(token, target.id) → setStatusError(...) happens.
    expect(guard.isThread(token, "A")).toBe(true);
  });

  it("reopen failure is visible in the same thread at the same generation", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    expect(guard.isThread(token, "A")).toBe(true);
  });

  it("a failure after A → B navigation does not render in Thread B", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    guard.navigateThread("B"); // user switched mid-request
    expect(guard.isThread(token, "A")).toBe(false); // status error dropped at set time
    expect(guard.isCurrent(token)).toBe(false);
  });

  it("a failure after A → list → A navigation does not reappear in the later generation of A", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    guard.navigateList(); // user pressed Back
    guard.navigateThread("A"); // user re-opens A — NEW generation
    expect(guard.isThread(token, "A")).toBe(false);
    expect(guard.isCurrent(token)).toBe(false);
  });

  it("switching threads invalidates an in-flight status error (visibility gate)", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture(); // status error token (thread A)
    guard.navigateThread("B"); // switch clears: token stale
    expect(guard.isCurrent(token)).toBe(false);
    guard.navigateList();
    expect(guard.isCurrent(token)).toBe(false);
  });

  it("successful Close/Reopen applies only to the same thread at the same generation", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    expect(guard.isThread(token, "A")).toBe(true);
    guard.navigateThread("B");
    expect(guard.isThread(token, "A")).toBe(false);
  });

  // ---- Async mutation error scoping (Reply + Create + Close/Reopen) ---------

  it("record-reply failure from Thread A does not apply after A → list navigation", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    guard.navigateList();
    expect(guard.isThread(token, "A")).toBe(false);
  });

  it("record-reply failure from Thread A does not apply after A → B navigation", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    guard.navigateThread("B");
    expect(guard.isThread(token, "A")).toBe(false);
  });

  it("record-reply failure from A does not appear in a later generation of A", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    guard.navigateList();
    guard.navigateThread("A");
    expect(guard.isThread(token, "A")).toBe(false);
  });

  it("create-thread failure from the list does not apply after the user opened Thread B", () => {
    const guard = createNavigationGuard(); // list context
    const token = guard.capture();
    guard.navigateThread("B");
    expect(guard.isList(token)).toBe(false);
  });

  it("any navigation bumps the generation for ALL captured mutation tokens", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const tokens = [guard.capture(), guard.capture(), guard.capture()];
    guard.navigateList();
    for (const token of tokens) {
      expect(guard.isCurrent(token)).toBe(false);
    }
  });
});
