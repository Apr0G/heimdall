"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  DeadlineBadge,
  OutcomeBadge,
  StatusBadge,
} from "@/components/case-badges";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { carcMeaning } from "@/lib/carc-codes";
import { toastError } from "@/lib/errors";
import { useAuth } from "@/lib/auth-context";
import { useDebouncedValue } from "@/lib/use-debounce";
import {
  type CaseListItem,
  type CaseSummary,
  fetchCases,
  fetchSummary,
  type PendingOutcomeItem,
  submitOutcome,
} from "@/lib/cases";
import { formatCents, formatDate, humanize } from "@/lib/format";

const QUICK_RESULTS: { result: string; label: string; token: string | null }[] =
  [
    { result: "overturned", label: "Overturned", token: "--ok" },
    { result: "upheld", label: "Upheld", token: "--danger" },
    { result: "partial", label: "Partial", token: "--warn" },
    { result: "pending", label: "Still pending", token: null },
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
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";

  // Admins live on /admin; /dashboard is the practice view. The edge proxy only
  // knows "signed in", so the role-aware hop happens here.
  useEffect(() => {
    if (isAdmin) router.replace("/admin");
  }, [isAdmin, router]);

  const [status, setStatus] = useState("all");
  const [payer, setPayer] = useState("");
  const [page, setPage] = useState(1);
  // Debounce so we don't fire a request on every keystroke.
  const debouncedPayer = useDebouncedValue(payer.trim(), 300);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["cases", status, debouncedPayer, page],
    queryFn: () =>
      fetchCases(
        {
          status: status === "all" ? undefined : status,
          payer: debouncedPayer || undefined,
        },
        page,
      ),
    placeholderData: keepPreviousData, // keep the old page visible while the next loads
  });

  const { data: summary, isError: summaryError } = useQuery({
    queryKey: ["case-summary"],
    queryFn: fetchSummary,
  });

  // Capture "now" once (lazy initializer) so render stays pure.
  const [now] = useState(() => Date.now());
  const items = data?.items ?? [];
  const hasFilters = status !== "all" || payer.trim() !== "";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold tracking-tight">Appeals</h1>
          <p className="text-sm text-muted-foreground">
            Track every denial from upload to outcome.
          </p>
        </div>
        <Link href="/cases/new" className={buttonVariants()}>
          + New Appeal
        </Link>
      </div>

      {summary && <RecoveryStats summary={summary} />}
      {summaryError && (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          Couldn&rsquo;t load recovery stats. Refresh to try again.
        </p>
      )}
      {summary && summary.pending_outcomes.length > 0 && (
        <PendingBanner pending={summary.pending_outcomes} />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value ?? "all");
            setPage(1); // jump back to the first page on a filter change
          }}
        >
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
          onChange={(e) => {
            setPayer(e.target.value);
            setPage(1);
          }}
          className="w-64"
        />
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : isError ? (
        <p className="text-sm text-destructive">
          Couldn&rsquo;t load cases. Please try again.
        </p>
      ) : items.length === 0 ? (
        <EmptyState hasFilters={hasFilters} />
      ) : (
        <>
          <CasesTable items={items} now={now} />
          {data && (
            <Pagination
              page={page}
              total={data.total}
              pageSize={data.page_size}
              onPage={setPage}
            />
          )}
        </>
      )}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2 rounded-md border p-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-5 w-12" />
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-5 flex-1" />
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  );
}

