import { useEffect, useRef } from "react";

import { api } from "@/lib/api";

// Activity is broadcast across tabs so any one tab's interaction keeps the whole
// session alive. Without this, listeners bound to `window` only saw their own
// tab: a user working in tab B for 20 minutes would have tab A fire the idle
// handler — and because that handler performs a GLOBAL sign-out, it would log
// them out of the tab they were actively using.
const ACTIVITY_CHANNEL = "hd-activity";

// How often genuine interaction is reported to the server. The server's idle
// window is 15 minutes, so a minute of granularity is far finer than it needs,
// while keeping this to at most ~1 request/minute for an active user.
const HEARTBEAT_INTERVAL_MS = 60_000;

/**
 * Calls `onIdle` after `timeoutMs` of no user activity in ANY tab
 * (HIPAA §164.312(a)(2)(iii) automatic logoff), and reports real interaction to
 * the server so its own idle clock agrees with this one.
 *
 * WHY THE HEARTBEAT EXISTS. The server expires a session whose `last_seen_at` is
 * stale, but it can only see HTTP requests — and it deliberately does NOT count
 * the app's polling endpoints (`processing-ids`, `{id}/status`), because those
 * fire on a timer with nobody necessarily at the keyboard. Without this
 * heartbeat, someone reading a long appeal letter without clicking would be
 * signed out mid-sentence: the browser knows they are there, the server does not.
 *
 * So: mouse/key/scroll/touch keeps the session alive; a tab left open on an empty
 * desk sends nothing and expires on schedule. That is the distinction between
 * "the page is open" and "someone is working", and only the second should count.
 *
 * The browser timer below is still not the control — a closed tab cancels it.
 * The enforcing check is `core/auth.py::get_current_user`.
 */
export function useIdleLogout(timeoutMs: number, onIdle: () => void) {
  const onIdleRef = useRef(onIdle);

  // Keep the latest callback without re-subscribing the activity listeners.
  useEffect(() => {
    onIdleRef.current = onIdle;
  });

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let lastBeat = 0;
    let cancelled = false;

    // BroadcastChannel is unavailable in some older/embedded browsers; the hook
    // degrades to per-tab behaviour rather than throwing.
    const channel =
      typeof BroadcastChannel !== "undefined"
        ? new BroadcastChannel(ACTIVITY_CHANNEL)
        : null;

    const restart = () => {
      clearTimeout(timer);
      timer = setTimeout(() => onIdleRef.current(), timeoutMs);
    };

    const beat = () => {
      const now = Date.now();
      if (now - lastBeat < HEARTBEAT_INTERVAL_MS) return;
      lastBeat = now;
      // Fire-and-forget. A failed heartbeat must never surface to the user or
      // throw: if the session really is gone, the next real request returns 401
      // and the normal sign-out path handles it.
      void api.post("/api/auth/heartbeat").catch(() => {});
    };

    // Local activity: restart our own timer, tell the other tabs, and let the
    // server know a human is here.
    const onLocalActivity = () => {
      if (cancelled) return;
      restart();
      beat();
      channel?.postMessage("active");
    };

    // Remote activity: restart our timer only. Re-broadcasting would loop, and
    // the tab that saw the real interaction has already sent the heartbeat.
    if (channel) {
      channel.onmessage = () => restart();
    }

    const events = [
      "mousemove",
      "mousedown",
      "keydown",
      "scroll",
      "touchstart",
    ];
    events.forEach((e) =>
      window.addEventListener(e, onLocalActivity, { passive: true }),
    );
    restart();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, onLocalActivity));
      channel?.close();
    };
  }, [timeoutMs]);
}
