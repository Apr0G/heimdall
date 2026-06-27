import { toast } from "sonner";

type ToastAction = { label: string; onClick: () => void };

/**
 * Show a toast that does NOT auto-dismiss while the tab is hidden. The 5-second
 * dismissal timer only runs while the Heimdall tab is actually visible, so a
 * notification fired while the user is on another tab stays put until they come
 * back — then it lingers for 5 seconds and clears.
 */
export function notifyUntilSeen(
  type: "success" | "error",
  message: string,
  action?: ToastAction,
) {
  const show = type === "error" ? toast.error : toast.success;
  const id = show(message, {
    duration: Infinity, // we control dismissal ourselves
    action,
  });

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

  document.addEventListener("visibilitychange", onVisibility);
  onVisibility(); // start now if the tab is already visible
}
