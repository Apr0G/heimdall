import { describe, expect, it, vi } from "vitest";

import { httpError } from "@/test/axios-error";

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn() } }));
vi.mock("sonner", () => ({ toast }));

import { pipelineErrorMessage, toastError } from "./errors";

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

describe("toastError", () => {
  it("translates a machine-readable detail and passes user copy through", () => {
    toastError(httpError(409, "report_changed"));
    expect(toast.error).toHaveBeenLastCalledWith(
      "This report changed — reload and pick your edits again",
    );
    toastError(httpError(400, "Selections must be distinct."));
    expect(toast.error).toHaveBeenLastCalledWith(
      "Selections must be distinct.",
    );
  });
});
