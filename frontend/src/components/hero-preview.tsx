import type { CSSProperties } from "react";

// Same status-pill recipe the real app uses (see case-badges.tsx): 16% of the
// status token mixed into the card, with token-colored text. Keeps the preview
// visually honest — it's the actual design language, not a fake screenshot.
function tone(token: string): CSSProperties {
  return {
    background: `color-mix(in oklab, var(${token}) 16%, var(--card))`,
    color: `var(${token})`,
  };
}

const PILL = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold";
const LABEL = "text-[11px] font-bold uppercase tracking-wider text-muted-foreground";

/** A stylized in-product preview shown in the hero — built from the app's own
 * primitives so visitors see what Heimdall does without a real screenshot. */
export function HeroPreview() {
  return (
    <div className="mx-auto mt-16 max-w-3xl">
      <div className="overflow-hidden rounded-xl border border-border bg-card text-left shadow-xl">
        {/* window chrome */}
        <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-4 py-2.5">
          <span className="size-2.5 rounded-full bg-red-400/70" />
          <span className="size-2.5 rounded-full bg-amber-400/80" />
          <span className="size-2.5 rounded-full bg-green-400/70" />
          <span className="ml-2 text-xs font-medium text-muted-foreground">
            Case CLM-TEST-0481 · Blue Cross PPO
          </span>
          <span className={`${PILL} ml-auto`} style={tone("--ok")}>
            ready
          </span>
        </div>

        {/* body */}
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <div className="space-y-4">
            <div>
              <div className={LABEL}>Denial reason</div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="rounded-md px-2 py-0.5 text-xs font-bold" style={tone("--warn")}>
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
              Per the attached operative note and CPT guidance, the service was medically necessary
              and precertification is documented on file
              <span className="ml-0.5 inline-block h-3.5 w-px translate-y-[3px] animate-pulse bg-amber-600" />
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
