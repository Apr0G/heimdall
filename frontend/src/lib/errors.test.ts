import { describe, expect, it } from "vitest";

import { pipelineErrorMessage } from "./errors";

describe("pipelineErrorMessage", () => {
  it("maps known exception-type signals to friendly copy", () => {
    expect(
      pipelineErrorMessage("Processing failed (NoBillableLinesError)."),
    ).toMatch(/billable lines/i);
    expect(
      pipelineErrorMessage("Processing failed (DocumentParseError)."),
    ).toMatch(/valid, non-corrupt PDF/i);
  });

  it("never returns the raw message for an unrecognized error", () => {
    const raw = "Processing failed (SomethingWeird: SECRETVALUE).";
    const out = pipelineErrorMessage(raw);
    expect(out).not.toContain("SECRETVALUE");
    expect(out).not.toContain("SomethingWeird");
    expect(out).toMatch(/something went wrong/i);
  });

  it("returns the generic message for null", () => {
    expect(pipelineErrorMessage(null)).toMatch(/something went wrong/i);
  });
});
