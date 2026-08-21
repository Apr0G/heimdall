import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { httpError } from "@/test/axios-error";

const { api, auth, toast } = vi.hoisted(() => ({
  api: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
  auth: {
    user: {
      id: "u1",
      email: "doctor@heimdall.test",
      full_name: "Dr. Jane Doe",
      role: "office_manager",
      practice_id: "p1",
    },
    logout: vi.fn(),
  },
  toast: { message: vi.fn() },
}));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => auth,
  homePath: (role: string) => (role === "admin" ? "/admin" : "/dashboard"),
}));

import SettingsPage from "./page";

function render(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const STRONG = "Correct-Horse-9!";

async function fill(current: string, next = STRONG, confirm = next) {
  const user = userEvent.setup();
  render(<SettingsPage />);
  await user.type(screen.getByLabelText("Current password"), current);
  await user.type(screen.getByLabelText("New password"), next);
  await user.type(screen.getByLabelText("Confirm new password"), confirm);
  await user.click(screen.getByRole("button", { name: "Update password" }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.user.role = "office_manager";
  api.get.mockResolvedValue({ data: null }); // no pending deactivation request
});

describe("settings page", () => {
  it("shows the profile with a humanised role and a role-aware back link", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Dr. Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("doctor@heimdall.test")).toBeInTheDocument();
    expect(screen.getByText("Office manager")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Appeals/ })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("sends admins back to the admin area", () => {
    auth.user.role = "admin";
    render(<SettingsPage />);
    expect(screen.getByRole("link", { name: /Admin/ })).toHaveAttribute(
      "href",
      "/admin",
    );
  });

  it("sends snake_case fields, confirms, and clears the form", async () => {
    api.post.mockResolvedValue({ data: null });
    await fill("Old-Horse-1!");
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/auth/password/change", {
        current_password: "Old-Horse-1!",
        new_password: STRONG,
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Password updated.",
    );
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("offers forgot-password: emails a code, resets, then signs out", async () => {
    api.post.mockResolvedValue({ data: null });
    const user = userEvent.setup();
    render(<SettingsPage />);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await user.click(
      await screen.findByRole("button", { name: "Email me a code" }),
    );
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/auth/password/forgot", {
        email: "doctor@heimdall.test",
      }),
    );
    await user.type(await screen.findByLabelText("Code"), "246810");
    await user.type(document.getElementById("reset-newPassword")!, STRONG);
    await user.type(document.getElementById("reset-confirm")!, STRONG);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenLastCalledWith("/api/auth/password/reset", {
        email: "doctor@heimdall.test",
        code: "246810",
        new_password: STRONG,
      }),
    );
    await waitFor(() => expect(auth.logout).toHaveBeenCalled());
    expect(toast.message).toHaveBeenCalledWith(
      expect.stringMatching(/Password updated/),
    );
  });

  it("refuses to reuse the current password without a round-trip", async () => {
    await fill(STRONG, STRONG);
    expect(
      await screen.findByText(/haven't used here before/),
    ).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("maps 401 to a current-password message and 400 to the server reason", async () => {
    api.post.mockRejectedValueOnce(httpError(401));
    const user = await fill("Wrong-Horse-1!");
    expect(
      await screen.findByText(/current password didn't match/),
    ).toBeInTheDocument();

    api.post.mockRejectedValueOnce(
      httpError(400, "Password doesn't meet the requirements: too short"),
    );
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByText(/too short/)).toBeInTheDocument();
  });

  it("resets the authenticator: password -> emailed code -> signed out", async () => {
    api.post.mockResolvedValue({ data: null });
    const user = userEvent.setup();
    render(<SettingsPage />);
    await user.click(
      screen.getByRole("button", { name: "Reset authenticator" }),
    );
    expect(screen.getByLabelText("Email")).toHaveValue("doctor@heimdall.test");
    expect(screen.getByLabelText("Email")).toHaveAttribute("readonly");
    await user.type(screen.getByLabelText("Password"), "Old-Horse-1!");
    await user.click(screen.getByRole("button", { name: "Email me a code" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/auth/mfa/recover/start", {
        email: "doctor@heimdall.test",
        password: "Old-Horse-1!",
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
          email: "doctor@heimdall.test",
          password: "Old-Horse-1!",
          code: "135790",
        },
      ),
    );
    await waitFor(() => expect(auth.logout).toHaveBeenCalled());
    expect(toast.message).toHaveBeenCalledWith(
      expect.stringMatching(/Authenticator reset/),
    );
  });

  it("requests deactivation with a reason, then shows the pending state", async () => {
    api.post.mockResolvedValue({ data: { id: "r1", status: "pending" } });
    const user = userEvent.setup();
    render(<SettingsPage />);
    await user.click(
      await screen.findByRole("button", { name: "Request deactivation" }),
    );
    await user.type(screen.getByLabelText(/Reason/), "Leaving the practice");
    api.get.mockResolvedValue({
      data: {
        id: "r1",
        status: "pending",
        reason: "Leaving the practice",
        created_at: "2026-08-21T00:00:00Z",
      },
    });
    await user.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/auth/deactivation-request", {
        reason: "Leaving the practice",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(/Request sent/);
    expect(
      screen.getByRole("button", { name: "Cancel request" }),
    ).toBeInTheDocument();
  });

  it("cancels a pending deactivation request", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        id: "r1",
        status: "pending",
        reason: null,
        created_at: "2026-08-21T00:00:00Z",
      },
    });
    api.delete.mockResolvedValue({ data: null });
    const user = userEvent.setup();
    render(<SettingsPage />);
    await user.click(
      await screen.findByRole("button", { name: "Cancel request" }),
    );
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/api/auth/deactivation-request"),
    );
    expect(
      await screen.findByRole("button", { name: "Request deactivation" }),
    ).toBeInTheDocument();
  });
});
