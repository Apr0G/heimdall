"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { RiskBadge, StatusBadge } from "@/components/case-badges";
import {
  DocumentsCard,
  ErrorView,
  Field,
  ProcessingView,
} from "@/components/case-view";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { carcMeaning } from "@/lib/carc-codes";
import {
  type CaseDetail,
  fetchCase,
  fetchCaseStatus,
  retryCase,
  type RiskFinding,
} from "@/lib/cases";
import { toastError } from "@/lib/errors";
import { formatCents, formatDate, humanize } from "@/lib/format";

const SEVERITY_ORDER = ["high", "medium", "low", "info"] as const;

const SEVERITY_META: Record<string, { label: string; token: string }> = {
  high: { label: "High risk", token: "--danger" },
  medium: { label: "Medium risk", token: "--warn" },
  low: { label: "Worth tightening", token: "--info" },
  info: { label: "Notes", token: "--neutral" },
};

// The pipeline's typed failure for an unreadable claim; translate the PHI-free
// error name into copy a biller can act on.
const NO_LINES_MESSAGE =
  "We couldn't read any billable lines from the claim document. Check that the right file was uploaded — it should be the draft CMS-1500 with the CPT and diagnosis codes filled in.";

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

  const errorMessage = data.error_message?.includes("NoBillableLinesError")
    ? NO_LINES_MESSAGE
    : data.error_message;

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
          <FindingsCard c={data} />
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

function FindingsCard({ c }: { c: CaseDetail }) {
  const report = c.risk_report;
  if (!report || report.findings.length === 0) return null;

  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    findings: report.findings.filter((f) => f.severity === severity),
  })).filter((g) => g.findings.length > 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Findings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
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
            <div className="space-y-2.5">
              {group.findings.map((f, i) => (
                <Finding key={`${f.check_id}-${i}`} f={f} />
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function Finding({ f }: { f: RiskFinding }) {
  const token = SEVERITY_META[f.severity]?.token ?? "--neutral";
  return (
    <div
      className="rounded-md border border-border bg-card p-3.5"
      style={{ borderLeft: `3px solid var(${token})` }}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="text-sm font-semibold">{f.title}</div>
        <div className="flex shrink-0 items-center gap-1.5">
          {f.predicted_carc && (
            <Badge variant="outline" title={carcMeaning(f.predicted_carc)}>
              {f.predicted_carc}
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">
            {f.source === "ncci" ? "CMS edit tables" : "AI review"}
          </span>
        </div>
      </div>
      {f.explanation && (
        <p className="mt-1.5 text-sm text-muted-foreground">{f.explanation}</p>
      )}
      {f.suggested_fix && (
        <p className="mt-2 text-sm">
          <span className="font-medium">Suggested fix: </span>
          {f.suggested_fix}
        </p>
      )}
    </div>
  );
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
