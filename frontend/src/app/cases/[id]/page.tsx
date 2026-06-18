"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  DeadlineBadge,
  OutcomeBadge,
  ProbabilityBadge,
  StatusBadge,
} from "@/components/case-badges";
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
import { carcMeaning } from "@/lib/carc-codes";
import {
  type CaseDetail,
  downloadLetterPdf,
  fetchCase,
  fetchDocumentDownloadUrl,
  markSubmitted,
  type OutcomePayload,
  retryCase,
  submitOutcome,
} from "@/lib/cases";
import { formatCents, formatDate, humanize } from "@/lib/format";

const DISCLAIMER =
  "This is an AI-generated estimate based on case characteristics, not a guarantee. Final decisions rest with the practice.";

const DOC_LABELS: Record<string, string> = {
  denial: "Denial document",
  claim: "Original claim",
  clinical: "Clinical notes",
};

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();
  const [now] = useState(() => Date.now());

  const { data, isLoading, isError } = useQuery({
    queryKey: ["case", id],
    queryFn: () => fetchCase(id),
    // Poll while the pipeline is still working.
    refetchInterval: (query) =>
      query.state.data?.status === "processing" ? 2000 : false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["case", id] });
  const retry = useMutation({ mutationFn: () => retryCase(id), onSuccess: invalidate });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading case…</p>;
  }
  if (isError || !data) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">Couldn&rsquo;t load this case.</p>
        <Link href="/" className={buttonVariants({ variant: "outline" })}>
          ← Back to appeals
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← Appeals
        </Link>
        <StatusBadge status={data.status} />
      </div>

      {data.status === "processing" ? (
        <ProcessingView />
      ) : data.status === "error" ? (
        <ErrorView message={data.error_message} onRetry={() => retry.mutate()} retrying={retry.isPending} />
      ) : (
        <>
          <HeaderCard c={data} now={now} />
          <div className="grid gap-6 lg:grid-cols-2">
            <DenialCard c={data} />
            <AnalysisCard c={data} />
          </div>
          <DocumentsCard c={data} />
          <LetterCard c={data} onChanged={invalidate} />
          {(data.status === "submitted" || data.status === "resolved") && (
            <OutcomeCard c={data} onChanged={invalidate} />
          )}
        </>
      )}
    </div>
  );
}

function ProcessingView() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-foreground" />
        <p className="font-medium">Working on your appeal…</p>
        <p className="text-sm text-muted-foreground">
          Reading your documents, analyzing the denial, and drafting your letter. This usually
          takes under a minute.
        </p>
      </CardContent>
    </Card>
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
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="font-medium text-destructive">Something went wrong processing this case.</p>
        <p className="text-sm text-muted-foreground">{message ?? "An unexpected error occurred."}</p>
        <Button onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-medium">{children}</div>
    </div>
  );
}

