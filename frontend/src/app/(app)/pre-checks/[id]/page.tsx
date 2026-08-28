"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  CheckIcon,
  ChevronDownIcon,
  DownloadIcon,
  ScanLineIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { RiskBadge, StatusBadge } from "@/components/case-badges";
import {
  DocumentsCard,
  ErrorView,
  Field,
  ProcessingView,
} from "@/components/case-view";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { carcMeaning } from "@/lib/carc-codes";
import {
  type CaseDetail,
  type CorrectedClaimDetail,
  createCorrectedClaim,
  fetchCase,
  fetchCaseStatus,
  fetchCorrectedClaimDownloadUrl,
  type ProposedEdit,
  retryCase,
  type RiskFinding,
} from "@/lib/cases";
import { pipelineErrorMessage, toastError } from "@/lib/errors";
import { formatCents, formatDate, humanize } from "@/lib/format";
import {
  attachEditsToFindings,
  buildSelections,
  type ChargeChoice,
  choiceIsComplete,
  defaultChoice,
  type EditChoice,
  isClaimEdit,
  isProcedureCode,
  modifierOptions,
  noteText,
  skipReasonText,
} from "@/lib/precheck-findings";

const SEVERITY_ORDER = ["high", "medium", "low", "info"] as const;

const SEVERITY_META: Record<string, { label: string; token: string }> = {
  high: { label: "High risk", token: "--danger" },
  medium: { label: "Medium risk", token: "--warn" },
  low: { label: "Worth tightening", token: "--info" },
  info: { label: "Notes", token: "--neutral" },
};

export default function PreCheckDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["case", id],
    queryFn: () => fetchCase(id),
  });

  // Same PHI-free poll as the appeal page, driven by the parent query's status.
  const { data: statusPoll, isError: statusPollFailed } = useQuery({
    queryKey: ["case-status", id],
    queryFn: () => fetchCaseStatus(id),
    enabled: data?.status === "processing",
    refetchInterval: data?.status === "processing" ? 2000 : false,
    retry: 3,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["case", id] });

  useEffect(() => {
    if (
      data?.status === "processing" &&
      statusPoll &&
      statusPoll.status !== "processing"
    ) {
      invalidate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusPoll?.status, data?.status]);

  const retry = useMutation({
    mutationFn: () => retryCase(id),
    onSuccess: invalidate,
    onError: (e) => toastError(e),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-6 w-24" />
        </div>
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">
          Couldn&rsquo;t load this pre-check.
        </p>
        <Link
          href="/pre-checks"
          className={buttonVariants({ variant: "outline" })}
        >
          ← Back to pre-checks
        </Link>
      </div>
    );
  }

  const errorMessage = pipelineErrorMessage(data.error_message);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link
          href="/pre-checks"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Pre-checks
        </Link>
        <StatusBadge status={data.status} />
      </div>

      {data.status === "processing" ? (
        <ProcessingView
          stalled={statusPoll?.stalled ?? data.stalled ?? false}
          pollFailed={statusPollFailed}
          onRetry={() => retry.mutate()}
          retrying={retry.isPending}
          title="Checking your claim…"
          description="Reading the draft claim and clinical notes, running CMS bundling and unit edits, and reviewing whether the documentation supports the billed codes. This usually takes under a minute."
          steps={[
            { label: "Documents read", token: "--ok" },
            { label: "Running NCCI edits", token: "--info" },
            { label: "Reviewing documentation", token: "--muted-foreground" },
          ]}
        />
      ) : data.status === "error" ? (
        <ErrorView
          message={errorMessage}
          onRetry={() => retry.mutate()}
          retrying={retry.isPending}
        />
      ) : (
        <>
          <HeaderCard c={data} />
          <RiskSummaryCard c={data} />
          <FindingsCard c={data} onCorrected={invalidate} />
          {data.corrected_claim && (
            <CorrectedClaimCard c={data} corrected={data.corrected_claim} />
          )}
          <DocumentsCard documents={data.documents} />
          <ReportFooter c={data} />
        </>
      )}
    </div>
  );
}

