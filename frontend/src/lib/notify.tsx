import { toast } from "sonner";

import { cn } from "@/lib/utils";

/**
 * Show a clickable toast that does NOT auto-dismiss while the tab is hidden. The
 * whole toast is a button (clicking it runs `onClick`). The 5-second dismissal
 * timer only runs while the Heimdall tab is visible, so a notification fired
 * while the user is on another tab waits until they come back, then clears.
 */
export function notifyUntilSeen(
  type: "success" | "error",
  message: string,
  onClick?: () => void,
) {
  let timer: ReturnType<typeof setTimeout> | undefined;

  const cleanup = () => {
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  };

  function onVisibility() {
    clearTimeout(timer);
    if (document.visibilityState === "visible") {
      // Restart the 5s countdown each time the tab becomes visible.
      timer = setTimeout(() => {
        toast.dismiss(id);
        cleanup();
      }, 5000);
    }
  }

  const id = toast.custom(
    (t) => (
      <button
        type="button"
        onClick={() => {
          onClick?.();
          toast.dismiss(t);
          cleanup();
        }}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg border bg-popover px-4 py-3 text-left",
          "text-sm font-medium text-popover-foreground shadow-lg transition-colors hover:bg-accent",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "size-2 shrink-0 rounded-full",
            type === "error" ? "bg-red-500" : "bg-emerald-500",
          )}
        />
        <span className="flex-1">{message}</span>
      </button>
    ),
    { duration: Infinity }, // we control dismissal ourselves
  );

  document.addEventListener("visibilitychange", onVisibility);
  onVisibility(); // start now if the tab is already visible
}
