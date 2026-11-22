import { describe, expect, it } from "vitest";

import { createOwnershipLock } from "@/lib/ownership-lock";

describe("createOwnershipLock", () => {
  it("one request owns the lock at a time", () => {
    const lock = createOwnershipLock();
    expect(lock.tryAcquire(1)).toBe(true);
    expect(lock.current()).toBe(1);
  });

  it("a second concurrent request is rejected", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(1);
    expect(lock.tryAcquire(2)).toBe(false);
    expect(lock.current()).toBe(1);
  });

  it("thread switching invalidates the first request", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(1);
    lock.invalidate(); // navigation invalidates the stale request
    expect(lock.current()).toBeNull();
    expect(lock.tryAcquire(2)).toBe(true); // the new thread's request acquires
  });

  it("the old request's completion cannot clear the new owner's lock", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(1);
    lock.invalidate(); // user switches threads
    lock.tryAcquire(2); // new thread's request owns the lock
    lock.release(1); // stale request finishes — must NOT release
    expect(lock.current()).toBe(2);
    lock.release(2); // new request finishes — releases its own lock
    expect(lock.current()).toBeNull();
  });

  it("stale requests never release anything when a new owner exists", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(1);
    lock.invalidate();
    lock.tryAcquire(2);
    lock.release(1);
    lock.release(1); // repeated no-op
    expect(lock.current()).toBe(2);
  });

  it("the current request releases its own lock", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(7);
    lock.release(7);
    expect(lock.current()).toBeNull();
  });

  it("a failed request releases only its own lock, then retry can acquire", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(1);
    lock.release(1); // request finished (failed or succeeded) — released its own lock
    expect(lock.tryAcquire(2)).toBe(true); // retry works
  });

  it("stale failure followed by a retry does not wedge the lock", () => {
    const lock = createOwnershipLock();
    lock.tryAcquire(1);
    lock.invalidate(); // stale
    expect(lock.tryAcquire(2)).toBe(true); // retry on the new view succeeds
    lock.release(1); // stale completion arrives — owner(2) unaffected
    expect(lock.current()).toBe(2);
    lock.release(2);
    expect(lock.current()).toBeNull();
  });
});
