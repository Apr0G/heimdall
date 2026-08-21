import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { httpError } from "@/test/axios-error";

const { api } = vi.hoisted(() => ({ api: { post: vi.fn() } }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      email: "doctor@heimdall.test",
      full_name: "Dr. Jane Doe",
      role: "office_manager",
      practice_id: "p1",
    },
  }),
}));

import SettingsPage from "./page";

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

beforeEach(() => vi.clearAllMocks());

describe("settings page", () => {
  it("shows the profile with a humanised role", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Dr. Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("doctor@heimdall.test")).toBeInTheDocument();
    expect(screen.getByText("Office manager")).toBeInTheDocument();
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
});
