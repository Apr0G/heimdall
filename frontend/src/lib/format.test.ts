import { describe, expect, it } from "vitest";

import { centsToInputString, formatCents } from "./format";

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