function HeaderCard({ c }: { c: CaseDetail }) {
  return (
    <div className="rounded-lg border border-border bg-card p-[22px] shadow-sm">
      <div className="flex flex-wrap items-center gap-3.5">
        <span className="flex size-12 items-center justify-center rounded-xl bg-muted text-base font-bold">
          {c.patient_initials ?? "—"}
        </span>
        <div className="min-w-40 flex-1">
          <div className="text-lg font-extrabold tracking-tight">
            {c.patient_initials ?? "—"}
            {c.claim_number && (
              <>
                {" · "}
                <span className="font-mono text-sm font-medium text-muted-foreground">
                  {c.claim_number}
                </span>
              </>
            )}
          </div>
          <div className="mt-0.5 text-[13px] text-muted-foreground">
            {c.payer_name ?? "Unknown payer"} · {humanize(c.plan_type)}
          </div>
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4 border-t border-border pt-[18px] sm:grid-cols-3">
        <Field label="Date of service">{formatDate(c.date_of_service)}</Field>
        <Field label="Billed">
          <span className="font-mono">
            {formatCents(c.billed_amount_cents, c.currency)}
          </span>
        </Field>
        <Field label="Codes">{c.extraction?.cpt_codes.join(", ") || "—"}</Field>
      </div>
    </div>
  );
}

