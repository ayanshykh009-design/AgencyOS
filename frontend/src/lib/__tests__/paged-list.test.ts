import { describe, expect, it } from "vitest";

import {
  applyPage,
  applyPageError,
  beginPage,
  initialPagedList,
  nextOffset,
  resetPagedList,
  type PagedListState,
} from "@/lib/paged-list";

const PAGE = 2;
const item = (id: string) => ({ id, label: `item-${id}` });

describe("paged-list machine", () => {
  it("initial offset is zero", () => {
    const s = initialPagedList();
    expect(nextOffset(s)).toBe(0);
    expect(s.items).toEqual([]);
    expect(s.hasMore).toBe(true);
    expect(s.loading).toBe(false);
    expect(s.error).toBeNull();
  });

  it("normal page progression advances the cursor by raw response size", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("1"), item("2")], PAGE, false);
    expect(nextOffset(s)).toBe(2);
    s = applyPage(s, [item("3"), item("4")], PAGE, true);
    expect(nextOffset(s)).toBe(4);
  });

  it("THE critical case: page 1 [A, B], page 2 [B, C] → displayed [A, B, C], next offset = 4", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("A"), item("B")], PAGE, false);
    s = applyPage(s, [item("B"), item("C")], PAGE, true);
    expect(s.items.map((i) => i.id)).toEqual(["A", "B", "C"]);
    expect(nextOffset(s)).toBe(4);
  });

  it("raw offset advances by response size even when duplicates arrive", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("A")], PAGE, false);
    s = applyPage(s, [item("A"), item("B")], PAGE, true);
    expect(nextOffset(s)).toBe(3); // 1 + 2 raw records consumed
    expect(s.items.map((i) => i.id)).toEqual(["A", "B"]); // duplicate not rendered
  });

  it("a failed append preserves items AND the raw cursor", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("A"), item("B")], PAGE, false);
    s = applyPageError(s, "boom");
    expect(nextOffset(s)).toBe(2);
    expect(s.items.map((i) => i.id)).toEqual(["A", "B"]);
    expect(s.error).toBe("boom");
  });

  it("a failed INITIAL page leaves the cursor at zero", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPageError(s, "boom");
    expect(nextOffset(s)).toBe(0);
    expect(s.items).toEqual([]);
  });

  it("retry uses exactly the failed offset (raw consumed)", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("A"), item("B")], PAGE, false);
    s = applyPageError(s, "boom"); // e.g. page 2 (offset 2) failed
    const retryOffset = nextOffset(s); // must be 2, not items.length nuance
    expect(retryOffset).toBe(2);
    s = applyPage(s, [item("B"), item("C")], PAGE, true); // records 3 and 4 delivered
    expect(nextOffset(s)).toBe(4);
  });

  it("short page terminates pagination", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("1")], PAGE, false);
    expect(s.hasMore).toBe(false);
  });

  it("full page indicates another page may exist", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("1"), item("2")], PAGE, false);
    expect(s.hasMore).toBe(true);
  });

  it("more than 500 records accumulate across pages (no artificial cap)", () => {
    let s = initialPagedList<{ id: string }>();
    for (let pageIndex = 0; pageIndex < 12; pageIndex += 1) {
      const offset = pageIndex * 50;
      const page = Array.from({ length: 50 }, (_, i) => item(String(offset + i + 1)));
      s = applyPage(s, page, 50, pageIndex > 0);
    }
    expect(s.items).toHaveLength(600);
    expect(nextOffset(s)).toBe(600);
    expect(s.hasMore).toBe(true);
    s = applyPage(
      s,
      Array.from({ length: 17 }, (_, i) => item(`x${i}`)),
      50,
      true
    );
    expect(s.items).toHaveLength(617);
    expect(s.hasMore).toBe(false);
    expect(nextOffset(s)).toBe(617);
  });

  it("backend order is preserved across appends", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("c"), item("a")], PAGE, false);
    s = applyPage(s, [item("b"), item("d")], PAGE, true);
    expect(s.items.map((i) => i.id)).toEqual(["c", "a", "b", "d"]);
  });

  it("an append never reduces or resets the consumed cursor", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("A"), item("B")], PAGE, false);
    const before = nextOffset(s);
    s = applyPage(s, [item("B")], PAGE, true); // all-duplicate page still consumes a record
    expect(nextOffset(s)).toBe(before + 1);
  });

  it("a successful refresh re-baselines the cursor", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("A"), item("B")], PAGE, false);
    s = applyPage(s, [item("X")], PAGE, false); // refresh, only 1 new row
    expect(nextOffset(s)).toBe(1);
    expect(s.items.map((i) => i.id)).toEqual(["X"]);
  });

  it("duplicate messages across boundaries are deduplicated by id", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("1"), item("2")], PAGE, false);
    s = applyPage(s, [item("2"), item("3")], PAGE, true);
    expect(s.items.map((i) => i.id)).toEqual(["1", "2", "3"]);
  });

  it("beginPage is a no-op (same object) while a request is in flight", () => {
    let s = initialPagedList<{ id: string }>();
    s = beginPage(s);
    const again = beginPage(s);
    expect(again).toBe(s);
  });

  it("reset returns both items and offset to zero", () => {
    let s = initialPagedList<{ id: string }>();
    s = applyPage(s, [item("1"), item("2")], PAGE, false);
    const fresh: PagedListState<{ id: string }> = resetPagedList<{ id: string }>();
    expect(fresh.items).toEqual([]);
    expect(nextOffset(fresh)).toBe(0);
    expect(fresh.hasMore).toBe(true);
  });
});
