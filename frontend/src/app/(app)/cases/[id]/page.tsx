"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  DeadlineBadge,
  OutcomeBadge,
  ProbabilityBadge,
  StatusBadge,
} from "@/components/case-badges";
import { FileDrop, type SlotStatus } from "@/components/file-drop";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { carcMeaning } from "@/lib/carc-codes";
import { copyToClipboard } from "@/lib/clipboard";
import {
  type CaseDetail,
  downloadLetterPdf,
  fetchCase,
  fetchCaseStatus,
  fetchDocumentDownloadUrl,
  type LetterDetail,
  markSubmitted,
  type OutcomePayload,
  retryCase,
  submitOutcome,
} from "@/lib/cases";
import { toastError } from "@/lib/errors";
import { CONTACT_MAILTO } from "@/lib/site";
import {
  centsToInputString,
  formatCents,
  formatDate,
  humanize,
} from "@/lib/format";
import { type AdditionalDocType, reanalyzeWithUploads } from "@/lib/upload";

const DISCLAIMER =
  "This is an AI-generated estimate based on case characteristics, not a guarantee. Final decisions rest with the practice.";

const DOC_LABELS: Record<string, string> = {
  denial: "Denial document",
  claim: "Original claim",
  clinical: "Clinical notes",
  prior_auth: "Prior authorization",
  prior_treatment: "Prior treatment records",
};

// Conditional doc types the user can upload to trigger a re-draft (Phase 12).
const UPLOADABLE_ADDITIONAL: AdditionalDocType[] = [
  "prior_auth",
  "prior_treatment",
];

const ADDITIONAL_HINTS: Record<AdditionalDocType, string> = {
  prior_auth: "The payer's prior authorization / precertification approval.",
  prior_treatment:
    "Records showing prior conservative treatment (e.g. failed step therapy).",
};

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();
  const [now] = useState(() => Date.now());

  const { data, isLoading, isError } = useQuery({
    queryKey: ["case", id],
    queryFn: () => fetchCase(id),
  });

  // While processing, poll a PHI-free status endpoint (no audit row per poll)
  // instead of re-fetching the full audited detail every 2s.
  const { data: statusPoll, isError: statusPollFailed } = useQuery({
    queryKey: ["case-status", id],
    queryFn: () => fetchCaseStatus(id),
    enabled: data?.status === "processing",
    // Driven by the PARENT query's status, not by the poll's own last result.
    // Keying off `query.state.data` meant two consecutive failures left
    // `data` undefined, the interval became false, and polling stopped
    // permanently — stranding the case on a spinner with no error and no retry.
    // The poll is only enabled while the parent says "processing" anyway, so the
    // parent is the correct authority for when to stop.
    refetchInterval: data?.status === "processing" ? 2000 : false,
    retry: 3,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["case", id] });

  // When the poll shows the pipeline finished, refetch the full detail once.
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
    return <CaseDetailSkeleton />;
  }
  if (isError || !data) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">
          Couldn&rsquo;t load this case.
        </p>
        <Link
          href="/dashboard"
          className={buttonVariants({ variant: "outline" })}
        >
          ← Back to appeals
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link
          href="/dashboard"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Appeals
        </Link>
        <StatusBadge status={data.status} />
      </div>

      {data.status === "processing" ? (
        <ProcessingView
          stalled={statusPoll?.stalled ?? data.stalled ?? false}
          // A poll that has exhausted its retries shows the same way out as a
          // stall. Otherwise the user sits on a spinner forever with no signal
          // that we stopped listening.
          pollFailed={statusPollFailed}
          onRetry={() => retry.mutate()}
          retrying={retry.isPending}
        />
      ) : data.status === "error" ? (
        <ErrorView
          message={data.error_message}
          onRetry={() => retry.mutate()}
          retrying={retry.isPending}
        />
      ) : (
        <>
          <HeaderCard c={data} now={now} />
          <div className="grid gap-6 lg:grid-cols-2">
            <DenialCard c={data} />
            <AnalysisCard c={data} />
          </div>
          <DocumentsCard c={data} />
          <AdditionalDocsCard c={data} onChanged={invalidate} />
          <LetterCard c={data} onChanged={invalidate} />
          {(data.status === "submitted" || data.status === "resolved") && (
            <OutcomeCard c={data} onChanged={invalidate} />
          )}
        </>
      )}
    </div>
  );
}

function CaseDetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-6 w-24" />
      </div>
      <Skeleton className="h-28 w-full" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function ProcessingView({
  stalled,
  pollFailed = false,
  onRetry,
  retrying,
}: {
  stalled: boolean;
  pollFailed?: boolean;
  onRetry: () => void;
  retrying: boolean;
}) {
  // The pipeline runs in-process, so a deploy/crash can strand a case in
  // `processing`. Once the server flags it stalled — or once we can no longer
  // reach the status endpoint at all — offer a way out rather than spinning.
  if (stalled || pollFailed) {
    return (
      <div className="flex flex-col items-center rounded-lg border border-border bg-card px-6 py-24 text-center shadow-sm">
        <span
          className="mb-5 flex size-[52px] items-center justify-center rounded-full text-2xl font-bold"
          style={{
            background: "color-mix(in oklab, var(--warn) 16%, var(--card))",
            color: "var(--warn)",
          }}
          aria-hidden
        >
          ⏱
        </span>
        <div className="mb-2 text-xl font-extrabold tracking-tight">
          This is taking longer than expected
        </div>
        <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
          Your documents are safe — nothing was lost. The analysis didn&rsquo;t
          finish, which can happen after a system update. Retry to pick it back
          up.
        </p>
        <div className="mt-6 flex gap-2.5">
          <Button onClick={onRetry} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry"}
          </Button>
          <a
            href={CONTACT_MAILTO}
            className={buttonVariants({ variant: "outline" })}
          >
            Contact support
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center rounded-lg border border-border bg-card px-6 py-24 text-center shadow-sm">
      <span className="mb-6 size-11 animate-spin rounded-full border-[3px] border-border border-t-primary" />
      <div className="mb-2 text-xl font-extrabold tracking-tight">
        Reading your documents…
      </div>
      <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
        Analyzing the denial, matching CARC/RARC codes, and drafting your appeal
        letter. This usually takes under a minute.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3 text-[12.5px]">
        <span className="text-ok inline-flex items-center gap-1.5">
          <span className="bg-ok size-1.5 rounded-full" />
          Documents read
        </span>
        <span className="text-info inline-flex items-center gap-1.5">
          <span className="bg-info size-1.5 rounded-full" />
          Analyzing denial
        </span>
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          <span className="size-1.5 rounded-full bg-muted-foreground" />
          Drafting letter
        </span>
      </div>
    </div>
  );
}

function ErrorView({
  message,
  onRetry,
  retrying,
}: {
  message: string | null;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-border bg-card px-6 py-24 text-center shadow-sm">
      <span
        className="mb-5 flex size-[52px] items-center justify-center rounded-full text-2xl font-bold"
        style={{
          background: "color-mix(in oklab, var(--danger) 16%, var(--card))",
          color: "var(--danger)",
        }}
        aria-hidden
      >
        !
      </span>
      <div className="mb-2 text-xl font-extrabold tracking-tight">
        We couldn&rsquo;t finish this analysis
      </div>
      <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
        {message ??
          "Something went wrong while reading your documents. Your files are safe — nothing was lost. Try again, and if it keeps happening, email us."}
      </p>
      <div className="mt-6 flex gap-2.5">
        <Button onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
        <a
          href={CONTACT_MAILTO}
          className={buttonVariants({ variant: "outline" })}
        >
          Contact support
        </a>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-medium">{children}</div>
    </div>
  );
}

function HeaderCard({ c, now }: { c: CaseDetail; now: number }) {
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
        <div className="flex items-center gap-2">
          <DeadlineBadge deadline={c.appeal_deadline} now={now} />
          <span className="text-sm text-muted-foreground">
            {formatDate(c.appeal_deadline)}
          </span>
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4 border-t border-border pt-[18px] sm:grid-cols-4">
        <Field label="Date of service">{formatDate(c.date_of_service)}</Field>
        <Field label="Denial date">{formatDate(c.denial_date)}</Field>
        <Field label="Billed">
          <span className="font-mono">
            {formatCents(c.billed_amount_cents, c.currency)}
          </span>
        </Field>
        <Field label="Denied">
          <span
            className="font-mono font-bold"
            style={{ color: "var(--danger)" }}
          >
            {formatCents(c.denied_amount_cents, c.currency)}
          </span>
        </Field>
      </div>
      {c.deadline_note && c.appeal_deadline && (
        <p className="mt-3 flex items-start gap-1.5 border-t border-border pt-3 text-[12.5px] text-muted-foreground">
          <span aria-hidden style={{ color: "var(--warn)" }}>
            ⚠
          </span>
          <span>{c.deadline_note}</span>
        </p>
      )}
    </div>
  );
}