function RiskSummaryCard({ c }: { c: CaseDetail }) {
  const report = c.risk_report;
  if (!report) return null;
  const flagged = report.findings.filter(
    (f) => f.severity === "high" || f.severity === "medium",
  ).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Denial risk</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-4">
          <RiskBadge band={report.overall_risk_band} size="lg" />
          <div className="text-sm text-muted-foreground">
            {report.findings.length === 0 ? (
              <>
                No flags found. That&rsquo;s a good sign — it is not a guarantee
                of payment.
              </>
            ) : (
              <>
                {flagged} flag{flagged === 1 ? "" : "s"} likely to matter ·{" "}
                {report.findings.length} finding
                {report.findings.length === 1 ? "" : "s"} total ·{" "}
                {report.deterministic_count} from CMS edit tables,{" "}
                {report.model_count} from documentation review
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Diff-style glyphs for the one-line change inside a finding: removals read as
// deletions, tweaks as modifications, note tasks as writing work.
const EDIT_GLYPH: Record<string, { glyph: string; token: string }> = {
  remove_line: { glyph: "−", token: "--danger" },
  add_modifier: { glyph: "±", token: "--warn" },
  change_units: { glyph: "±", token: "--warn" },
  change_code: { glyph: "±", token: "--warn" },
  documentation: { glyph: "✎", token: "--info" },
};

function FindingsCard({
  c,
  onCorrected,
}: {
  c: CaseDetail;
  onCorrected: () => void;
}) {
  const report = c.risk_report;
  // `expanded` is the user's explicit choice; null = per-row default (closed).
  const [expanded, setExpanded] = useState<boolean | null>(null);
  // Edit index -> the doctor's choice for it. Only claim-kind edits get here.
  const [chosen, setChosen] = useState<Map<number, EditChoice>>(new Map());

  const apply = useMutation({
    mutationFn: (edits: ProposedEdit[]) =>
      createCorrectedClaim(c.id, buildSelections(edits, chosen)),
    onSuccess: () => {
      setChosen(new Map());
      onCorrected();
    },
    onError: (e) => toastError(e, "Couldn't create the corrected claim."),
  });

  if (!report || report.findings.length === 0) return null;

  const edits = report.proposed_edits ?? [];
  const editByFinding = attachEditsToFindings(report.findings, edits);
  // Finding index -> index of its edit in proposed_edits (what the API takes).
  const editIndexByFinding = new Map<number, number>();
  for (const [findingIndex, edit] of editByFinding) {
    editIndexByFinding.set(findingIndex, edits.indexOf(edit));
  }
  const selectable = new Set(
    Array.from(editIndexByFinding.values()).filter((i) =>
      isClaimEdit(edits[i]),
    ),
  );
  const editable = Boolean(c.claim_editable) && selectable.size > 0;
  const allChosen = selectable.size > 0 && chosen.size === selectable.size;
  // Ticked changes still missing a value (e.g. an AI "change the code" edit
  // with no concrete new code). They block the button until filled in, so the
  // rows open themselves and the footer says what's blocking.
  const incomplete = new Set(
    Array.from(chosen.entries())
      .filter(([i, choice]) => !choiceIsComplete(edits[i], choice))
      .map(([i]) => i),
  );
  const complete = incomplete.size === 0;

  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    findings: report.findings
      .map((f, index) => ({ f, index }))
      .filter(({ f }) => f.severity === severity),
  })).filter((g) => g.findings.length > 0);

  function toggle(editIndex: number, on: boolean) {
    setChosen((prev) => {
      const next = new Map(prev);
      if (on) {
        next.set(
          editIndex,
          prev.get(editIndex) ?? defaultChoice(edits[editIndex]),
        );
      } else {
        next.delete(editIndex);
      }
      return next;
    });
  }

  function choose(editIndex: number, choice: EditChoice) {
    setChosen((prev) => new Map(prev).set(editIndex, choice));
  }

  function selectAll(on: boolean) {
    setChosen((prev) => {
      const next = new Map<number, EditChoice>();
      if (on) {
        for (const i of selectable) {
          next.set(i, prev.get(i) ?? defaultChoice(edits[i]));
        }
      }
      return next;
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Findings{" "}
          <span className="font-normal text-muted-foreground">
            ({report.findings.length})
          </span>
        </CardTitle>
        <CardAction>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Collapse all" : "Expand all"}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-5">
        {editable && (
          <p className="text-sm text-muted-foreground">
            Tick the changes you want made to the claim, then create a corrected
            PDF. Findings without a checkbox are documentation work or notes.
          </p>
        )}
        {groups.map((group) => (
          <div key={group.severity}>
            <div
              className="mb-2 text-xs font-semibold tracking-wide uppercase"
              style={{
                color: `var(${SEVERITY_META[group.severity].token})`,
              }}
            >
              {SEVERITY_META[group.severity].label} ({group.findings.length})
            </div>
            <div className="space-y-2">
              {group.findings.map(({ f, index }) => {
                const editIndex = editIndexByFinding.get(index);
                const edit =
                  editIndex === undefined ? undefined : edits[editIndex];
                const canSelect =
                  editable &&
                  editIndex !== undefined &&
                  selectable.has(editIndex);
                return (
                  <Finding
                    // Keyed on the toggle so a native <details> re-mounts and
                    // picks up the new default; a user can still open/close
                    // rows individually afterwards.
                    key={`${f.check_id}-${index}-${expanded}`}
                    f={f}
                    edit={edit}
                    defaultOpen={expanded ?? false}
                    selectable={canSelect}
                    choice={
                      editIndex === undefined
                        ? undefined
                        : chosen.get(editIndex)
                    }
                    needsValue={
                      editIndex !== undefined && incomplete.has(editIndex)
                    }
                    onToggle={
                      canSelect
                        ? (on) => toggle(editIndex as number, on)
                        : undefined
                    }
                    onChoose={
                      canSelect
                        ? (choice) => choose(editIndex as number, choice)
                        : undefined
                    }
                  />
                );
              })}
            </div>
          </div>
        ))}

        {editable ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <span className="text-sm text-muted-foreground">
              {chosen.size === 0
                ? "No changes selected"
                : `${chosen.size} of ${selectable.size} change${
                    selectable.size === 1 ? "" : "s"
                  } selected`}
              {!complete && (
                <span className="block" style={{ color: "var(--warn)" }}>
                  Fill in the new value for {incomplete.size} selected change
                  {incomplete.size === 1 ? "" : "s"} above to continue.
                </span>
              )}
            </span>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => selectAll(!allChosen)}
              >
                {allChosen ? "Clear" : "Select all"}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={chosen.size === 0 || !complete || apply.isPending}
                onClick={() => apply.mutate(edits)}
              >
                {apply.isPending
                  ? "Creating…"
                  : `Create corrected PDF${
                      chosen.size ? ` (${chosen.size})` : ""
                    }`}
              </Button>
            </div>
          </div>
        ) : (
          c.claim_editable === false &&
          selectable.size > 0 && (
            <div className="flex items-start gap-2.5 rounded-md bg-muted p-3 text-xs leading-relaxed text-muted-foreground">
              <ScanLineIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
              <span>
                This claim was uploaded as a scan, so Heimdall can&rsquo;t edit
                it for you. Apply these changes in your billing system — or
                re-run the pre-check with the claim exported from your billing
                software as a PDF to get a corrected copy back.
              </span>
            </div>
          )
        )}
        <p className="text-xs text-muted-foreground">
          Open a finding to see what the payer would object to and how to fix
          it. Apply what fits — you decide what&rsquo;s clinically right.
        </p>
      </CardContent>
    </Card>
  );
}

