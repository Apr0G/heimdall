import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { state, router } = vi.hoisted(() => ({
  state: {
    user: null as null | { role: string },
    loading: false,
    pathname: "/admin",
  },
  router: { replace: vi.fn() },
}));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: state.user, loading: state.loading }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => state.pathname,
}));

import AdminLayout from "./layout";

beforeEach(() => vi.clearAllMocks());

describe("admin layout", () => {
  it("redirects non-admins to the dashboard and renders nothing", () => {
    state.user = { role: "doctor" };
    const { container } = render(<AdminLayout>child</AdminLayout>);
    expect(router.replace).toHaveBeenCalledWith("/dashboard");
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the section nav for admins with the current section marked", () => {
    state.user = { role: "admin" };
    state.pathname = "/admin/users";
    render(<AdminLayout>child</AdminLayout>);
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByText("child")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Users" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});
