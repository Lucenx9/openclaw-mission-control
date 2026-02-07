import { describe, expect, it, vi } from "vitest";

import { createExponentialBackoff } from "./backoff";

describe("createExponentialBackoff", () => {
  it("increments attempt and clamps delay", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);

    const backoff = createExponentialBackoff({
      baseMs: 100,
      factor: 2,
      maxMs: 250,
      jitter: 0,
    });

    expect(backoff.attempt()).toBe(0);
    expect(backoff.nextDelayMs()).toBe(100);
    expect(backoff.attempt()).toBe(1);
    expect(backoff.nextDelayMs()).toBe(200);
    expect(backoff.nextDelayMs()).toBe(250); // capped
  });

  it("clamps invalid numeric options and treats negative jitter as zero", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.9999);

    // baseMs: NaN should clamp to min (50)
    // maxMs: Infinity should clamp to min (= baseMs)
    // jitter: negative -> treated as 0 (no extra delay)
    const backoff = createExponentialBackoff({
      baseMs: Number.NaN,
      maxMs: Number.POSITIVE_INFINITY,
      jitter: -1,
    });

    // With maxMs clamped to baseMs, delay will always be baseMs
    expect(backoff.nextDelayMs()).toBe(50);
    expect(backoff.nextDelayMs()).toBe(50);
  });

  it("reset brings attempt back to zero", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);

    const backoff = createExponentialBackoff({ baseMs: 100, jitter: 0 });
    backoff.nextDelayMs();
    expect(backoff.attempt()).toBe(1);

    backoff.reset();
    expect(backoff.attempt()).toBe(0);
  });

  it("uses defaults when options are omitted", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);

    const backoff = createExponentialBackoff();
    expect(backoff.attempt()).toBe(0);

    // Default baseMs is 1000 (clamped within bounds), jitter default is 0.2.
    // With Math.random=0, delay should be the normalized base (1000).
    expect(backoff.nextDelayMs()).toBe(1000);
  });
});
