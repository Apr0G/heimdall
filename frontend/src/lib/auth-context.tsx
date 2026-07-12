"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, TOKEN_KEY } from "@/lib/api";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  practice_id: string;
};

// login resolves to "ok" (session started) or an MFA challenge to answer next.
export type LoginResult = { status: "ok" } | { status: "mfa"; challenge: string; session: string };

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (email: string, session: string, code: string) => Promise<void>;
  startMfaSetup: (email: string, session: string) => Promise<{ secret: string; session: string }>;
  completeMfaSetup: (email: string, session: string, code: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// A presence flag (NOT the token) so Next middleware can gate navigation
// server-side, where it cannot read localStorage.
const AUTH_COOKIE = "hd_authed";

function setAuthedCookie() {
  // Secure over HTTPS (prod); omitted on http://localhost so dev auth-gating works.
  const secure = window.location.protocol === "https:" ? "; secure" : "";
  document.cookie = `${AUTH_COOKIE}=1; path=/; max-age=2592000; samesite=lax${secure}`;
}

function clearAuthedCookie() {
  document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const queryClient = useQueryClient();

  // On mount, hydrate the user from a stored token (and validate it via /me).
  // All state updates happen in promise callbacks — never synchronously in the
  // effect body — to satisfy react-hooks/set-state-in-effect.
  useEffect(() => {
    let active = true;
    const token = window.localStorage.getItem(TOKEN_KEY);
    const request: Promise<User | null> = token
      ? api.get<User>("/api/auth/me").then((res) => res.data)
      : Promise.resolve(null);
    request
      .then((data) => {
        if (active) setUser(data);
      })
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
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

  // Shared tail once tokens are obtained (direct login or after MFA): store the
  // token, wipe any previous session's cache, load the user, and go to the app.
  const completeAuth = useCallback(
    async (token: string) => {
      window.localStorage.setItem(TOKEN_KEY, token);
      setAuthedCookie();
      queryClient.clear();
      const me = await api.get<User>("/api/auth/me");
      setUser(me.data);
      router.replace("/dashboard");
    },
    [router, queryClient],
  );

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const res = await api.post("/api/auth/login", { email, password });
      if (res.data.mfa) {
        return { status: "mfa", challenge: res.data.mfa.challenge, session: res.data.mfa.session };
      }
      await completeAuth(res.data.access_token);
      return { status: "ok" };
    },
    [completeAuth],
  );

  const verifyMfa = useCallback(
    async (email: string, session: string, code: string) => {
      const res = await api.post("/api/auth/mfa/verify", { email, session, code });
      await completeAuth(res.data.access_token);
    },
    [completeAuth],
  );

  const startMfaSetup = useCallback(async (email: string, session: string) => {
    const res = await api.post("/api/auth/mfa/setup/start", { email, session });
    return res.data as { secret: string; session: string };
  }, []);

  const completeMfaSetup = useCallback(
    async (email: string, session: string, code: string) => {
      const res = await api.post("/api/auth/mfa/setup/complete", { email, session, code });
      await completeAuth(res.data.access_token);
    },
    [completeAuth],
  );

  const logout = useCallback(async () => {
    // Best-effort server sign-out (Cognito global sign-out + audit); clear locally
    // regardless so the user is always signed out client-side.
    try {
      await api.post("/api/auth/logout");
    } catch {
      // ignore — proceed with local sign-out
    }
    window.localStorage.removeItem(TOKEN_KEY);
    clearAuthedCookie();
    setUser(null);
    // Drop all cached queries so the next user never sees this session's PHI.
    queryClient.clear();
    router.replace("/login");
  }, [router, queryClient]);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, verifyMfa, startMfaSetup, completeMfaSetup, logout }}
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
