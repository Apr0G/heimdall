import { useEffect, useRef } from "react";

/**
 * Calls `onIdle` after `timeoutMs` of no user activity (HIPAA §164.312(a)(2)(iii)
 * automatic logoff). Any interaction resets the timer.
 */
export function useIdleLogout(timeoutMs: number, onIdle: () => void) {
  const onIdleRef = useRef(onIdle);

  // Keep the latest callback without re-subscribing the activity listeners.
  useEffect(() => {
    onIdleRef.current = onIdle;
  });

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => onIdleRef.current(), timeoutMs);
    };
    const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [timeoutMs]);
}
