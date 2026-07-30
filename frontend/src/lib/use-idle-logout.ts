import { useEffect, useRef } from "react";

// Activity is broadcast across tabs so any one tab's interaction keeps the whole
// session alive. Without this, listeners bound to `window` only saw their own
// tab: a user working in tab B for 20 minutes would have tab A fire the idle
// handler — and because that handler performs a GLOBAL sign-out, it would log
// them out of the tab they were actively using.
const ACTIVITY_CHANNEL = "hd-activity";

/**
 * Calls `onIdle` after `timeoutMs` of no user activity in ANY tab
 * (HIPAA §164.312(a)(2)(iii) automatic logoff). Any interaction resets the timer.
 *
 * This is a convenience, NOT the control. A closed tab cancels its timers, so a
 * browser-side timer alone leaves the session valid for the token's full
 * remaining life. The enforcing check is server-side, in
 * `core/auth.py::get_current_user`, which rejects a session whose `last_seen_at`
 * is older than IDLE_TIMEOUT_MINUTES.
 */
export function useIdleLogout(timeoutMs: number, onIdle: () => void) {
  const onIdleRef = useRef(onIdle);

  // Keep the latest callback without re-subscribing the activity listeners.
  useEffect(() => {
    onIdleRef.current = onIdle;
  });

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    // BroadcastChannel is unavailable in some older/embedded browsers; the hook
    // degrades to per-tab behaviour rather than throwing.
    const channel =
      typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(ACTIVITY_CHANNEL) : null;

    const restart = () => {
      clearTimeout(timer);
      timer = setTimeout(() => onIdleRef.current(), timeoutMs);
    };

    // Local activity: restart our own timer AND tell the other tabs.
    const onLocalActivity = () => {
      restart();
      channel?.postMessage("active");
    };

    // Remote activity: restart our timer only — re-broadcasting would loop.
    if (channel) {
      channel.onmessage = () => restart();
    }

    const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, onLocalActivity, { passive: true }));
    restart();

    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, onLocalActivity));
      channel?.close();
    };
  }, [timeoutMs]);
}