function Pagination({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <div className="flex items-center justify-between text-sm text-muted-foreground">
      <span>
        {from}–{to} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </Button>
        <span className="tabular-nums">
          Page {page} of {pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

function CasesTable({ items, now }: { items: CaseListItem[]; now: number }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto rounded-md border">
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
              <TableCell className="font-medium">
                {c.patient_initials ?? "—"}
              </TableCell>
              <TableCell>{formatDate(c.date_of_service)}</TableCell>
              <TableCell>
                <div>{c.payer_name ?? "—"}</div>
                <div className="text-xs text-muted-foreground">
                  {humanize(c.plan_type)}
                </div>
              </TableCell>
              <TableCell className="text-right font-mono font-medium">
                {formatCents(c.denied_amount_cents, c.currency)}
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {c.carc_codes.length === 0
                    ? "—"
                    : c.carc_codes.map((code) => (
                        <Tooltip key={code}>
                          <TooltipTrigger className="cursor-help">
                            <span className="rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-xs">
                              {code}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            {carcMeaning(code)}
                          </TooltipContent>
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
                        {formatCents(c.amount_recovered_cents, c.currency)}{" "}
                        recovered
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
        Upload a denial, the original claim, and your clinical notes to get
        started.
      </p>
      <Link href="/cases/new" className={buttonVariants({ className: "mt-4" })}>
        + New Appeal
      </Link>
    </div>
  );
}

function RecoveryStats({ summary }: { summary: CaseSummary }) {
  const winRate =
    summary.win_rate == null ? "—" : `${Math.round(summary.win_rate * 100)}%`;
  return (
    <div className="grid gap-3.5 sm:grid-cols-3">
      <div className="rounded-lg border border-border bg-card p-[18px] shadow-sm">
        <div className="mb-2 text-[13px] text-muted-foreground">
          Cases this month
        </div>
        <div className="text-3xl font-extrabold tracking-tight tabular-nums">
          {summary.month_case_count}
        </div>
      </div>
      <div className="rounded-lg border border-border bg-card p-[18px] shadow-sm">
        <div className="mb-2 text-[13px] text-muted-foreground">Win rate</div>
        <div className="flex items-baseline gap-2">
          <div className="text-ok text-3xl font-extrabold tracking-tight tabular-nums">
            {winRate}
          </div>
          <span className="text-xs text-muted-foreground">
            {summary.win_count}/{summary.resolved_count} resolved
          </span>
        </div>
      </div>
      <div className="rounded-lg border border-border bg-card p-[18px] shadow-sm">
        <div className="mb-2 text-[13px] text-muted-foreground">Recovered</div>
        <div className="font-mono text-3xl font-extrabold tracking-tight">
          {formatCents(summary.total_recovered_cents)}
        </div>
      </div>
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
      toast.success("Thanks — outcome recorded.");
      queryClient.invalidateQueries({ queryKey: ["case-summary"] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
    onError: (e) => toastError(e),
  });

  return (
    <div
      className="overflow-hidden rounded-lg border"
      style={{
        borderColor: "color-mix(in oklab, var(--warn) 40%, var(--border))",
        background: "color-mix(in oklab, var(--warn) 10%, var(--card))",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left"
      >
        <span
          className="flex size-[26px] shrink-0 items-center justify-center rounded-full text-sm font-bold"
          style={{
            background: "color-mix(in oklab, var(--warn) 22%, var(--card))",
            color: "var(--warn)",
          }}
          aria-hidden
        >
          !
        </span>
        <span className="flex-1 text-sm">
          <strong>
            You have {pending.length} pending case
            {pending.length === 1 ? "" : "s"}.
          </strong>{" "}
          <span className="text-muted-foreground">
            Tell us how they turned out so we can sharpen future estimates.
          </span>
        </span>
        <span className="text-xs text-muted-foreground">
          {open ? "Hide" : "Review"}
        </span>
      </button>
      {open && (
        <div className="space-y-2 px-4 pb-3.5">
          {pending.map((c) => (
            <div
              key={c.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2.5"
            >
              <div className="text-[13px]">
                <span className="font-bold">{c.patient_initials ?? "—"}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · {c.payer_name ?? "Unknown"} ·{" "}
                  <span className="font-mono">
                    {formatCents(c.denied_amount_cents, c.currency)}
                  </span>{" "}
                  · submitted {c.submitted_days_ago}d ago
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {QUICK_RESULTS.map((q) => {
                  const isThis =
                    log.isPending &&
                    log.variables?.id === c.id &&
                    log.variables?.result === q.result;
                  // Disable this case's buttons while one is in flight; other
                  // cases stay clickable.
                  const caseBusy = log.isPending && log.variables?.id === c.id;
                  return (
                    <button
                      key={q.result}
                      disabled={caseBusy}
                      onClick={() => log.mutate({ id: c.id, result: q.result })}
                      className="inline-flex h-[30px] items-center justify-center rounded-[7px] border border-border px-[11px] text-xs font-semibold disabled:opacity-50"
                      style={
                        q.token
                          ? {
                              background: `color-mix(in oklab, var(${q.token}) 14%, var(--card))`,
                              color: `var(${q.token})`,
                            }
                          : { color: "var(--muted-foreground)" }
                      }
                    >
                      {isThis ? <Spinner /> : q.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
