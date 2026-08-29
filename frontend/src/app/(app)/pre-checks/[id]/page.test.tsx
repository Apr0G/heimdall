/**
 * The pre-check report: findings open into problem + fix, and on an editable
 * (born-digital) claim the doctor ticks changes and creates a corrected PDF;
 * on a scanned claim the same findings render with no checkboxes.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CaseDetail } from "@/lib/cases";

const { cases } = vi.hoisted(() => ({
  cases: {
    fetchCase: vi.fn(),
    fetchCaseStatus: vi.fn(),
    createCorrectedClaim: vi.fn(),
    fetchCorrectedClaimDownloadUrl: vi.fn(),
    retryCase: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "case-1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/lib/cases", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/cases")>();
  return { ...actual, ...cases };
});

import PreCheckDetailPage from "./page";

// Synthetic report: an NCCI bundling edit (modifier or remove), an NCCI unit
// cut, and a model documentation task that is never a claim edit.
function detail(over: Partial<CaseDetail> = {}): CaseDetail {
  return {
    id: "case-1",
    status: "ready",
    case_type: "pre_check",
    stalled: false,
    error_message: null,
    patient_initials: "J.D.",
    payer_name: "Test Payer",
    plan_type: "commercial",
    claim_number: "CLM-TEST-0001",
    date_of_service: "2026-08-01",
    denial_date: null,
    appeal_deadline: null,
    billed_amount_cents: 31500,
    denied_amount_cents: null,
    currency: "USD",
    documents: [],
    extraction: null,
    analysis: null,
    letter: null,
    letters: [],
    outcome: null,
    claim_editable: true,
    corrected_claim: null,
    risk_report: {
      overall_risk_band: "high",
      deterministic_count: 2,
      model_count: 1,
      ncci_version_tag: "ptp 2026Q3",
      created_at: "2026-08-27T10:00:00Z",
      findings: [
        {
          check_id: "ncci_ptp",
          severity: "high",
          title:
            "20610 will be denied as bundled into 99213 unless a modifier is added",
          predicted_carc: "CO-97",
          explanation:
            "CMS NCCI lists 20610 as not separately payable with 99213.",
          suggested_fix: "Add an NCCI-associated modifier or remove the line.",
          source: "ncci",
        },
        {
          check_id: "ncci_mue",
          severity: "medium",
          title: "J3301: 2 units exceeds the Medicare MUE limit of 1/day",
          predicted_carc: "CO-151",
          explanation: "CMS publishes an MUE of 1 for J3301.",
          suggested_fix: "Verify the units.",
          source: "ncci",
        },
        {
          check_id: "medical_necessity_narrative",
          severity: "low",
          title: "Note lacks conservative-treatment history",
          predicted_carc: "CO-50",
          explanation: "The note does not say what was tried first.",
          suggested_fix: "Document prior conservative treatment.",
          source: "model",
        },
      ],
      proposed_edits: [
        {
          kind: "add_modifier",
          target: "20610",
          instruction:
            "Add modifier 59/XS/XE to 20610 if distinct — otherwise remove the line",
          value: "59",
          source: "ncci",
        },
        {
          kind: "change_units",
          target: "J3301",
          instruction: "Reduce J3301 from 2 to ≤1 units/day",
          value: "1",
          cap: "day",
          source: "ncci",
        },
        {
          kind: "documentation",
          target: null,
          instruction: "Document prior conservative treatment",
          value: null,
          source: "model",
        },
      ],
    },
    ...over,
  } as CaseDetail;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PreCheckDetailPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("pre-check report page", () => {
  it("opens a finding into the problem and the fix", async () => {
    cases.fetchCase.mockResolvedValue(detail());
    renderPage();
    await screen.findByText(/20610 will be denied/);
    // Every finding carries its own problem/fix panels (native <details>),
    // labelled by where the fix lands: two claim changes, one note task.
    expect(screen.getAllByText("What’s wrong")).toHaveLength(3);
    expect(screen.getAllByText("Change on the claim (CMS-1500)")).toHaveLength(
      2,
    );
    expect(screen.getAllByText("Add to the clinical note")).toHaveLength(1);
    expect(screen.getAllByText("Claim change")).toHaveLength(2);
    expect(screen.getAllByText("Note task")).toHaveLength(1);
    expect(screen.getByText(/doesn’t edit clinical notes/)).toBeInTheDocument();
    expect(screen.getByText(/otherwise remove the line/)).toBeInTheDocument();
    // The old separate card is gone.
    expect(screen.queryByText("Proposed changes")).not.toBeInTheDocument();
  });

  it("ticks claim edits, select-all, and creates a corrected PDF", async () => {
    cases.fetchCase.mockResolvedValue(detail());
    cases.createCorrectedClaim.mockResolvedValue({
      id: "cc-1",
      version: 1,
      results: [],
      total_updated: null,
      downloadable: true,
      created_at: "2026-08-28T10:00:00Z",
      downloaded_at: null,
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/20610 will be denied/);

    // Two claim edits get checkboxes; the documentation task does not.
    const boxes = screen.getAllByRole("checkbox", {
      name: /Include this change/,
    });
    expect(boxes).toHaveLength(2);
    const create = screen.getByRole("button", { name: /Create corrected PDF/ });
    expect(create).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByText("2 of 2 changes selected")).toBeInTheDocument();
    expect(create).toBeEnabled();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();

    // Untick one → the count follows, the button stays enabled.
    await user.click(boxes[1]);
    expect(screen.getByText("1 of 2 changes selected")).toBeInTheDocument();

    await user.click(create);
    await waitFor(() =>
      expect(cases.createCorrectedClaim).toHaveBeenCalledWith("case-1", [
        { index: 0, value: "59" },
      ]),
    );
  });

  it("lets the doctor remove the line instead of adding the modifier", async () => {
    cases.fetchCase.mockResolvedValue(detail());
    cases.createCorrectedClaim.mockResolvedValue({
      id: "cc-1",
      version: 1,
      results: [],
      total_updated: true,
      downloadable: true,
      created_at: "2026-08-28T10:00:00Z",
      downloaded_at: null,
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/20610 will be denied/);
    await user.click(
      screen.getAllByRole("checkbox", { name: /Include this change/ })[0],
    );
    await user.click(screen.getByText(/20610 will be denied/)); // open the row
    await user.click(
      screen.getByRole("checkbox", { name: /Remove the 20610 line instead/ }),
    );
    expect(screen.getByText("Will remove 20610")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: /Create corrected PDF/ }),
    );
    await waitFor(() =>
      expect(cases.createCorrectedClaim).toHaveBeenCalledWith("case-1", [
        { index: 0, remove: true },
      ]),
    );
  });

  it("explains why the button is disabled when a ticked change needs a value", async () => {
    const d = detail();
    // An AI re-level edit with no concrete new code: the doctor must type one.
    d.risk_report!.findings.push({
      check_id: "em_level_mdm",
      severity: "medium",
      title: "99214 documentation supports 99213",
      predicted_carc: "CO-150",
      explanation: "MDM is low.",
      suggested_fix: "Re-level the visit.",
      source: "model",
    });
    d.risk_report!.proposed_edits!.push({
      kind: "change_code",
      target: "99214",
      instruction: "Change 99214 to the level the note supports",
      value: null,
      source: "model",
    });
    cases.fetchCase.mockResolvedValue(d);
    cases.createCorrectedClaim.mockResolvedValue({
      id: "cc-1",
      version: 1,
      results: [],
      total_updated: null,
      downloadable: true,
      created_at: "2026-08-28T10:00:00Z",
      downloaded_at: null,
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/20610 will be denied/);

    await user.click(screen.getByRole("button", { name: "Select all" }));
    const create = screen.getByRole("button", { name: /Create corrected PDF/ });
    expect(create).toBeDisabled();
    expect(
      screen.getByText(/Fill in the new value for 1 selected change/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Needs a value/)).toBeInTheDocument();
    // An NCCI unit limit is a ceiling, not a count to write.
    expect(screen.getByText("Unit limit")).toBeInTheDocument();
    expect(
      screen.getByText(/Will reduce units to at most 1 for the day/),
    ).toBeInTheDocument();

    // The row opened itself; typing a valid code unblocks the button.
    const input = screen
      .getAllByRole("textbox")
      .find((el) => (el as HTMLInputElement).value === "")!;
    await user.type(input, "99213");
    expect(screen.queryByText(/Needs a value/)).not.toBeInTheDocument();
    expect(create).toBeEnabled();
    await user.click(create);
    await waitFor(() =>
      expect(cases.createCorrectedClaim).toHaveBeenCalledWith("case-1", [
        { index: 0, value: "59" },
        { index: 1, value: "1", charge: "scale" },
        { index: 3, value: "99213" },
      ]),
    );
  });

  it("shows the corrected claim with its outcome and a download", async () => {
    cases.fetchCase.mockResolvedValue(
      detail({
        corrected_claim: {
          id: "cc-1",
          version: 2,
          results: [
            {
              index: 0,
              kind: "add_modifier",
              target: "20610",
              value: "XS",
              applied: true,
              reason: null,
            },
            {
              index: 1,
              kind: "change_units",
              target: "J3301",
              value: "1",
              applied: false,
              reason: "no_room",
            },
            {
              index: 2,
              kind: "change_units",
              target: "J2501",
              value: "2",
              applied: true,
              reason: null,
              applied_lines: 2,
              charge_before_cents: 4400,
              charge_after_cents: 1760,
            },
            {
              index: 3,
              kind: "remove_line",
              target: "D50.9",
              value: null,
              applied: true,
              reason: null,
              applied_lines: 1,
              note: "check_dx_pointers",
            },
          ],
          total_updated: null,
          downloadable: true,
          format: "form",
          created_at: "2026-08-28T10:00:00Z",
          downloaded_at: null,
        },
        documents: [
          {
            id: "d1",
            doc_type: "claim",
            original_filename: "claim.pdf",
            file_size_bytes: 1000,
            ocr_status: "not_needed",
            text_source: "form_fields",
          },
        ],
      }),
    );
    cases.fetchCorrectedClaimDownloadUrl.mockResolvedValue("https://s3/signed");
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Corrected claim");
    expect(screen.getByText("Added modifier XS to 20610")).toBeInTheDocument();
    expect(
      screen.getByText(/Set J3301 units to 1 — No space in the box/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Set J2501 units to 2 (2 lines) · charge $44.00 → $17.60",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Removed diagnosis D50.9")).toBeInTheDocument();
    expect(
      screen.getByText(/Check the diagnosis pointers/),
    ).toBeInTheDocument();
    expect(screen.getByText(/still a fillable form/)).toBeInTheDocument();
    expect(screen.getByText("Fillable form")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Download PDF/ }));
    await waitFor(() =>
      expect(open).toHaveBeenCalledWith(
        "https://s3/signed",
        "_blank",
        "noopener",
      ),
    );
    open.mockRestore();
  });

  it("scanned claim: same findings, no checkboxes, a plain explanation", async () => {
    cases.fetchCase.mockResolvedValue(detail({ claim_editable: false }));
    renderPage();
    await screen.findByText(/20610 will be denied/);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Create corrected PDF/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/uploaded as a scan/)).toBeInTheDocument();
  });
});