function Finding({
  f,
  edit,
  defaultOpen,
  selectable,
  choice,
  needsValue,
  onToggle,
  onChoose,
}: {
  f: RiskFinding;
  edit: ProposedEdit | undefined;
  defaultOpen: boolean;
  selectable: boolean;
  choice: EditChoice | undefined;
  needsValue: boolean;
  onToggle?: (on: boolean) => void;
  onChoose?: (choice: EditChoice) => void;
}) {
  const token = SEVERITY_META[f.severity]?.token ?? "--neutral";
  const hasDetail = Boolean(f.explanation || f.suggested_fix || edit);
  const muted = f.severity === "info";
  const checked = Boolean(choice);
  return (
    <div className="flex items-start gap-2.5">
      {selectable && (
        // Outside the <details> so a click here never toggles the row.
        <span className="flex h-11 shrink-0 items-center">
          <Checkbox
            aria-label={`Include this change: ${f.title}`}
            checked={checked}
            onCheckedChange={(on) => onToggle?.(Boolean(on))}
          />
        </span>
      )}
      <details
        className={`group min-w-0 flex-1 overflow-hidden rounded-md border bg-card ${
          muted ? "opacity-80 open:opacity-100" : ""
        } ${checked ? "border-primary/40" : "border-border"}`}
        style={{ borderLeft: `3px solid var(${token})` }}
        // A ticked change that still needs a value opens itself so the input
        // is in view; the user can close it again by hand.
        open={hasDetail && (defaultOpen || needsValue)}
      >
        <summary
          className={`flex items-start gap-3 px-3.5 py-3 marker:content-none [&::-webkit-details-marker]:hidden ${
            hasDetail
              ? "cursor-pointer select-none transition-colors hover:bg-muted/60 group-open:bg-muted/40"
              : "pointer-events-none"
          }`}
        >
          <div className="min-w-0 flex-1">
            <div className="text-sm leading-snug font-semibold">{f.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span>
                {f.source === "ncci"
                  ? "CMS NCCI edit tables"
                  : "AI documentation review"}
              </span>
              {f.predicted_carc && (
                <>
                  <span aria-hidden>·</span>
                  <span>
                    Would deny as{" "}
                    <Badge
                      variant="outline"
                      className="font-mono"
                      title={carcMeaning(f.predicted_carc)}
                    >
                      {f.predicted_carc}
                    </Badge>
                  </span>
                </>
              )}
              {checked && choice && edit && (
                <>
                  <span aria-hidden>·</span>
                  {needsValue ? (
                    <span
                      className="font-medium"
                      style={{ color: "var(--warn)" }}
                    >
                      Needs a value — enter it below
                    </span>
                  ) : (
                    <span className="font-medium text-foreground">
                      {choiceSummary(edit, choice)}
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
          {hasDetail && (
            <ChevronDownIcon
              aria-hidden
              className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
            />
          )}
        </summary>
        {hasDetail && (
          <div className="grid gap-4 border-t border-border px-3.5 py-4 md:grid-cols-2">
            <section>
              <h4 className="mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                What&rsquo;s wrong
              </h4>
              {f.explanation ? (
                <p className="text-sm leading-relaxed">{f.explanation}</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No further detail for this flag.
                </p>
              )}
              {f.predicted_carc && (
                <p className="mt-2 text-xs text-muted-foreground">
                  <span className="font-mono">{f.predicted_carc}</span> —{" "}
                  {carcMeaning(f.predicted_carc)}
                </p>
              )}
            </section>
            <section
              className="rounded-md p-3"
              style={{
                background: `color-mix(in oklab, var(${token}) 7%, var(--card))`,
                border: `1px solid color-mix(in oklab, var(${token}) 25%, var(--border))`,
              }}
            >
              <h4
                className="mb-1.5 text-[11px] font-semibold tracking-wide uppercase"
                style={{ color: `var(${token})` }}
              >
                How to fix it
              </h4>
              {edit && <EditChip edit={edit} />}
              {f.suggested_fix ? (
                <p
                  className={`text-sm leading-relaxed ${edit ? "mt-2.5" : ""}`}
                >
                  {f.suggested_fix}
                </p>
              ) : (
                !edit && (
                  <p className="text-sm text-muted-foreground">
                    Nothing to change — this is for your awareness.
                  </p>
                )
              )}
              {selectable && edit && checked && choice && onChoose && (
                <ChoiceControls
                  edit={edit}
                  choice={choice}
                  onChoose={onChoose}
                />
              )}
            </section>
          </div>
        )}
      </details>
    </div>
  );
}

// The one-line, PM-system version of the fix: glyph, the code it applies to,
// and the imperative instruction.
function EditChip({ edit }: { edit: ProposedEdit }) {
  const meta = EDIT_GLYPH[edit.kind] ?? { glyph: "±", token: "--neutral" };
  return (
    <div className="flex items-start gap-2 rounded border border-border bg-card px-2.5 py-2">
      <span
        aria-hidden
        className="flex size-5 shrink-0 items-center justify-center rounded font-mono text-sm font-bold"
        style={{
          background: `color-mix(in oklab, var(${meta.token}) 16%, var(--card))`,
          color: `var(${meta.token})`,
        }}
      >
        {meta.glyph}
      </span>
      <span className="text-sm leading-snug">
        {edit.target && (
          <span className="mr-1.5 font-mono font-semibold">{edit.target}</span>
        )}
        {edit.instruction}
      </span>
    </div>
  );
}

function choiceSummary(edit: ProposedEdit, choice: EditChoice): string {
  if (choice.remove || edit.kind === "remove_line") {
    return `Will remove ${edit.target}`;
  }
  if (edit.kind === "add_modifier") {
    return `Will add modifier ${choice.value || "…"}`;
  }
  if (edit.kind === "change_units") {
    return `Will set units to ${choice.value || "…"}${
      choice.charge === "keep" ? ", keep the charge" : ", scale the charge"
    }`;
  }
  return `Will change ${edit.target} to ${choice.value || "…"}`;
}

// What exactly gets written, when the doctor has a say: which modifier, how
// many units, which code — or the conservative alternative of dropping the line.
function ChoiceControls({
  edit,
  choice,
  onChoose,
}: {
  edit: ProposedEdit;
  choice: EditChoice;
  onChoose: (choice: EditChoice) => void;
}) {
  if (edit.kind === "remove_line") return null;
  const label =
    edit.kind === "add_modifier"
      ? "Modifier to add"
      : edit.kind === "change_units"
        ? "New unit count"
        : "New code";
  return (
    <div className="mt-3 space-y-2 border-t border-border/60 pt-3">
      <label className="flex flex-wrap items-center gap-2 text-xs">
        <span className="w-28 text-muted-foreground">{label}</span>
        {edit.kind === "add_modifier" ? (
          <NativeSelect
            className="h-7 w-24 text-xs"
            value={choice.value}
            disabled={choice.remove}
            onChange={(e) => onChoose({ ...choice, value: e.target.value })}
          >
            {modifierOptions(edit).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </NativeSelect>
        ) : (
          <Input
            className="h-7 w-24 font-mono text-xs"
            inputMode={edit.kind === "change_units" ? "numeric" : "text"}
            maxLength={edit.kind === "change_units" ? 3 : 5}
            value={choice.value}
            disabled={choice.remove}
            aria-invalid={!choice.remove && !choiceIsComplete(edit, choice)}
            onChange={(e) => onChoose({ ...choice, value: e.target.value })}
          />
        )}
      </label>
      {edit.kind === "change_units" && (
        <label className="flex flex-wrap items-center gap-2 text-xs">
          <span className="w-28 text-muted-foreground">Line charge</span>
          <NativeSelect
            className="h-7 w-64 text-xs"
            value={choice.charge}
            disabled={choice.remove}
            onChange={(e) =>
              onChoose({ ...choice, charge: e.target.value as ChargeChoice })
            }
          >
            <option value="scale">Scale with the units (price × units)</option>
            <option value="keep">Keep as billed (units were a typo)</option>
          </NativeSelect>
        </label>
      )}
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Checkbox
          checked={choice.remove}
          onCheckedChange={(on) => onChoose({ ...choice, remove: Boolean(on) })}
        />
        Remove the {edit.target} line instead
      </label>
    </div>
  );
}

function CorrectedClaimCard({
  c,
  corrected,
}: {
  c: CaseDetail;
  corrected: CorrectedClaimDetail;
}) {
  const [opening, setOpening] = useState(false);
  const applied = corrected.results.filter((r) => r.applied);
  const skipped = corrected.results.filter((r) => !r.applied);

  async function download() {
    setOpening(true);
    try {
      const url = await fetchCorrectedClaimDownloadUrl(c.id);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toastError(e, "Couldn't open the corrected claim.");
    } finally {
      setOpening(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Corrected claim
          <span className="text-xs font-normal text-muted-foreground">
            v{corrected.version} ·{" "}
            {formatDate(corrected.created_at.slice(0, 10))}
          </span>
        </CardTitle>
        {corrected.downloadable && (
          <CardAction>
            <Button size="sm" onClick={download} disabled={opening}>
              <DownloadIcon data-icon="inline-start" />
              {opening ? "Opening…" : "Download PDF"}
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {!corrected.downloadable && (
          <p className="text-sm">
            None of the selected changes could be applied to this PDF, so there
            is nothing to download. Apply them in your billing system.
          </p>
        )}
        {applied.length > 0 && (
          <ul className="space-y-1.5 text-sm">
            {applied.map((r) => (
              <li key={r.index} className="flex items-start gap-2">
                <CheckIcon
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0"
                  style={{ color: "var(--ok)" }}
                />
                <span>
                  {resultText(r)}
                  {noteText(r.note) && (
                    <span className="block text-xs text-muted-foreground">
                      {noteText(r.note)}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {skipped.length > 0 && (
          <ul className="space-y-1.5 text-sm text-muted-foreground">
            {skipped.map((r) => (
              <li key={r.index} className="flex items-start gap-2">
                <span aria-hidden className="mt-0.5 w-4 shrink-0 text-center">
                  –
                </span>
                <span>
                  {resultText(r)} — {skipReasonText(r.reason)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {corrected.total_updated === false && (
          <p
            className="rounded-md bg-muted p-2.5 text-xs leading-relaxed text-muted-foreground"
            style={{ borderLeft: "2px solid var(--warn)" }}
          >
            A line was removed but the total charge (Box 28) couldn&rsquo;t be
            located on this form — update it by hand.
          </p>
        )}
        <p className="text-xs leading-relaxed text-muted-foreground">
          For review — check every changed cell against the note, then re-key
          the claim in your billing system. This PDF is not for submission to
          the payer, and a corrected claim is not a guarantee of payment.
        </p>
      </CardContent>
    </Card>
  );
}

function resultText(r: CorrectedClaimDetail["results"][number]): string {
  const code = r.target ?? "line";
  // A code on several service lines (one per date) is edited on each.
  const lines =
    r.applied && (r.applied_lines ?? 0) > 1
      ? ` (${r.applied_lines} lines)`
      : "";
  // Diagnosis codes live in Box 21, not on a service line.
  const dx = r.target !== null && !isProcedureCode(r.target);
  switch (r.kind) {
    case "remove_line":
      return dx
        ? `Removed diagnosis ${code}`
        : `Removed the ${code} line${lines}`;
    case "add_modifier":
      return `Added modifier ${r.value} to ${code}${lines}`;
    case "change_units": {
      const charge =
        r.charge_before_cents != null && r.charge_after_cents != null
          ? ` · charge ${formatCents(r.charge_before_cents)} → ${formatCents(r.charge_after_cents)}`
          : "";
      return `Set ${code} units to ${r.value}${lines}${charge}`;
    }
    case "change_code":
      return dx
        ? `Changed diagnosis ${code} to ${r.value}`
        : `Changed ${code} to ${r.value}${lines}`;
    default:
      return `${humanize(r.kind)} ${code}`;
  }
}

function ReportFooter({ c }: { c: CaseDetail }) {
  const report = c.risk_report;
  return (
    <p className="rounded-md bg-muted p-3 text-xs leading-relaxed text-muted-foreground">
      Risk flags are informational — not coding or billing advice, and not a
      guarantee the payer will pay or deny this claim. Checks run against the
      Medicare (NCCI) edit baseline; commercial payers largely mirror it but can
      differ, and some CMS unit limits are unpublished. The practice is
      responsible for the final claim. To re-check after fixing the claim, run a
      new pre-check with the corrected documents.
      {report?.ncci_version_tag && (
        <span className="mt-1 block">
          CMS edit data: {report.ncci_version_tag} · checked{" "}
          {formatDate(report.created_at.slice(0, 10))}
        </span>
      )}
    </p>
  );
}
