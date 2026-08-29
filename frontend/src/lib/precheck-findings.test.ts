import { describe, expect, it } from "vitest";

import type { ProposedEdit, RiskFinding } from "./cases";
import {
  attachEditsToFindings,
  buildSelections,
  type EditChoice,
  choiceIsComplete,
  defaultChoice,
  fixTarget,
  isClaimEdit,
  modifierOptions,
  isDxCode,
  skipReasonText,
} from "./precheck-findings";

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
  value: null,
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

describe("corrected-claim selection helpers", () => {
  const ncciModifier = edit({
    kind: "add_modifier",
    target: "20610",
    value: "59",
  });
  const modelModifier = edit({
    kind: "add_modifier",
    target: "99213",
    value: "25",
    source: "model",
  });
  const units = edit({ kind: "change_units", target: "J3301", value: "2" });
  const code = edit({
    kind: "change_code",
    target: "99214",
    value: null,
    source: "model",
  });
  const removal = edit({ kind: "remove_line", target: "10002", value: null });
  const note = edit({
    kind: "documentation",
    target: null,
    value: null,
    source: "model",
  });

  it("only claim edits with a target are selectable", () => {
    expect([ncciModifier, units, code, removal, note].map(isClaimEdit)).toEqual(
      [true, true, true, true, false],
    );
    expect(isClaimEdit(edit({ kind: "change_units", target: " " }))).toBe(
      false,
    );
  });

  it("defaults to the report's value, or 59 for an open modifier choice", () => {
    expect(defaultChoice(ncciModifier)).toEqual({
      value: "59",
      remove: false,
      charge: "scale",
    });
    expect(
      defaultChoice(edit({ kind: "add_modifier", target: "1", value: null }))
        .value,
    ).toBe("59");
    expect(defaultChoice(code)).toEqual({
      value: "",
      remove: false,
      charge: "scale",
    });
  });

  it("offers the report's modifier first, then the NCCI set, without duplicates", () => {
    expect(modifierOptions(modelModifier)).toEqual([
      "25",
      "59",
      "XE",
      "XS",
      "XP",
      "XU",
    ]);
    expect(modifierOptions(ncciModifier)).toEqual([
      "59",
      "XE",
      "XS",
      "XP",
      "XU",
    ]);
  });

  it("holds the button until every chosen edit has a valid value", () => {
    expect(
      choiceIsComplete(code, { value: "", remove: false, charge: "scale" }),
    ).toBe(false);
    expect(
      choiceIsComplete(code, {
        value: "99213",
        remove: false,
        charge: "scale",
      }),
    ).toBe(true);
    expect(
      choiceIsComplete(code, { value: "", remove: true, charge: "scale" }),
    ).toBe(true);
    expect(
      choiceIsComplete(units, { value: "0", remove: false, charge: "scale" }),
    ).toBe(false);
    expect(
      choiceIsComplete(units, { value: "12", remove: false, charge: "scale" }),
    ).toBe(true);
    expect(
      choiceIsComplete(ncciModifier, {
        value: "x",
        remove: false,
        charge: "scale",
      }),
    ).toBe(false);
    expect(
      choiceIsComplete(removal, { value: "", remove: false, charge: "scale" }),
    ).toBe(true);
  });

  it("builds the request in index order, sending only what the server needs", () => {
    const edits = [ncciModifier, units, code, removal];
    const chosen = new Map<number, EditChoice>([
      [3, { value: "", remove: false, charge: "scale" }],
      [0, { value: "xs", remove: false, charge: "scale" }],
      [2, { value: "99213", remove: true, charge: "scale" }],
      [1, { value: " 1 ", remove: false, charge: "scale" }],
    ]);
    expect(buildSelections(edits, chosen)).toEqual([
      { index: 0, value: "XS" },
      { index: 1, value: "1", charge: "scale" },
      { index: 2, remove: true },
      { index: 3 },
    ]);
    chosen.set(1, { value: "1", remove: false, charge: "keep" });
    expect(buildSelections(edits, chosen)[1]).toEqual({
      index: 1,
      value: "1",
      charge: "keep",
    });
  });

  it("accepts the ICD-10-CM shapes a Box 21 correction can need", () => {
    for (const code of [
      "N18.5",
      "D509",
      "S72.001A",
      "T36.0X1A",
      "M1A.0X0",
      "U07.1",
      "Z3A.12",
    ]) {
      expect(isDxCode(code)).toBe(true);
    }
    // (HCPCS "J3301" is also dx-shaped — callers test isProcedureCode first.)
    for (const code of ["99213", "N1", "S72.001AB", "abc", "1A2"]) {
      expect(isDxCode(code)).toBe(false);
    }
  });

  it("translates skip reasons and falls back for unknown ones", () => {
    expect(skipReasonText("no_room")).toBe(
      "No space in the box for this value",
    );
    expect(skipReasonText("within_limit")).toBe(
      "No line is over this limit — nothing to reduce",
    );
    expect(skipReasonText("units_span_lines")).toMatch(/change it by hand/);
    expect(skipReasonText("something_new")).toBe("Couldn't apply this change");
    expect(skipReasonText(null)).toBe("Couldn't apply this change");
  });
});

describe("fixTarget", () => {
  const base = finding({ title: "x", suggested_fix: "do something" });
  it("is the claim when the edit is a claim edit or an NCCI finding has a fix", () => {
    expect(
      fixTarget(
        base,
        edit({ kind: "change_units", target: "20610", value: "1" }),
      ),
    ).toBe("claim");
    expect(
      fixTarget(
        finding({ title: "x", suggested_fix: "fix", source: "ncci" }),
        undefined,
      ),
    ).toBe("claim");
  });
  it("is the note for documentation edits and AI-review findings", () => {
    expect(fixTarget(base, edit({ kind: "documentation", target: null }))).toBe(
      "note",
    );
    expect(
      fixTarget(
        finding({ title: "x", suggested_fix: "fix", source: "model" }),
        undefined,
      ),
    ).toBe("note");
  });
  it("is info when there is nothing to do", () => {
    expect(
      fixTarget(finding({ title: "x", suggested_fix: null }), undefined),
    ).toBe("info");
  });
});
