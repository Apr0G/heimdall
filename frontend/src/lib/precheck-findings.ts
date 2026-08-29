import type {
  CorrectedClaimSelection,
  ProposedEdit,
  RiskFinding,
} from "@/lib/cases";

// Pair each proposed edit with the finding it fixes, so the report can show
// the one-line change inside the finding instead of as a separate list.
//
// The API keeps findings and edits as parallel lists with no explicit link:
// the NCCI engine emits both from the same PTP hit / MUE violation, and the
// review prompt tells the model to derive edits only from its own findings.
// The stable join key is the edit's `target` code, which both sides name in
// the finding title ("20610 will be denied as bundled into 99213…"). Each
// finding takes at most one edit and each edit lands on at most one finding;
// an edit whose target no finding mentions is simply not shown — its prose
// `suggested_fix` already covers the same ground.
export function attachEditsToFindings(
  findings: RiskFinding[],
  edits: ProposedEdit[],
): Map<number, ProposedEdit> {
  const byFinding = new Map<number, ProposedEdit>();
  for (const edit of edits) {
    const target = edit.target?.trim();
    if (!target) continue;
    const index = findings.findIndex(
      (finding, i) =>
        !byFinding.has(i) &&
        finding.source === edit.source &&
        mentionsCode(finding.title, target),
    );
    if (index !== -1) byFinding.set(index, edit);
  }
  return byFinding;
}

// Whole-token match so "2061" does not hit "20610". Codes are alphanumeric
// (CPT "99213", HCPCS "J3301"); anything else around them is a boundary.
function mentionsCode(text: string, code: string): boolean {
  const escaped = code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^A-Za-z0-9])${escaped}(?![A-Za-z0-9])`, "i").test(
    text,
  );
}

// --- corrected-claim selection --------------------------------------------

// Edit kinds the in-place patcher can apply. `documentation` is a task for
// the clinician's note, not a change to the claim.
export const CLAIM_EDIT_KINDS = new Set([
  "remove_line",
  "add_modifier",
  "change_units",
  "change_code",
]);

// NCCI-associated modifiers — the ones a bundling edit can be bypassed with.
export const MODIFIER_OPTIONS = ["59", "XE", "XS", "XP", "XU"];

export type ChargeChoice = "scale" | "keep";

// `charge` matters for unit changes only: "scale" rewrites the line charge as
// price-per-unit × new units (how billing systems build 24F); "keep" leaves it
// for a units typo. Only the practice knows which.
export type EditChoice = {
  value: string;
  remove: boolean;
  charge: ChargeChoice;
};

export function isClaimEdit(edit: ProposedEdit): boolean {
  return CLAIM_EDIT_KINDS.has(edit.kind) && Boolean(edit.target?.trim());
}

// What the checkbox applies before the doctor changes anything: the report's
// own value, or the most widely accepted modifier when it left the choice open.
export function defaultChoice(edit: ProposedEdit): EditChoice {
  const value =
    edit.value ?? (edit.kind === "add_modifier" ? MODIFIER_OPTIONS[0] : "");
  return { value, remove: false, charge: "scale" };
}

export function modifierOptions(edit: ProposedEdit): string[] {
  return Array.from(
    new Set([...(edit.value ? [edit.value] : []), ...MODIFIER_OPTIONS]),
  );
}

// A choice that would be rejected server-side is not sent — the button stays
// disabled instead of round-tripping a 422.
export function choiceIsComplete(
  edit: ProposedEdit,
  choice: EditChoice,
): boolean {
  if (choice.remove || edit.kind === "remove_line") return true;
  const v = choice.value.trim().toUpperCase();
  if (edit.kind === "add_modifier") return /^[A-Z0-9]{2}$/.test(v);
  if (edit.kind === "change_units") return /^[1-9]\d{0,2}$/.test(v);
  if (edit.kind === "change_code") return isProcedureCode(v) || isDxCode(v);
  return false;
}

// CPT (5 digits, or 4 + F/T/U) or HCPCS level II (letter + 4 digits).
export function isProcedureCode(code: string): boolean {
  return /^(\d{5}|\d{4}[FTU]|[A-Z]\d{4})$/.test(code.trim().toUpperCase());
}

// ICD-10-CM, with or without the decimal the paper form omits ("D509").
// Category: letter, digit, then digit or letter (C4A, M1A); up to four
// alphanumeric extension characters (X placeholders, a 7th-character
// encounter code: S72.001A, T36.0X1A). The U chapter is live (U07.1). Must
// match backend schemas/precheck.py and services/claim_patch.py.
export function isDxCode(code: string): boolean {
  return /^[A-Z]\d[A-Z0-9](\.?[A-Z0-9]{1,4})?$/.test(code.trim().toUpperCase());
}

export function buildSelections(
  edits: ProposedEdit[],
  chosen: Map<number, EditChoice>,
): CorrectedClaimSelection[] {
  return Array.from(chosen.entries())
    .sort(([a], [b]) => a - b)
    .map(([index, choice]) => {
      const edit = edits[index];
      if (choice.remove) return { index, remove: true };
      if (edit.kind === "remove_line") return { index };
      const value = choice.value.trim().toUpperCase();
      if (edit.kind === "change_units")
        return { index, value, charge: choice.charge };
      return { index, value };
    });
}

// Skip reasons from services/claim_patch.py, in the doctor's words.
export const SKIP_REASON_TEXT: Record<string, string> = {
  line_not_found: "Couldn't find this code on the claim",
  ambiguous_line: "This code is on more than one line — apply by hand",
  modifier_slots_full: "All four modifier positions are already used",
  already_present: "Already on the claim",
  no_room: "No space in the box for this value",
  bad_value: "Not a valid value",
  unsupported_kind: "Not a claim change",
  not_a_service_line:
    "That's a diagnosis code — modifiers and units apply to service lines",
  within_limit: "No line is over this limit — nothing to reduce",
  units_span_lines:
    "The day's total is over the limit but no single line is — decide which line loses units and change it by hand",
};

export function skipReasonText(reason: string | null): string {
  return (reason && SKIP_REASON_TEXT[reason]) || "Couldn't apply this change";
}

// Advisory notes on an applied edit.
export const NOTE_TEXT: Record<string, string> = {
  check_dx_pointers:
    "Check the diagnosis pointers (Box 24E) on any line that referenced it",
  charge_not_scaled:
    "Charge left as it was — the per-unit price didn't divide to the cent, so set it and the total by hand",
};

export function noteText(note: string | null | undefined): string | null {
  return (note && NOTE_TEXT[note]) || null;
}

// Where a finding's fix lands. "claim": a change to the CMS-1500 the patcher
// can make (tickable). "note": something only the clinician can do — the
// record has to say what happened, or the claim has to change to match it.
// "info": nothing to change.
export type FixTarget = "claim" | "note" | "info";

export function fixTarget(
  finding: RiskFinding,
  edit: ProposedEdit | undefined,
): FixTarget {
  if (edit && isClaimEdit(edit)) return "claim";
  if (edit?.kind === "documentation") return "note";
  if (!finding.suggested_fix) return "info";
  return finding.source === "ncci" ? "claim" : "note";
}

export const FIX_TARGET_LABEL: Record<FixTarget, string> = {
  claim: "Claim change",
  note: "Note task",
  info: "Info",
};

export const FIX_TARGET_TITLE: Record<FixTarget, string> = {
  claim: "Change on the claim (CMS-1500)",
  note: "Add to the clinical note",
  info: "Nothing to change",
};
