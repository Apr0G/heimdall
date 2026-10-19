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
