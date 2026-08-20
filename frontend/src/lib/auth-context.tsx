"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import { api } from "@/lib/api";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  practice_id: string;
};

// login resolves to "ok" (session started) or an MFA challenge to answer next.
export type LoginResult =
  { status: "ok" } | { status: "mfa"; challenge: string; session: string };

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (email: string, session: string, code: string) => Promise<void>;
  startMfaSetup: (
    email: string,
    session: string,
  ) => Promise<{ secret: string; session: string }>;
  completeMfaSetup: (
    email: string,
    session: string,
    code: string,
  ) => Promise<void>;
  // NEW_PASSWORD_REQUIRED (temporary password): like login, may resolve to "ok" or
  // hand off to an MFA challenge.
  setNewPassword: (
    email: string,
    session: string,
    newPassword: string,
  ) => Promise<LoginResult>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// A presence flag (NOT the token) so Next middleware can gate navigation
// server-side, where it cannot read localStorage.
const AUTH_COOKIE = "hd_authed";

// Fallback lifetime when the server didn't tell us (matches Cognito's default
// access-token validity of one hour).
const DEFAULT_SESSION_SECONDS = 3600;

function setAuthedCookie(expiresIn: number = DEFAULT_SESSION_SECONDS) {
  // Secure over HTTPS (prod); omitted on http://localhost so dev auth-gating works.
  const secure = window.location.protocol === "https:" ? "; secure" : "";
  // Lifetime tracks the SESSION, not a fixed 30 days. When this outlived the
  // httpOnly session cookie, the presence flag kept claiming "logged in" for 30
  // days after a 1-hour session expired — so `/` and `/login` redirected to
  // `/dashboard`, which bounced back, leaving the marketing site unreachable to
  // a logged-out user until they cleared cookies.
  const maxAge = Math.max(1, Math.floor(expiresIn));
  document.cookie = `${AUTH_COOKIE}=1; path=/; max-age=${maxAge}; samesite=lax${secure}`;
}

function clearAuthedCookie() {
  document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const queryClient = useQueryClient();

  // On mount, if the presence flag says we're logged in, validate via /me (the
  // httpOnly session cookie is sent automatically). No JS-readable token exists.
  // State updates happen in promise callbacks, not synchronously — to satisfy
  // react-hooks/set-state-in-effect.
  useEffect(() => {
    let active = true;
    const authed = document.cookie
      .split("; ")
      .some((c) => c.startsWith(`${AUTH_COOKIE}=1`));
    const request: Promise<User | null> = authed
      ? api.get<User>("/api/auth/me").then((res) => res.data)
      : Promise.resolve(null);
    request
      .then((data) => {
        if (active) setUser(data);
      })
      .catch(() => {
        clearAuthedCookie();
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // Shared tail once a session is established (direct login or after MFA): the
  // server has already set the httpOnly cookie, so just set the presence flag,
  // wipe any previous session's cache, load the user, and go to the app.
  const completeAuth = useCallback(
    async (expiresIn?: number) => {
      setAuthedCookie(expiresIn);
      queryClient.clear();
      const me = await api.get<User>("/api/auth/me");
      setUser(me.data);
      // Admins land on the global overview; everyone else on their practice
      // dashboard. UX only — /admin data is gated by require_role on the API.
      router.replace(me.data.role === "admin" ? "/admin" : "/dashboard");
    },
    [router, queryClient],
  );

  // Shared tail for the two calls that can either finish login or return a challenge.
  const settle = useCallback(
    async (data: {
      mfa?: { challenge: string; session: string };
      expires_in?: number;
    }) => {
      if (data.mfa) {
        return {
          status: "mfa",
          challenge: data.mfa.challenge,
          session: data.mfa.session,
        } as const;
      }
      await completeAuth(data.expires_in);
      return { status: "ok" } as const;
    },
    [completeAuth],
  );

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const res = await api.post("/api/auth/login", { email, password });
      return settle(res.data);
    },
    [settle],
  );

  const setNewPassword = useCallback(
    async (
      email: string,
      session: string,
      newPassword: string,
    ): Promise<LoginResult> => {
      const res = await api.post("/api/auth/password/set", {
        email,
        session,
        new_password: newPassword,
      });
      return settle(res.data);
    },
    [settle],
  );

  const verifyMfa = useCallback(
    async (email: string, session: string, code: string) => {
      const res = await api.post("/api/auth/mfa/verify", {
        email,
        session,
        code,
      });
      await completeAuth(res.data.expires_in);
    },
    [completeAuth],
  );

  const startMfaSetup = useCallback(async (email: string, session: string) => {
    const res = await api.post("/api/auth/mfa/setup/start", { email, session });
    return res.data as { secret: string; session: string };
  }, []);

  const completeMfaSetup = useCallback(
    async (email: string, session: string, code: string) => {
      const res = await api.post("/api/auth/mfa/setup/complete", {
        email,
        session,
        code,
      });
      await completeAuth(res.data.expires_in);
    },
    [completeAuth],
  );

  const logout = useCallback(async () => {
    // Server clears the httpOnly cookie + Cognito global sign-out; best-effort so we
    // always sign out client-side even if it fails.
    try {
      await api.post("/api/auth/logout");
    } catch {
      // ignore — proceed with local sign-out
    }
    clearAuthedCookie();
    setUser(null);
    // Drop all cached queries so the next user never sees this session's PHI.
    queryClient.clear();
    router.replace("/login");
  }, [router, queryClient]);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        verifyMfa,
        startMfaSetup,
        completeMfaSetup,
        setNewPassword,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
