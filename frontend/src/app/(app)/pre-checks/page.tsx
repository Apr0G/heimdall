"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RiskBadge, StatusBadge } from "@/components/case-badges";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
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
import { useAuth } from "@/lib/auth-context";
import { type CaseListItem, fetchCases } from "@/lib/cases";
import { formatCents, formatDate, humanize } from "@/lib/format";
import { useDebouncedValue } from "@/lib/use-debounce";

// Pre-checks never reach submitted/resolved (appeal-only states).
const STATUS_OPTIONS = ["all", "processing", "ready", "error"];

export default function PreChecksPage() {
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";

  // Admins live on /admin; pre-checks are the practice view (same hop as
  // /dashboard — the edge proxy only knows "signed in").
  useEffect(() => {
    if (isAdmin) router.replace("/admin");
  }, [isAdmin, router]);

  const [status, setStatus] = useState("all");
  const [payer, setPayer] = useState("");
  const [page, setPage] = useState(1);
  const debouncedPayer = useDebouncedValue(payer.trim(), 300);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pre-checks", status, debouncedPayer, page],
    queryFn: () =>
      fetchCases(
        {
          case_type: "pre_check",
          status: status === "all" ? undefined : status,
          payer: debouncedPayer || undefined,
        },
        page,
      ),
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];
  const hasFilters = status !== "all" || payer.trim() !== "";
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold tracking-tight">
            Pre-checks
          </h1>
          <p className="text-sm text-muted-foreground">
            Screen a claim for denial risk before you submit it.
          </p>
        </div>
        <Link href="/pre-checks/new" className={buttonVariants()}>
          + New Pre-check
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value ?? "all");
            setPage(1);
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
        <div className="space-y-2 rounded-md border p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-5 w-12" />
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-5 flex-1" />
              <Skeleton className="h-5 w-20" />
            </div>
          ))}
        </div>
      ) : isError ? (
        <p className="text-sm text-destructive">
          Couldn&rsquo;t load pre-checks. Please try again.
        </p>
      ) : items.length === 0 ? (
        <EmptyState hasFilters={hasFilters} />
      ) : (
        <>
          <PreChecksTable items={items} />
          {pages > 1 && data && (
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {(page - 1) * data.page_size + 1}–
                {Math.min(page * data.page_size, data.total)} of {data.total}
              </span>
              <div className="flex items-center gap-2">
                <button
                  className={buttonVariants({
                    variant: "outline",
                    size: "sm",
                  })}
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Previous
                </button>
                <span className="tabular-nums">
                  Page {page} of {pages}
                </span>
                <button
                  className={buttonVariants({
                    variant: "outline",
                    size: "sm",
                  })}
                  disabled={page >= pages}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PreChecksTable({ items }: { items: CaseListItem[] }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Patient</TableHead>
            <TableHead>DOS</TableHead>
            <TableHead>Payer</TableHead>
            <TableHead className="text-right">Billed</TableHead>
            <TableHead>Risk</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((c) => (
            <TableRow
              key={c.id}
              onClick={() => router.push(`/pre-checks/${c.id}`)}
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
                {formatCents(c.billed_amount_cents, c.currency)}
              </TableCell>
              <TableCell>
                {c.status === "ready" ? (
                  <RiskBadge band={c.overall_risk_band} />
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell>
                <StatusBadge status={c.status} />
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
        No pre-checks match your filters.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-dashed p-12 text-center">
      <h2 className="text-lg font-medium">No pre-checks yet</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Upload a draft claim and its clinical notes before you submit to the
        payer — Heimdall flags likely denials while you can still fix them.
      </p>
      <Link
        href="/pre-checks/new"
        className={buttonVariants({ className: "mt-4" })}
      >
        + New Pre-check
      </Link>
    </div>
  );
}
