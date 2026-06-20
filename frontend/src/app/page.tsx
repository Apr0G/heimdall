"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DeadlineBadge, OutcomeBadge, StatusBadge } from "@/components/case-badges";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { carcMeaning } from "@/lib/carc-codes";
import {
  type CaseListItem,
  type CaseSummary,
  fetchCases,
  fetchSummary,
  type PendingOutcomeItem,
  submitOutcome,
} from "@/lib/cases";
import { formatCents, formatDate, humanize } from "@/lib/format";

const QUICK_RESULTS: { result: string; label: string }[] = [
  { result: "overturned", label: "Overturned" },
  { result: "upheld", label: "Upheld" },
  { result: "partial", label: "Partial" },
  { result: "pending", label: "Still pending" },
];

const STATUS_OPTIONS = [
  "all",
  "draft",
  "processing",
  "ready",
  "submitted",
  "resolved",
  "error",
];

export default function DashboardPage() {
  const [status, setStatus] = useState("all");
  const [payer, setPayer] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["cases", status, payer],
    queryFn: () =>
      fetchCases({ status: status === "all" ? undefined : status, payer: payer || undefined }),
  });

  const { data: summary } = useQuery({ queryKey: ["case-summary"], queryFn: fetchSummary });

  // Capture "now" once (lazy initializer) so render stays pure.
  const [now] = useState(() => Date.now());
  const items = data?.items ?? [];
  const hasFilters = status !== "all" || payer.trim() !== "";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Appeals</h1>
          <p className="text-sm text-muted-foreground">Track and act on your denied claims.</p>
        </div>
        <Link href="/cases/new" className={buttonVariants()}>
          + New Appeal
        </Link>
      </div>

      {summary && <RecoveryStats summary={summary} />}
      {summary && summary.pending_outcomes.length > 0 && (
        <PendingBanner pending={summary.pending_outcomes} />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Select value={status} onValueChange={(value) => setStatus(value ?? "all")}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "all" ? "All statuses" : humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          placeholder="Search payer…"
          value={payer}
          onChange={(e) => setPayer(e.target.value)}
          className="w-64"
        />
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading cases…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">Couldn&rsquo;t load cases. Please try again.</p>
      ) : items.length === 0 ? (
        <EmptyState hasFilters={hasFilters} />
      ) : (
        <CasesTable items={items} now={now} />
      )}
    </div>
  );
}

function CasesTable({ items, now }: { items: CaseListItem[]; now: number }) {
  const router = useRouter();
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Patient</TableHead>
            <TableHead>DOS</TableHead>
            <TableHead>Payer</TableHead>
            <TableHead className="text-right">Denied</TableHead>
            <TableHead>CARC</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Deadline</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Outcome</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((c) => (
            <TableRow
              key={c.id}
              onClick={() => router.push(`/cases/${c.id}`)}
              className="cursor-pointer"
            >
              <TableCell className="font-medium">{c.patient_initials ?? "—"}</TableCell>
              <TableCell>{formatDate(c.date_of_service)}</TableCell>
              <TableCell>
                <div>{c.payer_name ?? "—"}</div>
                <div className="text-xs text-muted-foreground">{humanize(c.plan_type)}</div>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCents(c.denied_amount_cents, c.currency)}
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {c.carc_codes.length === 0
                    ? "—"
                    : c.carc_codes.map((code) => (
                        <Tooltip key={code}>
                          <TooltipTrigger className="cursor-help">
                            <Badge variant="outline">{code}</Badge>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">{carcMeaning(code)}</TooltipContent>
                        </Tooltip>
                      ))}
                </div>
              </TableCell>
              <TableCell>{humanize(c.denial_category)}</TableCell>
              <TableCell>
                <div className="flex flex-col gap-0.5">
                  <DeadlineBadge deadline={c.appeal_deadline} now={now} />
                  <span className="text-xs text-muted-foreground">
                    {formatDate(c.appeal_deadline)}
                  </span>
                </div>
              </TableCell>
              <TableCell>
                <StatusBadge status={c.status} />
              </TableCell>
              <TableCell>
                {c.outcome_result ? (
                  <div className="flex flex-col gap-0.5">
                    <OutcomeBadge result={c.outcome_result} />
                    {c.amount_recovered_cents != null && (
                      <span className="text-xs text-muted-foreground">
                        {formatCents(c.amount_recovered_cents, c.currency)} recovered
                      </span>
                    )}
                  </div>
                ) : (
                  "—"
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  if (hasFilters) {
    return (
      <div className="rounded-md border border-dashed p-10 text-center text-sm text-muted-foreground">
        No cases match your filters.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-dashed p-12 text-center">
      <h2 className="text-lg font-medium">No appeals yet</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Upload a denial, the original claim, and your clinical notes to get started.
      </p>
      <Link href="/cases/new" className={buttonVariants({ className: "mt-4" })}>
        + New Appeal
      </Link>
    </div>
  );
}

function RecoveryStats({ summary }: { summary: CaseSummary }) {
  const winRate = summary.win_rate == null ? "—" : `${Math.round(summary.win_rate * 100)}%`;
  const stats: { label: string; value: string; hint?: string }[] = [
    { label: "Cases this month", value: String(summary.month_case_count) },
    {
      label: "Win rate",
      value: winRate,
      hint: `${summary.win_count}/${summary.resolved_count} resolved`,
    },
    { label: "Recovered", value: formatCents(summary.total_recovered_cents) },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {stats.map((s) => (
        <Card key={s.label}>
          <CardContent className="py-4">
            <div className="text-xs text-muted-foreground">{s.label}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{s.value}</div>
            {s.hint && <div className="text-xs text-muted-foreground">{s.hint}</div>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function PendingBanner({ pending }: { pending: PendingOutcomeItem[] }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const log = useMutation({
    mutationFn: ({ id, result }: { id: string; result: string }) =>
      submitOutcome(id, { result }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-summary"] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/40">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm">
          <span className="font-medium">
            You have {pending.length} pending case{pending.length === 1 ? "" : "s"}.
          </span>{" "}
          Tell us how they turned out so we can sharpen future estimates.
        </p>
        <Button variant="outline" size="sm" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "Review"}
        </Button>
      </div>
      {open && (
        <div className="mt-3 divide-y divide-amber-200 dark:divide-amber-900">
          {pending.map((c) => (
            <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="text-sm">
                <span className="font-medium">{c.patient_initials ?? "—"}</span>{" "}
                <span className="text-muted-foreground">
                  · {c.payer_name ?? "Unknown"} ·{" "}
                  {formatCents(c.denied_amount_cents, c.currency)} · submitted{" "}
                  {c.submitted_days_ago}d ago
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {QUICK_RESULTS.map((q) => (
                  <Button
                    key={q.result}
                    variant="outline"
                    size="sm"
                    disabled={log.isPending}
                    onClick={() => log.mutate({ id: c.id, result: q.result })}
                  >
                    {q.label}
                  </Button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
