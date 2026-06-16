import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const RED = "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
const AMBER = "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
const GREEN = "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";
const MUTED = "bg-muted text-muted-foreground";

export function DeadlineBadge({ deadline, now }: { deadline: string | null; now: number }) {
  if (!deadline) return <span className="text-muted-foreground">—</span>;
  const days = Math.ceil((new Date(`${deadline}T00:00:00`).getTime() - now) / 86_400_000);
  // Red < 7 days, yellow < 14 days, green otherwise.
  const tone = days < 7 ? RED : days < 14 ? AMBER : GREEN;
  const label = days < 0 ? `${Math.abs(days)}d overdue` : days === 0 ? "Due today" : `${days}d left`;
  return <Badge className={cn("border-transparent font-medium", tone)}>{label}</Badge>;
}

const STATUS_TONE: Record<string, string> = {
  draft: MUTED,
  processing: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  ready: GREEN,
  submitted: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
  resolved: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  error: RED,
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge className={cn("border-transparent capitalize", STATUS_TONE[status] ?? MUTED)}>
      {status}
    </Badge>
  );
}

const OUTCOME_TONE: Record<string, { label: string; tone: string }> = {
  overturned: { label: "Overturned ✓", tone: GREEN },
  upheld: { label: "Upheld ✗", tone: RED },
  partial: { label: "Partial 🟡", tone: AMBER },
  pending: { label: "Pending", tone: MUTED },
  withdrawn: { label: "Withdrawn", tone: MUTED },
};

export function OutcomeBadge({ result }: { result: string }) {
  const o = OUTCOME_TONE[result] ?? { label: result, tone: MUTED };
  return <Badge className={cn("border-transparent", o.tone)}>{o.label}</Badge>;
}
