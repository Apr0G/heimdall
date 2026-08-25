import axios from "axios";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Auth is an httpOnly cookie set by the API on a same-site subdomain. withCredentials
// sends it on every request; JavaScript never sees the token, so an XSS can't steal it.
export const api = axios.create({ baseURL: API_BASE, withCredentials: true });

// Endpoints where a 401 means "the credential you just typed is wrong", not
// "your session is dead". For these the form shows the message; for everything
// else a 401 drops the presence flag and bounces to login rather than leaving a
// half-dead session. Keep in sync with the routes in backend/app/api/auth.py.
export const CREDENTIAL_CHECK_PATHS = [
  "/api/auth/login",
  "/api/auth/password/set",
  "/api/auth/password/reset",
  "/api/auth/password/change",
  "/api/auth/mfa/verify",
  "/api/auth/mfa/setup/complete",
  "/api/auth/mfa/recover/start",
  "/api/auth/mfa/recover/complete",
];

export function isCredentialCheck(url: string): boolean {
  return CREDENTIAL_CHECK_PATHS.some((p) => url.includes(p));
}

// Public marketing routes (mirrors proxy.ts PUBLIC_PATHS). A stale hd_authed flag
// there must NOT bounce a visitor to /login — the auth-context's own /me catch
// clears the cookie and stays put. The bounce is only for gated app routes.
const PUBLIC_PATHS = [
  "/",
  "/contact",
  "/terms",
  "/privacy",
  "/login",
  "/get-started",
];

function onPublicRoute(): boolean {
  const p = window.location.pathname;
  return PUBLIC_PATHS.includes(p);
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    if (
      status === 401 &&
      !isCredentialCheck(url) &&
      typeof window !== "undefined" &&
      !onPublicRoute()
    ) {
      document.cookie = "hd_authed=; path=/; max-age=0; samesite=lax";
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  },
);
