import { describe, expect, it } from "vitest";

import type { ProposedEdit, RiskFinding } from "./cases";
import { attachEditsToFindings } from "./precheck-findings";

const finding = (over: Partial<RiskFinding>): RiskFinding => ({
  check_id: "ncci_ptp",
  severity: "high",
  title: "untitled",
  predicted_carc: null,
  explanation: null,
  suggested_fix: null,
  source: "ncci",
  ...over,
});

const edit = (over: Partial<ProposedEdit>): ProposedEdit => ({
  kind: "add_modifier",
  target: null,
  instruction: "do the thing",
  source: "ncci",
  ...over,
});

describe("attachEditsToFindings", () => {
  it("joins an edit to the finding whose title names its target code", () => {
    const findings = [
      finding({
        title: "99213: 3 units exceeds the Medicare MUE limit of 1/day",
      }),
      finding({ title: "20610 will be denied as bundled into 99213" }),
    ];
    const edits = [
      edit({ kind: "add_modifier", target: "20610" }),
      edit({ kind: "change_units", target: "99213" }),
    ];
    const joined = attachEditsToFindings(findings, edits);
    expect(joined.get(1)?.kind).toBe("add_modifier");
    expect(joined.get(0)?.kind).toBe("change_units");
  });

  it("matches whole codes only, never a prefix or suffix", () => {
    const findings = [finding({ title: "20610 will be denied as bundled" })];
    expect(
      attachEditsToFindings(findings, [edit({ target: "2061" })]).size,
    ).toBe(0);
    expect(
      attachEditsToFindings(findings, [edit({ target: "206100" })]).size,
    ).toBe(0);
    expect(
      attachEditsToFindings(findings, [edit({ target: "20610" })]).size,
    ).toBe(1);
  });

  it("gives each finding at most one edit, and each edit one finding", () => {
    // Two bundling hits on the same column-2 code produce two findings and
    // two edits; they must pair off rather than both landing on the first.
    const findings = [
      finding({ title: "20610 cannot be billed with 99213" }),
      finding({ title: "20610 cannot be billed with 20550" }),
    ];
    const edits = [
      edit({ kind: "remove_line", target: "20610", instruction: "a" }),
      edit({ kind: "remove_line", target: "20610", instruction: "b" }),
    ];
    const joined = attachEditsToFindings(findings, edits);
    expect(joined.get(0)?.instruction).toBe("a");
    expect(joined.get(1)?.instruction).toBe("b");
  });

  it("does not cross sources — an AI edit never attaches to a CMS finding", () => {
    const findings = [
      finding({ title: "20610 cannot be billed with 99213", source: "ncci" }),
    ];
    const edits = [edit({ target: "20610", source: "model" })];
    expect(attachEditsToFindings(findings, edits).size).toBe(0);
  });

  it("drops edits with no target or no matching finding", () => {
    const findings = [
      finding({ title: "E/M level not supported by MDM", source: "model" }),
    ];
    const edits = [
      edit({ kind: "documentation", target: null, source: "model" }),
      edit({ kind: "change_code", target: "99215", source: "model" }),
    ];
    expect(attachEditsToFindings(findings, edits).size).toBe(0);
  });
});
