"use client";

import { useState, type CSSProperties } from "react";

import { cn } from "@/lib/utils";

// Same status-pill recipe the real app uses (see case-badges.tsx): 16% of the
// status token mixed into the card, with token-colored text. Keeps the preview
// visually honest — it's the actual design language, not a fake screenshot.
function tone(token: string): CSSProperties {
  return {
    background: `color-mix(in oklab, var(${token}) 16%, var(--card))`,
    color: `var(${token})`,
  };
}

const PILL =
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold";
const LABEL =
  "text-[11px] font-bold uppercase tracking-wider text-muted-foreground";

type Tab = "pre-check" | "appeal";

/** A stylized in-product preview shown in the hero — built from the app's own
 * primitives so visitors see what Heimdall does without a real screenshot.
 * Tabbed like the app's own Pre-checks / Appeals control: one window, both
 * halves of the product. */
export function HeroPreview() {
  const [tab, setTab] = useState<Tab>("pre-check");

  return (
    <div className="mx-auto mt-16 max-w-3xl">
      <div className="overflow-hidden rounded-xl border border-border bg-card text-left shadow-xl">
        {/* window chrome, with the app's segmented control */}
        <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-4 py-2">
          <span className="size-2.5 rounded-full bg-red-400/70" />
          <span className="size-2.5 rounded-full bg-amber-400/80" />
          <span className="size-2.5 rounded-full bg-green-400/70" />
          <div
            role="tablist"
            aria-label="Preview Heimdall"
            className="ml-3 flex items-center gap-0.5 rounded-full border border-border bg-muted p-[3px] text-xs"
          >
            <PreviewTab
              active={tab === "pre-check"}
              onClick={() => setTab("pre-check")}
            >
              Pre-check
            </PreviewTab>
            <PreviewTab
              active={tab === "appeal"}
              onClick={() => setTab("appeal")}
            >
              Appeal
            </PreviewTab>
          </div>
          <span className={`${PILL} ml-auto`} style={tone("--ok")}>
            ready
          </span>
        </div>

        {tab === "pre-check" ? <PreCheckPanel /> : <AppealPanel />}
      </div>
      <p className="mt-3 text-center text-xs text-muted-foreground">
        Catch it before you submit — or fight it after the denial. Same three
        documents, same workspace.
      </p>
    </div>
  );
}

function PreviewTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-0.5 font-semibold transition-colors",
        active
          ? "bg-card text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function PreCheckPanel() {
  return (
    <div className="animate-panel grid gap-5 p-5 sm:grid-cols-2">
      <div className="space-y-4">
        <div>
          <div className={LABEL}>Draft claim · before submission</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">99214 + 20610-RT</span>
            <span
              className="rounded-md px-2 py-0.5 text-xs font-bold"
              style={tone("--danger")}
            >
              High risk
            </span>
          </div>
        </div>

        <div className="space-y-2" aria-label="Risk flags">
          <Flag token="--danger" carc="CO-97">
            E/M with modifier 25 won&rsquo;t survive the same-day procedure
          </Flag>
          <Flag token="--warn" carc="CO-150">
            Note supports 99213, not the billed 99214
          </Flag>
          <Flag token="--ok" carc={null}>
            Units &amp; diagnosis codes pass CMS edits
          </Flag>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-background p-3.5">
        <div className={LABEL}>Suggested fix</div>
        <p className="mt-2.5 text-[12px] leading-relaxed text-foreground/75">
          The injection was the scheduled purpose of the visit. Remove the
          99214-25 line, or document a separately identifiable evaluation before
          submitting
          <span className="ml-0.5 inline-block h-3.5 w-px translate-y-[3px] animate-pulse bg-amber-600" />
        </p>
        <div className="mt-3 border-t border-border pt-2.5 text-[11px] text-muted-foreground">
          Fixed in 2 minutes — instead of denied in 30 days.
        </div>
      </div>
    </div>
  );
}

function Flag({
  token,
  carc,
  children,
}: {
  token: string;
  carc: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border bg-background px-2.5 py-2">
      <span
        aria-hidden
        className="mt-1 size-2 shrink-0 rounded-full"
        style={{ background: `var(${token})` }}
      />
      <span className="text-[12.5px] leading-snug">{children}</span>
      {carc && (
        <span
          className="ml-auto shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10.5px] font-bold"
          style={tone(token)}
        >
          {carc}
        </span>
      )}
    </div>
  );
}

function AppealPanel() {
  return (
    <div className="animate-panel grid gap-5 p-5 sm:grid-cols-2">
      <div className="space-y-4">
        <div>
          <div className={LABEL}>Denial reason</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span
              className="rounded-md px-2 py-0.5 text-xs font-bold"
              style={tone("--warn")}
            >
              CO-197
            </span>
            <span className="text-sm font-medium">Precertification absent</span>
          </div>
          <span className={`${PILL} mt-2`} style={tone("--ok")}>
            ✓ Appealable
          </span>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <span className={LABEL}>Estimated success</span>
            <span className="text-sm font-extrabold">72%</span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full w-[72%] rounded-full bg-gradient-to-r from-amber-500 to-blue-500" />
          </div>
        </div>

        <div>
          <div className={LABEL}>Recovered if won</div>
          <div className="mt-1 text-lg font-extrabold">$1,240.00</div>
        </div>
      </div>

      {/* drafted letter */}
      <div className="rounded-lg border border-border bg-background p-3.5">
        <div className={LABEL}>Draft appeal letter</div>
        <div className="mt-2.5 space-y-1.5" aria-hidden>
          <div className="h-2 w-4/5 rounded bg-muted" />
          <div className="h-2 w-full rounded bg-muted" />
          <div className="h-2 w-11/12 rounded bg-muted" />
        </div>
        <p className="mt-2.5 text-[12px] leading-relaxed text-foreground/75">
          Per the attached operative note and CPT guidance, the service was
          medically necessary and precertification is documented on file
          <span className="ml-0.5 inline-block h-3.5 w-px translate-y-[3px] animate-pulse bg-amber-600" />
        </p>
      </div>
    </div>
  );
}
