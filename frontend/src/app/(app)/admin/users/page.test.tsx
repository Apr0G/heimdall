import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { httpError } from "@/test/axios-error";

const { adminApi, me } = vi.hoisted(() => ({
  adminApi: {
    fetchAdminUsers: vi.fn(),
    inviteUser: vi.fn(),
    resendInvite: vi.fn(),
    setUserActive: vi.fn(),
    fetchDeactivationRequests: vi.fn(),
    resolveDeactivationRequest: vi.fn(),
  },
  me: {
    id: "me",
    email: "admin@heimdall.test",
    role: "admin",
    practice_id: "p0",
  },
}));
vi.mock("@/lib/admin", () => adminApi);
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: me, loading: false }),
}));

import AdminUsersPage from "./page";

const PRACTICES = [
  { id: "p0", name: "Heimdall Internal" },
  { id: "p1", name: "Sunrise Family Medicine" },
];
const USERS = [
  {
    id: "me",
    email: "admin@heimdall.test",
    full_name: "Faig",
    role: "admin",
    practice_id: "p0",
    practice_name: "Heimdall Internal",
    is_active: true,
    last_login_at: "2026-08-20T10:00:00Z",
    created_at: "2026-07-01T00:00:00Z",
    invite_pending: false,
  },
  {
    id: "u-pending",
    email: "new@sunrise.test",
    full_name: null,
    role: "doctor",
    practice_id: "p1",
    practice_name: "Sunrise Family Medicine",
    is_active: true,
    last_login_at: null,
    created_at: "2026-08-20T00:00:00Z",
    invite_pending: true,
  },
  {
    id: "u-off",
    email: "former@sunrise.test",
    full_name: "Former Staff",
    role: "office_manager",
    practice_id: "p1",
    practice_name: "Sunrise Family Medicine",
    is_active: false,
    last_login_at: "2026-08-01T00:00:00Z",
    created_at: "2026-07-10T00:00:00Z",
    invite_pending: false,
  },
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AdminUsersPage />
    </QueryClientProvider>,
  );
}

const row = async (email: string) =>
  within(await screen.findByTestId(`user-row-${email}`));

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.fetchAdminUsers.mockResolvedValue({
    users: USERS,
    practices: PRACTICES,
  });
  adminApi.fetchDeactivationRequests.mockResolvedValue([]);
});

