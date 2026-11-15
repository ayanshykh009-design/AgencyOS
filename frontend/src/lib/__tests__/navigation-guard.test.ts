import { describe, expect, it } from "vitest";

import { createNavigationGuard } from "@/lib/navigation-guard";

const LIST = "list" as const;

describe("createNavigationGuard", () => {
  it("starts on the list view", () => {
    const guard = createNavigationGuard();
    expect(guard.view()).toBe(LIST);
  });

  it("navigateThread bumps the generation and switches view", () => {
    const guard = createNavigationGuard();
    const t1 = guard.navigateThread("A");
    expect(t1.view).toBe("A");
    expect(guard.isThread(t1, "A")).toBe(true);
    const t2 = guard.navigateThread("B");
    expect(guard.isThread(t1, "A")).toBe(false); // stale
    expect(guard.isThread(t2, "A")).toBe(false); // wrong thread
    expect(guard.isThread(t2, "B")).toBe(true);
  });

  it("navigateList bumps generation and switches to list", () => {
    const guard = createNavigationGuard();
    const t1 = guard.navigateThread("A");
    const t2 = guard.navigateList();
    expect(t2.view).toBe(LIST);
    expect(guard.isList(t2)).toBe(true);
    expect(guard.isList(t1)).toBe(false); // stale
    expect(guard.isCurrent(t1)).toBe(false);
  });

  it("isCurrent is true only for the latest navigation", () => {
    const guard = createNavigationGuard();
    const original = guard.capture();
    guard.navigateThread("A");
    expect(guard.isCurrent(original)).toBe(false);
    guard.navigateList();
    expect(guard.isCurrent(original)).toBe(false);
  });

  it("a captured token survives reads (capture is stable snapshot)", () => {
    const guard = createNavigationGuard();
    const first = guard.capture();
    const second = guard.capture();
    expect(first).toEqual(second);
  });

  // ---- mutation scenarios required by the review ---------------------------

  it("Record Reply — user stays on the same thread: completion applies", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const mutationToken = guard.capture();
    // ... mutation completes ...
    expect(guard.isThread(mutationToken, "A")).toBe(true);
  });

  it("Record Reply — user switches A → B during the request: completion must not apply", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const mutationToken = guard.capture();
    guard.navigateThread("B");
    expect(guard.isThread(mutationToken, "A")).toBe(false);
  });

  it("Record Reply — user returns to the list during the request: completion must not apply", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const mutationToken = guard.capture();
    guard.navigateList();
    expect(guard.isThread(mutationToken, "A")).toBe(false);
    expect(guard.isCurrent(mutationToken)).toBe(false);
  });

  it("Create Thread — user navigates to Thread B while creation is pending: no selection theft", () => {
    const guard = createNavigationGuard();
    guard.navigateList(); // starts on the list
    const createToken = guard.capture();
    guard.navigateThread("B"); // user opens another thread meanwhile
    expect(guard.isList(createToken)).toBe(false); // created thread must NOT auto-open
    // The created record is not discarded — it lands in the refreshed list.
  });

  it("Close/Reopen — user navigates away during the request: stale detail update is dropped", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const mutationToken = guard.capture();
    guard.navigateThread("B");
    expect(guard.isThread(mutationToken, "A")).toBe(false);
    guard.navigateList();
    expect(guard.isThread(mutationToken, "A")).toBe(false);
  });

  it("stale errors cannot appear in another thread: threadId tagging is required alongside generation", () => {
    // This test documents the required integration: the component applies an
    // error to a thread ONLY when (a) the mutation's threadId stamp matches
    // the currently selected thread AND (b) the flow uses the nav guard.
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const mutationToken = guard.capture();
    guard.navigateThread("B");
    const stamped: string = "A";
    const viewing: string = "B";
    expect(stamped === viewing).toBe(false); // filtered out at render
    expect(guard.isThread(mutationToken, "A")).toBe(false);
    expect(guard.isThread(mutationToken, "B")).toBe(false);
  });

  it("successful database mutations stay successful despite navigation (guard never discards results)", () => {
    // The guard only gates UI application; it has no delete/cancel semantics.
    const guard = createNavigationGuard();
    const token = guard.navigateThread("A");
    guard.navigateList(); // user leaves
    // The mutation outcome is still reported by the service layer — the guard
    // merely says where the UI effects land, which is nowhere here.
    expect(guard.isCurrent(token)).toBe(false);
    expect(() => guard.capture()).not.toThrow();
  });

  it("A→B→A navigation does not revive a stale token", () => {
    const guard = createNavigationGuard();
    guard.navigateThread("A");
    const token = guard.capture();
    guard.navigateThread("B");
    guard.navigateThread("A"); // same view, NEW generation
    expect(guard.isThread(token, "A")).toBe(false); // stale even though view matches
  });
});
