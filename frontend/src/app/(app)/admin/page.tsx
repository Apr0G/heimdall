"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { type AdminOverview, fetchAdminOverview } from "@/lib/admin";
import { useAuth } from "@/lib/auth-context";
import { formatCents, humanize } from "@/lib/format";

// Fixed display order (matches the backend enums); the payload zero-fills every
// member so these never need key-checks.
const CASE_STATUSES = [
  "draft",
  "processing",
  "ready",
  "submitted",
  "resolved",
  "error",
];
const RUN_PURPOSES = [
  "extraction",
  "analysis",
  "letter_draft",
  "classification",
];
const OUTCOME_RESULTS = [
  "overturned",
  "partial",
  "upheld",
  "withdrawn",
  "pending",
];

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const plain = new Intl.NumberFormat("en-US");

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  // UX guard only — the real gate is require_role("admin") on the API.
  useEffect(() => {
    if (!loading && user && user.role !== "admin") router.replace("/dashboard");
  }, [loading, user, router]);

  const isAdmin = user?.role === "admin";
  const overview = useQuery({
    queryKey: ["admin-overview"],
    queryFn: fetchAdminOverview,
    // Don't fire a guaranteed-403 request during the redirect frame.
    enabled: isAdmin,
  });

  if (!isAdmin) return null;

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Admin overview
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Global aggregates across all practices. Every view of this page is
          audit-logged.
        </p>
      </div>

      {overview.isLoading && (
        <div className="grid gap-3.5 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      )}
      {overview.isError && (
        <div className="rounded-md border border-dashed p-10 text-center text-sm text-muted-foreground">
          Couldn&apos;t load the overview. Refresh to try again.
        </div>
      )}
      {overview.data && <Overview data={overview.data} />}
    </main>
  );
}

function StatTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-[18px] shadow-sm">
      <div className="mb-2 text-[13px] text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-extrabold tracking-tight tabular-nums">
          {value}
        </div>
        {detail && (
          <span className="text-xs text-muted-foreground">{detail}</span>
        )}
      </div>
    </div>
  );
}

function CountsRow({
  order,
  counts,
}: {
  order: string[];
  counts: Record<string, number>;
}) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-lg border border-border bg-card p-[18px] text-sm shadow-sm">
      {order.map((key) => (
        <div key={key} className="flex items-baseline gap-1.5">
          <span className="text-muted-foreground">{humanize(key)}</span>
          <span className="font-semibold tabular-nums">
            {plain.format(counts[key] ?? 0)}
          </span>
        </div>
      ))}
    </div>
  );
}

function Overview({ data }: { data: AdminOverview }) {
  const winRate =
    data.outcomes.win_rate == null
      ? "—"
      : `${Math.round(data.outcomes.win_rate * 100)}%`;
  return (
    <div className="space-y-8">
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile label="Practices" value={plain.format(data.practice_count)} />
        <StatTile
          label="Users"
          value={plain.format(data.users.total)}
          detail={`${plain.format(data.users.active)} active`}
        />
        <StatTile
          label="Cases"
          value={plain.format(data.cases.total)}
          detail={`${plain.format(data.cases.by_status.error ?? 0)} in error`}
        />
        <StatTile
          label="Recovered"
          value={formatCents(data.outcomes.amount_recovered_cents)}
          detail={`win rate ${winRate}`}
        />
        <StatTile
          label="Est. model cost"
          value={formatCents(data.model_runs.estimated_cost_cents)}
          detail={`${plain.format(data.model_runs.total)} runs`}
        />
        <StatTile
          label="Tokens"
          value={compact.format(
            data.model_runs.input_tokens + data.model_runs.output_tokens,
          )}
          detail={`${compact.format(data.model_runs.input_tokens)} in / ${compact.format(data.model_runs.output_tokens)} out`}
        />
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">
          Cases by status
        </h2>
        <CountsRow order={CASE_STATUSES} counts={data.cases.by_status} />
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">
          Model runs by purpose
        </h2>
        <CountsRow order={RUN_PURPOSES} counts={data.model_runs.by_purpose} />
        <p className="text-xs text-muted-foreground">
          {plain.format(data.model_runs.error_count)} failed runs
          {data.model_runs.avg_latency_ms != null &&
            ` · ${plain.format(Math.round(data.model_runs.avg_latency_ms))} ms avg latency`}
          {" · cost is an estimate from token counts, not the AWS bill"}
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Outcomes</h2>
        <CountsRow order={OUTCOME_RESULTS} counts={data.outcomes.by_result} />
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">
          Storage &amp; letters
        </h2>
        <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-lg border border-border bg-card p-[18px] text-sm shadow-sm">
          <div className="flex items-baseline gap-1.5">
            <span className="text-muted-foreground">Documents</span>
            <span className="font-semibold tabular-nums">
              {plain.format(data.documents.count)}
            </span>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-muted-foreground">Stored</span>
            <span className="font-semibold tabular-nums">
              {formatBytes(data.documents.total_bytes)}
            </span>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-muted-foreground">Appeal letters</span>
            <span className="font-semibold tabular-nums">
              {plain.format(data.appeal_letter_count)}
            </span>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-muted-foreground">Denied (all cases)</span>
            <span className="font-semibold tabular-nums">
              {formatCents(data.cases.denied_amount_cents)}
            </span>
          </div>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Practices</h2>
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Practice</TableHead>
                <TableHead className="text-right">Users</TableHead>
                <TableHead className="text-right">Cases</TableHead>
                <TableHead className="text-right">Resolved</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">Est. cost</TableHead>
                <TableHead className="text-right">Recovered</TableHead>
                <TableHead className="text-right">Last activity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.practices.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <span className="font-medium">{p.name}</span>
                    {p.state && (
                      <span className="ml-1.5 text-muted-foreground">
                        {p.state}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {plain.format(p.user_count)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {plain.format(p.case_count)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {plain.format(p.cases_by_status.resolved ?? 0)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {plain.format(p.cases_by_status.error ?? 0)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {compact.format(p.input_tokens + p.output_tokens)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCents(p.estimated_cost_cents)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCents(p.amount_recovered_cents)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatDateTime(p.last_activity_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
