import type { ProposedEdit, RiskFinding } from "@/lib/cases";

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