describe("admin users page", () => {
  it("lists users with status badges and hides self-deactivation", async () => {
    renderPage();
    const admin = await row("admin@heimdall.test");
    expect(admin.getByText("Active")).toBeInTheDocument();
    expect(admin.getByText(/\(you\)/)).toBeInTheDocument();
    expect(admin.queryByRole("button", { name: /Deactivate/ })).toBeNull();
    const pending = await row("new@sunrise.test");
    expect(pending.getByText("Invite pending")).toBeInTheDocument();
    expect(
      pending.getByRole("button", { name: "Resend invite" }),
    ).toBeInTheDocument();
    const off = await row("former@sunrise.test");
    expect(off.getByText("Deactivated")).toBeInTheDocument();
    expect(off.getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
    expect(
      screen.getAllByText("Sunrise Family Medicine", { selector: "td" }),
    ).toHaveLength(2);
  });

  it("invites into an existing practice with the right payload", async () => {
    adminApi.inviteUser.mockResolvedValue({
      user: { ...USERS[1], email: "dr@sunrise.test" },
      created_user: true,
      created_practice: false,
      invite_resent: false,
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(
      await screen.findByRole("button", { name: "Invite user" }),
    );
    await user.type(screen.getByLabelText("Email"), "dr@sunrise.test");
    await user.type(screen.getByLabelText(/Full name/), "  Dr. Sun  ");
    await user.selectOptions(screen.getByLabelText("Role"), "office_manager");
    await user.selectOptions(screen.getByLabelText("Practice"), "p1");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    await waitFor(() =>
      expect(adminApi.inviteUser).toHaveBeenCalledWith({
        email: "dr@sunrise.test",
        role: "office_manager",
        full_name: "Dr. Sun",
        practice_id: "p1",
        practice_name: null,
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Invitation sent to dr@sunrise.test/,
    );
    expect(adminApi.fetchAdminUsers).toHaveBeenCalledTimes(2); // refetched after invite
  });

  it("requires a name when creating a new practice, then sends practice_name", async () => {
    adminApi.inviteUser.mockResolvedValue({
      user: USERS[1],
      created_user: true,
      created_practice: true,
      invite_resent: false,
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(
      await screen.findByRole("button", { name: "Invite user" }),
    );
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.selectOptions(screen.getByLabelText("Practice"), "__new__");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(
      await screen.findByText("Name the new practice"),
    ).toBeInTheDocument();
    expect(adminApi.inviteUser).not.toHaveBeenCalled();
    await user.type(
      screen.getByLabelText("New practice name"),
      "Lakeside Clinic",
    );
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    await waitFor(() =>
      expect(adminApi.inviteUser).toHaveBeenCalledWith(
        expect.objectContaining({
          practice_id: null,
          practice_name: "Lakeside Clinic",
        }),
      ),
    );
  });

  it("shows the server's reason when an invite is rejected", async () => {
    adminApi.inviteUser.mockRejectedValue(
      httpError(
        409,
        "This user has already activated their account; they can use Forgot password.",
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(
      await screen.findByRole("button", { name: "Invite user" }),
    );
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText(/already activated/)).toBeInTheDocument();
  });

  it("deactivates only after an explicit confirm", async () => {
    adminApi.setUserActive.mockResolvedValue({ ...USERS[1], is_active: false });
    const user = userEvent.setup();
    renderPage();
    const r = await row("new@sunrise.test");
    await user.click(r.getByRole("button", { name: "Deactivate" }));
    expect(adminApi.setUserActive).not.toHaveBeenCalled();
    await user.click(r.getByRole("button", { name: "Cancel" }));
    expect(r.queryByRole("button", { name: "Confirm deactivate" })).toBeNull();
    await user.click(r.getByRole("button", { name: "Deactivate" }));
    await user.click(r.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() =>
      expect(adminApi.setUserActive).toHaveBeenCalledWith("u-pending", false),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /deactivated and signed out everywhere/,
    );
  });

  it("reactivates a deactivated user", async () => {
    adminApi.setUserActive.mockResolvedValue({ ...USERS[2], is_active: true });
    const user = userEvent.setup();
    renderPage();
    const off = await row("former@sunrise.test");
    await user.click(off.getByRole("button", { name: "Reactivate" }));
    await waitFor(() =>
      expect(adminApi.setUserActive).toHaveBeenCalledWith("u-off", true),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /former@sunrise.test reactivated/,
    );
  });

  it("re-sends a pending invite", async () => {
    adminApi.resendInvite.mockResolvedValue(USERS[1]);
    const user = userEvent.setup();
    renderPage();
    const pending = await row("new@sunrise.test");
    await user.click(pending.getByRole("button", { name: "Resend invite" }));
    await waitFor(() =>
      expect(adminApi.resendInvite.mock.calls[0]?.[0]).toBe("u-pending"),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /re-sent to new@sunrise.test/,
    );
  });

  it("surfaces a row-level error when an action fails", async () => {
    adminApi.resendInvite.mockRejectedValue(
      httpError(
        409,
        "This user has already signed in; they can use Forgot password.",
      ),
    );
    const user = userEvent.setup();
    renderPage();
    const pending = await row("new@sunrise.test");
    await user.click(pending.getByRole("button", { name: "Resend invite" }));
    expect(await pending.findByText(/already signed in/)).toBeInTheDocument();
  });

  it("shows pending deactivation requests and resolves them", async () => {
    adminApi.fetchDeactivationRequests.mockResolvedValue([
      {
        id: "req-1",
        user: USERS[1],
        reason: "Leaving the practice",
        status: "pending",
        created_at: "2026-08-21T00:00:00Z",
      },
    ]);
    adminApi.resolveDeactivationRequest.mockResolvedValue({
      ...USERS[1],
      is_active: false,
    });
    const user = userEvent.setup();
    renderPage();
    const card = within(
      await screen.findByTestId("deactivation-request-new@sunrise.test"),
    );
    expect(card.getByText(/Leaving the practice/)).toBeInTheDocument();
    await user.click(card.getByRole("button", { name: /Approve/ }));
    await waitFor(() =>
      expect(
        adminApi.resolveDeactivationRequest.mock.calls[0]?.slice(0, 2),
      ).toEqual(["req-1", "approve"]),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /deactivated and signed out/,
    );
  });

  it("hides the requests section when there are none", async () => {
    renderPage();
    await screen.findByTestId("user-row-admin@heimdall.test");
    expect(screen.queryByText("Deactivation requests")).toBeNull();
  });
});
