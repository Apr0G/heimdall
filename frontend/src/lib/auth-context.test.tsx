/**
 * The auth context owns the only place the frontend decides "logged in": the
 * presence cookie, the /me load, and the role-aware redirect. These tests pin
 * that a finished login lands admins on /admin and everyone else on /dashboard,
 * and that a challenge is passed through untouched without starting a session.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { api, router } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  router: { replace: vi.fn(), push: vi.fn() },
}));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { AuthProvider, useAuth } from "./auth-context";

function setup() {
  const qc = new QueryClient();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useAuth(), { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  document.cookie = "hd_authed=; path=/; max-age=0";
  api.get.mockResolvedValue({ data: null });
});

describe("auth context", () => {
  it("does not call /me without the presence cookie", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.get).not.toHaveBeenCalled();
    expect(result.current.user).toBeNull();
  });

  it("sends doctors to the dashboard after login", async () => {
    api.post.mockResolvedValue({ data: { expires_in: 3600 } });
    api.get.mockResolvedValue({
      data: { id: "u", email: "d@x", role: "doctor", practice_id: "p" },
    });
    const { result } = setup();
    await waitFor(() => expect(result.current.loading).toBe(false));
    let out;
    await act(async () => {
      out = await result.current.login("d@x", "pw");
    });
    expect(out).toEqual({ status: "ok" });
    expect(router.replace).toHaveBeenCalledWith("/dashboard");
    expect(result.current.user?.role).toBe("doctor");
    expect(document.cookie).toMatch(/hd_authed=1/);
  });

  it("sends admins to the admin overview after login", async () => {
    api.post.mockResolvedValue({ data: { expires_in: 3600 } });
    api.get.mockResolvedValue({
      data: { id: "u", email: "a@x", role: "admin", practice_id: "p" },
    });
    const { result } = setup();
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.login("a@x", "pw");
    });
    expect(router.replace).toHaveBeenCalledWith("/admin");
  });

  it("passes a challenge through without starting a session", async () => {
    api.post.mockResolvedValue({
      data: { mfa: { challenge: "SOFTWARE_TOKEN_MFA", session: "s1" } },
    });
    const { result } = setup();
    await waitFor(() => expect(result.current.loading).toBe(false));
    let out;
    await act(async () => {
      out = await result.current.login("d@x", "pw");
    });
    expect(out).toEqual({
      status: "mfa",
      challenge: "SOFTWARE_TOKEN_MFA",
      session: "s1",
    });
    expect(router.replace).not.toHaveBeenCalled();
    expect(document.cookie).not.toMatch(/hd_authed=1/);
  });

  it("setNewPassword posts snake_case and settles like login", async () => {
    api.post.mockResolvedValue({
      data: { mfa: { challenge: "MFA_SETUP", session: "s2" } },
    });
    const { result } = setup();
    await waitFor(() => expect(result.current.loading).toBe(false));
    let out;
    await act(async () => {
      out = await result.current.setNewPassword(
        "d@x",
        "s1",
        "Correct-Horse-9!",
      );
    });
    expect(api.post).toHaveBeenCalledWith("/api/auth/password/set", {
      email: "d@x",
      session: "s1",
      new_password: "Correct-Horse-9!",
    });
    expect(out).toEqual({
      status: "mfa",
      challenge: "MFA_SETUP",
      session: "s2",
    });
  });
});
