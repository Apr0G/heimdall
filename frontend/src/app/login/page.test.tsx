/**
 * The login page is a six-step state machine (password → new-password / TOTP
 * code / TOTP enrolment, plus forgot → reset). These tests drive it through the
 * UI with the auth context and API client mocked, pinning the transitions, the
 * payloads sent, and what the user is told on each failure.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { httpError } from "@/test/axios-error";

const { auth, api } = vi.hoisted(() => ({
  auth: {
    login: vi.fn(),
    verifyMfa: vi.fn(),
    startMfaSetup: vi.fn(),
    completeMfaSetup: vi.fn(),
    setNewPassword: vi.fn(),
  },
  api: { post: vi.fn() },
}));

vi.mock("@/lib/auth-context", () => ({ useAuth: () => auth }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@/components/marketing-header", () => ({
  MarketingHeader: () => null,
}));

import LoginPage from "./page";

const EMAIL = "doctor@heimdall.test";
const STRONG = "Correct-Horse-9!";

async function signIn(password = "hunter2-hunter2") {
  const user = userEvent.setup();
  render(<LoginPage />);
  await user.type(screen.getByLabelText("Email"), EMAIL);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("password step", () => {
  it("shows a friendly message on wrong credentials", async () => {
    auth.login.mockRejectedValue(httpError(401));
    await signIn();
    expect(
      await screen.findByText(/doesn't match our records/),
    ).toBeInTheDocument();
    expect(auth.login).toHaveBeenCalledWith(EMAIL, "hunter2-hunter2");
  });

  it("shows a generic message on an outage, never the raw error", async () => {
    auth.login.mockRejectedValue(
      httpError(502, "Authentication service is unavailable"),
    );
    await signIn();
    expect(await screen.findByText(/Something went wrong/)).toBeInTheDocument();
    expect(screen.queryByText(/unavailable/)).not.toBeInTheDocument();
  });

  it("hands a SOFTWARE_TOKEN_MFA challenge to the code step", async () => {
    auth.login.mockResolvedValue({
      status: "mfa",
      challenge: "SOFTWARE_TOKEN_MFA",
      session: "s1",
    });
    auth.verifyMfa.mockResolvedValue(undefined);
    const user = await signIn();
    expect(
      await screen.findByText("Two-factor authentication"),
    ).toBeInTheDocument();
    const code = screen.getByLabelText("6-digit code");
    await user.type(code, "12ab3456"); // non-digits dropped, capped at 6
    expect(code).toHaveValue("123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() =>
      expect(auth.verifyMfa).toHaveBeenCalledWith(EMAIL, "s1", "123456"),
    );
  });

  it("starts enrolment on MFA_SETUP and shows the manual key", async () => {
    auth.login.mockResolvedValue({
      status: "mfa",
      challenge: "MFA_SETUP",
      session: "s1",
    });
    auth.startMfaSetup.mockResolvedValue({
      secret: "BASE32SECRET",
      session: "s2",
    });
    auth.completeMfaSetup.mockResolvedValue(undefined);
    const user = await signIn();
    expect(
      await screen.findByText("Set up two-factor authentication"),
    ).toBeInTheDocument();
    expect(auth.startMfaSetup).toHaveBeenCalledWith(EMAIL, "s1");
    expect(screen.getByText("BASE32SECRET")).toBeInTheDocument();
    await user.type(screen.getByLabelText("6-digit code"), "654321");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    // The session carried forward is the one associate_software_token returned.
    await waitFor(() =>
      expect(auth.completeMfaSetup).toHaveBeenCalledWith(EMAIL, "s2", "654321"),
    );
  });

  it("tells the user when a TOTP code is rejected", async () => {
    auth.login.mockResolvedValue({
      status: "mfa",
      challenge: "SOFTWARE_TOKEN_MFA",
      session: "s1",
    });
    auth.verifyMfa.mockRejectedValue(httpError(401));
    const user = await signIn();
    await user.type(await screen.findByLabelText("6-digit code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(
      await screen.findByText(/didn't match, or it expired/),
    ).toBeInTheDocument();
  });
});

describe("temporary password (NEW_PASSWORD_REQUIRED)", () => {
  beforeEach(() => {
    auth.login.mockResolvedValue({
      status: "mfa",
      challenge: "NEW_PASSWORD_REQUIRED",
      session: "np1",
    });
  });

  it("validates the pair client-side before calling the API", async () => {
    const user = await signIn("Temp-Pass-123!");
    expect(await screen.findByText("Choose your password")).toBeInTheDocument();
    await user.type(screen.getByLabelText("New password"), "weak");
    await user.type(screen.getByLabelText("Confirm new password"), "weaker");
    await user.click(screen.getByRole("button", { name: /Set password/ }));
    expect(
      await screen.findByText(/doesn't meet the rules/),
    ).toBeInTheDocument();
    expect(screen.getByText("Passwords don't match")).toBeInTheDocument();
    expect(auth.setNewPassword).not.toHaveBeenCalled();
  });

  it("ticks the rule checklist as the user types", async () => {
    const user = await signIn("Temp-Pass-123!");
    const field = await screen.findByLabelText("New password");
    const rule = () =>
      screen.getByText("At least 12 characters").closest("li")!;
    expect(rule()).not.toHaveClass("text-foreground");
    await user.type(field, STRONG);
    expect(rule()).toHaveClass("text-foreground");
  });

  it("chains into MFA enrolment after the password is set", async () => {
    auth.setNewPassword.mockResolvedValue({
      status: "mfa",
      challenge: "MFA_SETUP",
      session: "np2",
    });
    auth.startMfaSetup.mockResolvedValue({ secret: "K", session: "np3" });
    const user = await signIn("Temp-Pass-123!");
    await user.type(await screen.findByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm new password"), STRONG);
    await user.click(screen.getByRole("button", { name: /Set password/ }));
    await waitFor(() =>
      expect(auth.setNewPassword).toHaveBeenCalledWith(EMAIL, "np1", STRONG),
    );
    expect(
      await screen.findByText("Set up two-factor authentication"),
    ).toBeInTheDocument();
    expect(auth.startMfaSetup).toHaveBeenCalledWith(EMAIL, "np2");
  });

  it("relays the server's policy reason on 400 and an expiry hint on 401", async () => {
    auth.setNewPassword.mockRejectedValueOnce(
      httpError(
        400,
        "Password doesn't meet the requirements: Password must have symbol characters",
      ),
    );
    const user = await signIn("Temp-Pass-123!");
    await user.type(await screen.findByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm new password"), STRONG);
    await user.click(screen.getByRole("button", { name: /Set password/ }));
    expect(
      await screen.findByText(/must have symbol characters/),
    ).toBeInTheDocument();

    auth.setNewPassword.mockRejectedValueOnce(httpError(401));
    await user.click(screen.getByRole("button", { name: /Set password/ }));
    expect(await screen.findByText(/session expired/)).toBeInTheDocument();
  });
});

describe("lost authenticator", () => {
  it("is offered on the code step and resets via password + emailed code", async () => {
    auth.login.mockResolvedValue({
      status: "mfa",
      challenge: "SOFTWARE_TOKEN_MFA",
      session: "s1",
    });
    api.post.mockResolvedValue({ data: null });
    const user = await signIn();
    await user.click(
      await screen.findByRole("button", { name: "Lost your authenticator?" }),
    );
    expect(
      await screen.findByText("Reset your authenticator"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue(EMAIL); // carried from sign-in
    await user.type(screen.getByLabelText("Password"), "hunter2-hunter2");
    await user.click(screen.getByRole("button", { name: "Email me a code" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/auth/mfa/recover/start", {
        email: EMAIL,
        password: "hunter2-hunter2",
      }),
    );
    await user.type(await screen.findByLabelText("Code"), "135790");
    await user.click(
      screen.getByRole("button", { name: "Reset authenticator" }),
    );
    await waitFor(() =>
      expect(api.post).toHaveBeenLastCalledWith(
        "/api/auth/mfa/recover/complete",
        {
          email: EMAIL,
          password: "hunter2-hunter2",
          code: "135790",
        },
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Authenticator reset/,
    );
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("is NOT offered on the initial sign-in form", () => {
    render(<LoginPage />);
    expect(screen.queryByText(/authenticator/i)).toBeNull();
  });

  it("is reachable from the forgot-password page and explains a wrong password", async () => {
    api.post.mockRejectedValue(httpError(401));
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(screen.getByRole("button", { name: "Forgot password?" }));
    await user.click(await screen.findByRole("button", { name: "Reset it" }));
    expect(
      await screen.findByText("Reset your authenticator"),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.type(screen.getByLabelText("Password"), "wrong-wrong-wrong");
    await user.click(screen.getByRole("button", { name: "Email me a code" }));
    expect(
      await screen.findByText(/doesn't match our records/),
    ).toBeInTheDocument();
  });

  it("explains when there is no authenticator to reset", async () => {
    api.post.mockRejectedValue(
      httpError(
        400,
        "There's no authenticator on this account yet - just sign in to set one up.",
      ),
    );
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(screen.getByRole("button", { name: "Forgot password?" }));
    await user.click(await screen.findByRole("button", { name: "Reset it" }));
    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.type(screen.getByLabelText("Password"), "hunter2-hunter2");
    await user.click(screen.getByRole("button", { name: "Email me a code" }));
    expect(
      await screen.findByText(/no authenticator on this account/),
    ).toBeInTheDocument();
  });
});

describe("forgot password", () => {
  async function openForgot(prefill = true) {
    const user = userEvent.setup();
    render(<LoginPage />);
    if (prefill) await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.click(screen.getByRole("button", { name: "Forgot password?" }));
    expect(await screen.findByText("Reset your password")).toBeInTheDocument();
    return user;
  }

  it("carries the typed email into the reset request", async () => {
    api.post.mockResolvedValue({ data: null });
    const user = await openForgot();
    expect(screen.getByLabelText("Email")).toHaveValue(EMAIL);
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/auth/password/forgot", {
        email: EMAIL,
      }),
    );
    expect(await screen.findByText("Check your email")).toBeInTheDocument();
    expect(screen.getByText(EMAIL)).toBeInTheDocument();
  });

  it("completes a reset and returns to sign-in with a confirmation", async () => {
    api.post.mockResolvedValue({ data: null });
    const user = await openForgot();
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(await screen.findByLabelText("Code"), "246810");
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm new password"), STRONG);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenLastCalledWith("/api/auth/password/reset", {
        email: EMAIL,
        code: "246810",
        new_password: STRONG,
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Password updated/,
    );
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("rejects a non-6-digit code before calling the API", async () => {
    api.post.mockResolvedValue({ data: null });
    const user = await openForgot();
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(await screen.findByLabelText("Code"), "12");
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm new password"), STRONG);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(
      await screen.findByText("Enter the 6-digit code"),
    ).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1); // only the forgot call
  });

  it("explains a wrong code and offers a new one", async () => {
    api.post
      .mockResolvedValueOnce({ data: null })
      .mockRejectedValueOnce(httpError(401));
    const user = await openForgot();
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(await screen.findByLabelText("Code"), "000000");
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm new password"), STRONG);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(
      await screen.findByText(/didn't match, or it expired/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send a new code" }));
    expect(await screen.findByText("Reset your password")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue(EMAIL);
  });

  it("surfaces throttling on the forgot step and allows going back", async () => {
    api.post.mockRejectedValue(httpError(429));
    const user = await openForgot(false);
    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.click(screen.getByRole("button", { name: "Send code" }));
    expect(await screen.findByText(/Too many attempts/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
  });
});
