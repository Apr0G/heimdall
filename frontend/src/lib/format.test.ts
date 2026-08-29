import { afterEach, describe, expect, it, vi } from "vitest";

import {
  centsToInputString,
  formatCents,
  formatDate,
  formatTimestampDate,
} from "./format";

describe("money formatting (rule 11: integer cents, no doubles)", () => {
  it("formats with exact cents", () => {
    expect(formatCents(0)).toBe("$0.00");
    expect(formatCents(5)).toBe("$0.05");
    expect(formatCents(1015)).toBe("$10.15");
    expect(formatCents(123456789)).toBe("$1,234,567.89");
    expect(formatCents(-250)).toBe("-$2.50");
    expect(formatCents(null)).toBe("—");
  });

  it("is exact for every safe integer (the old Number(`d.cc`) path was not)", () => {
    expect(formatCents(Number.MAX_SAFE_INTEGER)).toBe("$90,071,992,547,409.91");
    expect(formatCents(100000000000000001 - 1)).toBe(
      "$1,000,000,000,000,000.00",
    );
  });

  it("round-trips to an input string", () => {
    expect(centsToInputString(1000)).toBe("10.00");
    expect(centsToInputString(7)).toBe("0.07");
    expect(centsToInputString(null)).toBe("");
  });
});

describe("date formatting", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("renders a plain date as the day it names, whatever the zone", () => {
    vi.stubEnv("TZ", "America/New_York");
    expect(formatDate("2026-08-28")).toBe("Aug 28, 2026");
    expect(formatDate(null)).toBe("—");
  });

  it("renders a timestamp on the viewer's calendar date, not the UTC one", () => {
    vi.stubEnv("TZ", "America/New_York");
    // 03:30 UTC on the 28th is 23:30 on the 27th in New York — the old
    // `slice(0, 10)` showed the 28th.
    const ts = "2026-08-28T03:30:00Z";
    expect(formatTimestampDate(ts)).toBe("Aug 27, 2026");
    expect(formatTimestampDate(ts)).toBe(
      new Date(ts).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
    );
    expect(formatTimestampDate(null)).toBe("—");
  });
});