function HeaderCard({ c, now }: { c: CaseDetail; now: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          {c.patient_initials ?? "—"} · {c.payer_name ?? "Unknown payer"}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Field label="Plan">{humanize(c.plan_type)}</Field>
        <Field label="Claim #">{c.claim_number ?? "—"}</Field>
        <Field label="Date of service">{formatDate(c.date_of_service)}</Field>
        <Field label="Denial date">{formatDate(c.denial_date)}</Field>
        <Field label="Billed">{formatCents(c.billed_amount_cents, c.currency)}</Field>
        <Field label="Denied">{formatCents(c.denied_amount_cents, c.currency)}</Field>
        <div className="col-span-2 sm:col-span-3 lg:col-span-6">
          <div className="text-xs text-muted-foreground">Appeal deadline</div>
          <div className="mt-1 flex items-center gap-2">
            <DeadlineBadge deadline={c.appeal_deadline} now={now} />
            <span className="text-sm text-muted-foreground">{formatDate(c.appeal_deadline)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
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
                  <span className="text-muted-foreground">{carcMeaning(code)}</span>
                </div>
              ))
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="RARC codes">{ext.rarc_codes.join(", ") || "—"}</Field>
          <Field label="Group codes">{ext.group_codes.join(", ") || "—"}</Field>
          <Field label="Denial category">{humanize(ana?.denial_category)}</Field>
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
    ana.success_probability != null ? `${Math.round(ana.success_probability * 100)}%` : "—";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appeal analysis</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <ProbabilityBadge band={ana.probability_band} />
          <div>
            <div className="text-2xl font-semibold tabular-nums">{pct}</div>
            <div className="text-xs text-muted-foreground">estimated chance of overturning</div>
          </div>
        </div>
        {ana.appealability_reason && <p className="text-sm">{ana.appealability_reason}</p>}
        {ana.reasoning_text && (
          <p className="text-sm text-muted-foreground">{ana.reasoning_text}</p>
        )}
        <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">{DISCLAIMER}</p>
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
            <div key={d.id} className="flex items-center justify-between py-2 first:pt-0 last:pb-0">
              <div>
                <div className="text-sm font-medium">{DOC_LABELS[d.doc_type] ?? humanize(d.doc_type)}</div>
                <div className="text-xs text-muted-foreground">
                  {d.original_filename ?? "document.pdf"}
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => open(d.id)} disabled={opening === d.id}>
                {opening === d.id ? "Opening…" : "View"}
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function LetterCard({ c, onChanged }: { c: CaseDetail; onChanged: () => void }) {
  const [copied, setCopied] = useState(false);
  const submit = useMutation({ mutationFn: () => markSubmitted(c.id), onSuccess: onChanged });

  if (!c.letter) {
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
    await navigator.clipboard.writeText(letter.body ?? "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Appeal letter
          <span className="text-xs font-normal text-muted-foreground">
            v{letter.version} · {humanize(letter.appeal_type)} · {humanize(letter.status)}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={copy}>
            {copied ? "Copied!" : "Copy to clipboard"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadLetterPdf(c.id, `appeal-${c.claim_number ?? c.id}.pdf`)}
          >
            Download PDF
          </Button>
          {c.status === "ready" && (
            <Button size="sm" onClick={() => submit.mutate()} disabled={submit.isPending}>
              {submit.isPending ? "Marking…" : "Mark as submitted"}
            </Button>
          )}
        </div>
        <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-4 font-sans text-sm leading-relaxed">
          {letter.body}
        </pre>
      </CardContent>
    </Card>
  );
}

const RESULT_OPTIONS = ["overturned", "upheld", "partial", "pending", "withdrawn"];

function OutcomeCard({ c, onChanged }: { c: CaseDetail; onChanged: () => void }) {
  const existing = c.outcome;
  const [result, setResult] = useState(existing?.result ?? "overturned");
  const [amount, setAmount] = useState(
    existing?.amount_recovered_cents != null ? String(existing.amount_recovered_cents / 100) : "",
  );
  const [resolutionDate, setResolutionDate] = useState(existing?.resolution_date ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");

  const save = useMutation({
    mutationFn: () => {
      const payload: OutcomePayload = {
        result,
        amount_recovered_cents:
          amount.trim() === "" ? null : Math.round(parseFloat(amount) * 100),
        resolution_date: resolutionDate || null,
        notes: notes.trim() || null,
      };
      return submitOutcome(c.id, payload);
    },
    onSuccess: onChanged,
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
          <Field label="Recovered">{formatCents(existing.amount_recovered_cents, c.currency)}</Field>
          <Field label="Resolved on">{formatDate(existing.resolution_date)}</Field>
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
          Once you hear back from the payer, record what happened — it sharpens future estimates.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Result</Label>
            <Select value={result} onValueChange={(v) => setResult(v ?? "overturned")}>
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
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
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
            <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        {save.isError && (
          <p className="text-sm text-destructive">Couldn&rsquo;t save the outcome. Try again.</p>
        )}
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : existing?.result ? "Update outcome" : "Save outcome"}
        </Button>
      </CardContent>
    </Card>
  );
}
