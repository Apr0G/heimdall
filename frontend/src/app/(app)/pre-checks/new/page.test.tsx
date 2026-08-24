/**
 * The pre-check upload flow: two slots (draft claim + clinical notes), submit
 * gated on both, and the created case routed to its report page.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { upload, router } = vi.hoisted(() => ({
  upload: { createPreCheckWithUploads: vi.fn() },
  router: { push: vi.fn(), replace: vi.fn() },
}));

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/upload", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/upload")>();
  return {
    ...actual,
    createPreCheckWithUploads: upload.createPreCheckWithUploads,
  };
});

import NewPreCheckPage from "./page";

function pdf(name: string): File {
  return new File(["%PDF-1.4 test"], name, { type: "application/pdf" });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("new pre-check page", () => {
  it("renders exactly the two pre-check slots — no denial slot", () => {
    render(<NewPreCheckPage />);
    expect(screen.getByText("Draft claim")).toBeInTheDocument();
    expect(screen.getByText("Clinical notes")).toBeInTheDocument();
    expect(screen.queryByText("Denial document")).not.toBeInTheDocument();
  });

  it("disables submit until both files are chosen, then creates and routes", async () => {
    upload.createPreCheckWithUploads.mockResolvedValue({
      id: "abc-123",
      status: "processing",
    });
    const user = userEvent.setup();
    render(<NewPreCheckPage />);

    const submit = screen.getByRole("button", { name: "Run pre-check" });
    expect(submit).toBeDisabled();

    const inputs = document.querySelectorAll('input[type="file"]');
    expect(inputs).toHaveLength(2);
    await user.upload(inputs[0] as HTMLInputElement, pdf("claim.pdf"));
    expect(submit).toBeDisabled(); // one of two
    await user.upload(inputs[1] as HTMLInputElement, pdf("notes.pdf"));
    expect(submit).toBeEnabled();

    await user.click(submit);
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith("/pre-checks/abc-123"),
    );
    expect(upload.createPreCheckWithUploads).toHaveBeenCalledTimes(1);
  });
});
