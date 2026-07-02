import type { CSSProperties } from "react";

import { cn } from "@/lib/utils";

// A token-tinted pill: 16% of the status color mixed into the card, colored text.
function tone(token: string, textToken?: string): CSSProperties {
  return {
    background: `color-mix(in oklab, var(${token}) 16%, var(--card))`,
    color: `var(${textToken ?? token})`,
  };
}

const PILL = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap";

export function DeadlineBadge({ deadline, now }: { deadline: string | null; now: number }) {
  if (!deadline) return <span className="text-muted-foreground">—</span>;
  const days = Math.ceil((new Date(`${deadline}T00:00:00`).getTime() - now) / 86_400_000);
  // Red < 7 days, amber < 14 days, green otherwise.
  const token = days < 7 ? "--danger" : days < 14 ? "--warn" : "--ok";
  const label = days < 0 ? `${Math.abs(days)}d overdue` : days === 0 ? "Due today" : `${days}d left`;
  return (
    <span className={cn(PILL, "font-bold")} style={tone(token)}>
      {label}
    </span>
  );
}

const STATUS: Record<string, { token: string; text?: string; dot?: boolean }> = {
  draft: { token: "--neutral" },
  processing: { token: "--info", dot: true },
  ready: { token: "--ok" },
  submitted: { token: "--indigo" },
  resolved: { token: "--neutral", text: "--muted-foreground" },
  error: { token: "--danger" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { token: "--neutral", text: "--muted-foreground" };
  return (
    <span className={cn(PILL, "capitalize")} style={tone(s.token, s.text)}>
      {s.dot && (
        <span
          className="size-1.5 rounded-full"
          style={{ background: `var(${s.token})` }}
          aria-hidden
        />
      )}
      {status}
    </span>
  );
}

const OUTCOME: Record<string, { label: string; token: string; text?: string }> = {
  overturned: { label: "✓ Overturned", token: "--ok" },
  upheld: { label: "✗ Upheld", token: "--danger" },
  partial: { label: "Partial", token: "--warn" },
  pending: { label: "Pending", token: "--neutral", text: "--muted-foreground" },
  withdrawn: { label: "Withdrawn", token: "--neutral", text: "--muted-foreground" },
};

export function OutcomeBadge({ result }: { result: string }) {
  const o = OUTCOME[result] ?? { label: result, token: "--neutral", text: "--muted-foreground" };
  return (
    <span className={PILL} style={tone(o.token, o.text)}>
      {o.label}
    </span>
  );
}

const BAND: Record<string, string> = { low: "--danger", moderate: "--warn", high: "--ok" };

export function ProbabilityBadge({ band }: { band: string | null }) {
  if (!band) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="inline-flex items-center rounded-md px-4 py-2 text-[15px] font-extrabold capitalize"
      style={tone(BAND[band] ?? "--neutral")}
    >
      {band}
    </span>
  );
}
