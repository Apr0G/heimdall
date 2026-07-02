import { cn } from "@/lib/utils";

/** Gradient shield mark + extrabold wordmark (matches the design system). */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 font-extrabold tracking-tight",
        className,
      )}
    >
      <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 shadow-sm">
        <svg viewBox="0 0 24 26" className="size-3.5" fill="none" aria-hidden>
          <path
            d="M12 1 22 5v8c0 6.5-4.3 10.4-10 12C6.3 23.4 2 19.5 2 13V5l10-4Z"
            fill="white"
            fillOpacity="0.92"
          />
        </svg>
      </span>
      <span>Heimdall</span>
    </span>
  );
}
