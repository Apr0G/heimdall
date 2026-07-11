import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// MVP shortcut: the access token lives in localStorage (XSS-exposed). Revisit
// with an httpOnly cookie set via a Next route handler before production.
export const TOKEN_KEY = "heimdall_access_token";

// 30s timeout so a hung backend surfaces an error instead of a mutation that
// spins forever. (Long work — the pipeline — runs server-side, not in a request.)
export const api = axios.create({ baseURL: API_BASE, timeout: 30_000 });

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// On any 401 (expired/invalidated token), drop the local session and bounce to
// login instead of leaving a half-dead session that toasts "session expired"
// forever. Skip the login call itself, where 401 is just a bad-credentials error.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    if (status === 401 && !url.includes("/api/auth/login") && typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_KEY);
      // Clear the presence cookie so Next middleware doesn't think we're authed.
      document.cookie = "hd_authed=; path=/; max-age=0; samesite=lax";
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  },
);
