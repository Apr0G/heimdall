import { cn } from "@/lib/utils";

/** Text wordmark with a small shield mark (Heimdall = the guardian). */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <svg viewBox="0 0 24 24" className="size-5 text-primary" aria-hidden>
        <path
          d="M12 2 4 5v6c0 5 3.4 8.3 8 11 4.6-2.7 8-6 8-11V5l-8-3Z"
          fill="currentColor"
          opacity="0.15"
        />
        <path
          d="M12 2 4 5v6c0 5 3.4 8.3 8 11 4.6-2.7 8-6 8-11V5l-8-3Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </svg>
      <span>Heimdall</span>
    </span>
  );
}