function DenialCard({ c }: { c: CaseDetail }) {
  const ext = c.extraction;
  const ana = c.analysis;
  if (!ext) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Denial summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="text-xs text-muted-foreground">CARC codes</div>
          <div className="mt-1 space-y-1">
            {ext.carc_codes.length === 0 ? (
              <span className="text-sm">—</span>
            ) : (
              ext.carc_codes.map((code) => (
                <div key={code} className="text-sm">
                  <Badge variant="outline" className="mr-2">
                    {code}
                  </Badge>
                  <span className="text-muted-foreground">
                    {carcMeaning(code)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="RARC codes">{ext.rarc_codes.join(", ") || "—"}</Field>
          <Field label="Group codes">{ext.group_codes.join(", ") || "—"}</Field>
          <Field label="Denial category">
            {humanize(ana?.denial_category)}
          </Field>
          <Field label="Appealable">
            {ana == null ? "—" : ana.is_appealable ? "Yes" : "No"}
          </Field>
        </div>
        {(ext.cpt_codes.length > 0 || ext.icd10_codes.length > 0) && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="CPT/HCPCS">{ext.cpt_codes.join(", ") || "—"}</Field>
            <Field label="ICD-10">{ext.icd10_codes.join(", ") || "—"}</Field>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AnalysisCard({ c }: { c: CaseDetail }) {
  const ana = c.analysis;
  if (!ana) return null;
  const pct =
    ana.success_probability != null
      ? `${Math.round(ana.success_probability * 100)}%`
      : "—";
  const pctToken =
    ana.probability_band === "high"
      ? "--ok"
      : ana.probability_band === "moderate"
        ? "--warn"
        : ana.probability_band === "low"
          ? "--danger"
          : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appeal analysis</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <ProbabilityBadge band={ana.probability_band} />
          <div>
            <div
              className="text-[32px] font-extrabold tracking-tight tabular-nums"
              style={pctToken ? { color: `var(${pctToken})` } : undefined}
            >
              {pct}
            </div>
            <div className="text-xs text-muted-foreground">
              estimated chance of overturning
            </div>
          </div>
        </div>
        {ana.appealability_reason && (
          <p className="text-sm">{ana.appealability_reason}</p>
        )}
        {ana.reasoning_text && (
          <p className="text-sm text-muted-foreground">{ana.reasoning_text}</p>
        )}
        <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
          {DISCLAIMER}
        </p>
      </CardContent>
    </Card>
  );
}

function DocumentsCard({ c }: { c: CaseDetail }) {
  const [opening, setOpening] = useState<string | null>(null);

  async function open(docId: string) {
    setOpening(docId);
    try {
      const url = await fetchDocumentDownloadUrl(docId);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toastError(e, "Couldn't open the document.");
    } finally {
      setOpening(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
      </CardHeader>
      <CardContent className="divide-y">
        {c.documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents.</p>
        ) : (
          c.documents.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between py-2 first:pt-0 last:pb-0"
            >
              <div>
                <div className="text-sm font-medium">
                  {DOC_LABELS[d.doc_type] ?? humanize(d.doc_type)}
                </div>
                <div className="text-xs text-muted-foreground">
                  {d.original_filename ?? "document.pdf"}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => open(d.id)}
                disabled={opening === d.id}
              >
                {opening === d.id ? "Opening…" : "View"}
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function AdditionalDocsCard({
  c,
  onChanged,
}: {
  c: CaseDetail;
  onChanged: () => void;
}) {
  const requested = c.analysis?.additional_documents_needed ?? [];
  const uploaded = new Set(c.documents.map((d) => d.doc_type));
  const pending = UPLOADABLE_ADDITIONAL.filter(
    (t) => requested.includes(t) && !uploaded.has(t),
  );

  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [status, setStatus] = useState<Record<string, SlotStatus>>({});
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [submitting, setSubmitting] = useState(false);

  // Only render when the analysis asked for docs we can actually accept.
  if (pending.length === 0) return null;

  const selected = pending.filter((t) => files[t]);

  function select(type: string, file: File | null, error: string | null) {
    setFiles((p) => ({ ...p, [type]: file }));
    setErrors((p) => ({ ...p, [type]: error }));
    setStatus((p) => ({ ...p, [type]: "idle" }));
    setProgress((p) => ({ ...p, [type]: 0 }));
  }

  async function onSubmit() {
    if (selected.length === 0 || submitting) return;
    setSubmitting(true);
    setStatus((p) => {
      const next = { ...p };
      for (const t of selected) next[t] = "uploading";
      return next;
    });
    try {
      await reanalyzeWithUploads(
        c.id,
        selected.map((t) => ({ docType: t, file: files[t] as File })),
        (docType, pct) => {
          setProgress((p) => ({ ...p, [docType]: pct }));
          if (pct >= 100) setStatus((p) => ({ ...p, [docType]: "done" }));
        },
      );
      toast.success("Re-analyzing with the new documents…");
      onChanged();
    } catch (e) {
      toastError(e, "Upload failed. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Additional documents requested</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          These documents would strengthen the appeal. Upload what you have and
          we&rsquo;ll re-draft the letter with them.
        </p>
        {pending.map((t) => (
          <FileDrop
            key={t}
            label={DOC_LABELS[t] ?? humanize(t)}
            hint={ADDITIONAL_HINTS[t]}
            example={ADDITIONAL_HINTS[t]}
            file={files[t] ?? null}
            status={status[t] ?? "idle"}
            progress={progress[t] ?? 0}
            error={errors[t] ?? null}
            onSelect={(file, error) => select(t, file, error)}
          />
        ))}
        <Button
          onClick={onSubmit}
          disabled={selected.length === 0 || submitting}
        >
          {submitting ? "Re-analyzing…" : "Re-run with these documents"}
        </Button>
      </CardContent>
    </Card>
  );
}

function LetterCard({
  c,
  onChanged,
}: {
  c: CaseDetail;
  onChanged: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const submit = useMutation({
    mutationFn: () => markSubmitted(c.id),
    onSuccess: () => {
      toast.success("Marked as submitted.");
      onChanged();
    },
    onError: (e) => toastError(e),
  });

  // Gate on the BODY, not on the letter object. A letter row with body: "" is
  // truthy, so this used to render the full card — version chips, status chips,
  // an empty body block and an ACTIVE Download button that 404s. The backend now
  // refuses to persist an empty body at all, but the UI must not depend on that
  // to avoid showing a download that cannot work.
  if (!c.letter?.body?.trim()) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Appeal letter</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {c.analysis && !c.analysis.is_appealable
              ? "This denial was assessed as not appealable, so no letter was drafted. Review the analysis above."
              : "No letter is available for this case."}
          </p>
        </CardContent>
      </Card>
    );
  }

  const letter = c.letter;
  async function copy() {
    try {
      await copyToClipboard(letter.body ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy. Select the letter text and copy manually.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Appeal letter
          <span className="text-xs font-normal text-muted-foreground">
            v{letter.version} · {humanize(letter.appeal_type)} ·{" "}
            {humanize(letter.status)}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p
          className="rounded-md bg-muted p-2.5 text-xs leading-relaxed text-muted-foreground"
          style={{ borderLeft: "2px solid var(--warn)" }}
        >
          AI-drafted. Review the whole letter — codes, dates, amounts, and every
          policy citation — and edit as needed before submitting. The practice
          is responsible for the final letter, its accuracy, and meeting the
          filing deadline.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={copy}>
            {copied ? "Copied!" : "Copy to clipboard"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              downloadLetterPdf(
                c.id,
                `appeal-${c.patient_initials ?? "case"}-${c.id.slice(0, 8)}.pdf`,
              )
            }
          >
            Download PDF
          </Button>
          {c.status === "ready" && (
            <Button
              size="sm"
              onClick={() => submit.mutate()}
              disabled={submit.isPending}
            >
              {submit.isPending ? "Marking…" : "Mark as submitted"}
            </Button>
          )}
        </div>
        <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-4 font-sans text-sm leading-relaxed">
          {letter.body}
        </pre>
        {c.letters.length > 1 && <LetterHistory letters={c.letters.slice(1)} />}
      </CardContent>
    </Card>
  );
}

function LetterHistory({ letters }: { letters: LetterDetail[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="border-t pt-3">
      <p className="mb-2 text-xs font-medium text-muted-foreground">
        Previous versions ({letters.length})
      </p>
      <div className="space-y-2">
        {letters.map((l) => (
          <div key={l.id} className="rounded-md border">
            <button
              type="button"
              onClick={() => setOpen((o) => (o === l.id ? null : l.id))}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted/40"
            >
              <span>
                v{l.version} · {humanize(l.appeal_type)}
                <span className="ml-2 text-xs text-muted-foreground">
                  {formatDate(l.created_at.slice(0, 10))}
                </span>
              </span>
              <span className="text-xs text-muted-foreground">
                {open === l.id ? "Hide" : "View"}
              </span>
            </button>
            {open === l.id && (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t bg-muted/20 p-3 font-sans text-xs leading-relaxed">
                {l.body}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const RESULT_OPTIONS = [
  "overturned",
  "upheld",
  "partial",
  "pending",
  "withdrawn",
];

// Strict money parse: "" -> null (not reported), a valid dollar amount -> integer
// cents, anything else -> "invalid" (block submit). parseFloat silently turned
// "1,234.50" into $1.00 and junk into NaN -> null, corrupting the recovery
// dashboard and the training labels.
function parseAmountToCents(raw: string): number | null | "invalid" {
  const t = raw.trim();
  if (t === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return "invalid";
  const cents = Math.round(Number(t) * 100);
  return Number.isSafeInteger(cents) && cents >= 0 ? cents : "invalid";
}

function OutcomeCard({
  c,
  onChanged,
}: {
  c: CaseDetail;
  onChanged: () => void;
}) {
  const existing = c.outcome;
  const [result, setResult] = useState(existing?.result ?? "overturned");
  const [amount, setAmount] = useState(
    centsToInputString(existing?.amount_recovered_cents),
  );
  const [resolutionDate, setResolutionDate] = useState(
    existing?.resolution_date ?? "",
  );
  const [notes, setNotes] = useState(existing?.notes ?? "");

  const amountCents = parseAmountToCents(amount);
  const amountInvalid = amountCents === "invalid";

  const save = useMutation({
    mutationFn: () => {
      const payload: OutcomePayload = {
        result,
        amount_recovered_cents: amountCents === "invalid" ? null : amountCents,
        resolution_date: resolutionDate || null,
        notes: notes.trim() || null,
      };
      return submitOutcome(c.id, payload);
    },
    onSuccess: () => {
      toast.success("Outcome saved.");
      onChanged();
    },
    onError: (e) => toastError(e),
  });

  // Resolved + already reported -> read-only display.
  if (c.status === "resolved" && existing?.result) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Outcome</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <div className="text-xs text-muted-foreground">Result</div>
            <div className="mt-1">
              <OutcomeBadge result={existing.result} />
            </div>
          </div>
          <Field label="Recovered">
            {formatCents(existing.amount_recovered_cents, c.currency)}
          </Field>
          <Field label="Resolved on">
            {formatDate(existing.resolution_date)}
          </Field>
          <Field label="Notes">{existing.notes ?? "—"}</Field>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Log the outcome</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Once you hear back from the payer, record what happened — it sharpens
          future estimates.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Result</Label>
            <Select
              value={result}
              onValueChange={(v) => setResult(v ?? "overturned")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RESULT_OPTIONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {humanize(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Amount recovered</Label>
            <Input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              placeholder="0.00"
              value={amount}
              aria-invalid={amountInvalid}
              onChange={(e) => setAmount(e.target.value)}
            />
            {amountInvalid && (
              <p className="text-xs text-destructive">
                Enter a dollar amount like 1234.50.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label>Resolution date</Label>
            <Input
              type="date"
              value={resolutionDate}
              onChange={(e) => setResolutionDate(e.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Notes</Label>
            <Textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending || amountInvalid}
        >
          {save.isPending
            ? "Saving…"
            : existing?.result
              ? "Update outcome"
              : "Save outcome"}
        </Button>
      </CardContent>
    </Card>
  );
}
