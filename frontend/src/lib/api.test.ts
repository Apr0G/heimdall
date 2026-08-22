/**
 * The 401 interceptor on the REAL api instance (other suites mock @/lib/api
 * wholesale, which is how MED-18 went unnoticed): a 401 from a credential-
 * checking endpoint must NOT clear the session or redirect; any other 401 must.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, isCredentialCheck } from "./api";

function fail401(url: string) {
  const onFulfilled = (
    api.interceptors.response as unknown as {
      handlers: Array<{ rejected: (e: unknown) => Promise<never> }>;
    }
  ).handlers[0];
  return onFulfilled.rejected({ response: { status: 401 }, config: { url } });
}

describe("api 401 interceptor", () => {
  beforeEach(() => {
    document.cookie = "hd_authed=1; path=/";
    vi.stubGlobal("location", { pathname: "/settings", assign: vi.fn() });
  });

  it("treats credential-check endpoints as bad input, not a dead session", async () => {
    for (const url of [
      "/api/auth/login",
      "/api/auth/password/change",
      "/api/auth/password/reset",
      "/api/auth/mfa/recover/start",
      "/api/auth/mfa/verify",
    ]) {
      await expect(fail401(url)).rejects.toBeTruthy();
      expect(document.cookie).toContain("hd_authed=1");
      expect(
        (window.location as unknown as { assign: ReturnType<typeof vi.fn> })
          .assign,
      ).not.toHaveBeenCalled();
    }
  });

  it("bounces to login on a 401 from any other endpoint", async () => {
    await expect(fail401("/api/cases")).rejects.toBeTruthy();
    expect(document.cookie).not.toContain("hd_authed=1");
    expect(
      (window.location as unknown as { assign: ReturnType<typeof vi.fn> })
        .assign,
    ).toHaveBeenCalledWith("/login");
  });

  it("isCredentialCheck matches by path", () => {
    expect(
      isCredentialCheck("https://api.example.com/api/auth/password/set"),
    ).toBe(true);
    expect(isCredentialCheck("/api/auth/me")).toBe(false);
  });
});
