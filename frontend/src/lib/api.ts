import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Auth is an httpOnly cookie set by the API on a same-site subdomain. withCredentials
// sends it on every request; JavaScript never sees the token, so an XSS can't steal it.
export const api = axios.create({ baseURL: API_BASE, withCredentials: true });

// On any 401 (expired/invalidated session), drop the presence flag and bounce to
// login instead of leaving a half-dead session. Skip the login call itself, where a
// 401 is just bad credentials.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    if (status === 401 && !url.includes("/api/auth/login") && typeof window !== "undefined") {
      document.cookie = "hd_authed=; path=/; max-age=0; samesite=lax";
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  },
);
