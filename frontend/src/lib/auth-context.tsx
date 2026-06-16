"use client";

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

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// A presence flag (NOT the token) so Next middleware can gate navigation
// server-side, where it cannot read localStorage.
const AUTH_COOKIE = "hd_authed";

function setAuthedCookie() {
  document.cookie = `${AUTH_COOKIE}=1; path=/; max-age=2592000; samesite=lax`;
}

function clearAuthedCookie() {
  document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

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

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.post("/api/auth/login", { email, password });
      window.localStorage.setItem(TOKEN_KEY, res.data.access_token);
      setAuthedCookie();
      const me = await api.get<User>("/api/auth/me");
      setUser(me.data);
      router.replace("/");
    },
    [router],
  );

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    clearAuthedCookie();
    setUser(null);
    router.replace("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
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
