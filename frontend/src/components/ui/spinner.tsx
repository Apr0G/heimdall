import { cn } from "@/lib/utils";

/** Lightweight CSS spinner (no icon dependency). */
export function Spinner({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn(
        "size-4 animate-spin rounded-full border-2 border-muted border-t-foreground",
        className,
      )}
    />
  );
}

export function LoadingRow({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Spinner />
      {label}
    </div>
  );
}
