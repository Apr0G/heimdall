import { api } from "@/lib/api";

export type CaseListItem = {
  id: string;
  status: string;
  case_type?: string;
  patient_initials: string | null;
  payer_name: string | null;
  plan_type: string;
  claim_number: string | null;
  date_of_service: string | null;
  denial_date: string | null;
  appeal_deadline: string | null;
  deadline_note?: string | null;
  billed_amount_cents: number | null;
  denied_amount_cents: number | null;
  currency: string;
  carc_codes: string[];
  denial_category: string | null;
  is_appealable: boolean | null;
  probability_band: string | null;
  outcome_result: string | null;
  amount_recovered_cents: number | null;
  // Pre-check cases only: the latest risk report's headline band.
  overall_risk_band?: string | null;
};

export type CaseListResponse = {
  items: CaseListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type CaseFilters = {
  status?: string;
  payer?: string;
  // Server defaults to "appeal"; pass "pre_check" for the pre-checks list.
  case_type?: string;
};

export async function fetchCases(
  filters: CaseFilters,
  page = 1,
): Promise<CaseListResponse> {
  const params: Record<string, string> = { page: String(page) };
  if (filters.status) params.status = filters.status;
  if (filters.payer) params.payer = filters.payer;
  if (filters.case_type) params.case_type = filters.case_type;
  const res = await api.get<CaseListResponse>("/api/cases", { params });
  return res.data;
}

// PHI-free feed of in-flight cases, for the background "is it done yet?" poll
// (so the full PHI-bearing list isn't fetched/audited every few seconds).
export type ProcessingItem = { id: string; case_type: string };
export async function fetchProcessingItems(): Promise<ProcessingItem[]> {
  const res = await api.get<{ ids: string[]; items?: ProcessingItem[] }>(
    "/api/cases/processing-ids",
  );
  // `items` is the typed shape; fall back to bare ids (treated as appeals)
  // during a deploy window where the backend predates it.
  return (
    res.data.items ??
    (res.data.ids ?? []).map((id) => ({ id, case_type: "appeal" as const }))
  );
}

// PHI-free status for the detail page's processing poll (no audit row per poll).
export type CaseStatusPoll = { id: string; status: string; stalled: boolean };
export async function fetchCaseStatus(id: string): Promise<CaseStatusPoll> {
  const res = await api.get<CaseStatusPoll>(`/api/cases/${id}/status`);
  return res.data;
}

// ---- Case detail (Phase 10) ----

export type DocumentDetail = {
  id: string;
  doc_type: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  ocr_status: string;
  // pdf_text | ocr | form_fields (fillable form); null before it was recorded.
  text_source?: string | null;
};

export type ExtractionDetail = {
  payer_name: string | null;
  plan_type: string | null;
  claim_number: string | null;
  carc_codes: string[];
  rarc_codes: string[];
  group_codes: string[];
  cpt_codes: string[];
  icd10_codes: string[];
  modifiers: string[];
  pos_codes: string[];
  billed_amount_cents: number | null;
  denied_amount_cents: number | null;
  confidence: number | null;
};

export type AnalysisDetail = {
  denial_category: string | null;
  is_appealable: boolean;
  appealability_reason: string | null;
  success_probability: number | null;
  probability_band: string | null;
  reasoning_text: string | null;
  recommended_appeal_level: string | null;
  additional_documents_needed: string[];
};

export type LetterDetail = {
  id: string;
  version: number;
  status: string;
  appeal_type: string | null;
  body: string | null;
  created_at: string;
};

export type OutcomeDetail = {
  action_taken: string | null;
  result: string | null;
  amount_recovered_cents: number | null;
  resolution_date: string | null;
  notes: string | null;
  reported_at: string;
};

export type RiskFinding = {
  check_id: string;
  severity: string; // high | medium | low | info
  title: string;
  predicted_carc: string | null;
  explanation: string | null;
  suggested_fix: string | null;
  source: string; // "ncci" (deterministic) | "model" (documentation review)
};

export type ProposedEdit = {
  kind: string; // remove_line | add_modifier | change_units | change_code | documentation
  target: string | null;
  instruction: string;
  // New modifier / units / code the edit writes; null when the biller chooses.
  value: string | null;
  source: string; // "ncci" | "model"
};

export type CorrectedClaimEditResult = {
  index: number;
  kind: string;
  target: string | null;
  value: string | null;
  applied: boolean;
  reason: string | null;
  // A code can sit on several service lines (one per date); how many it reached.
  applied_lines?: number;
  // Advisory for an applied edit, e.g. check_dx_pointers after a Box 21 removal.
  note?: string | null;
  // Scaled unit change: the line charge before and after, in cents.
  charge_before_cents?: number | null;
  charge_after_cents?: number | null;
};

export type CorrectedClaimDetail = {
  id: string;
  version: number;
  results: CorrectedClaimEditResult[];
  // null = no charge changed; false = a line was removed but the Box 28 total
  // couldn't be located, so the user must fix it by hand.
  total_updated: boolean | null;
  downloadable: boolean;
  // "form": the claim was a fillable PDF and the corrected copy stays fillable.
  format?: "text" | "form" | null;
  created_at: string;
  downloaded_at: string | null;
};

export type CorrectedClaimSelection = {
  index: number;
  value?: string | null;
  remove?: boolean;
  // Unit changes: "scale" the line charge with the units (default) or "keep" it.
  charge?: "scale" | "keep";
};

export type RiskReportDetail = {
  overall_risk_band: string | null;
  findings: RiskFinding[];
  proposed_edits?: ProposedEdit[];
  deterministic_count: number;
  model_count: number;
  ncci_version_tag: string | null;
  created_at: string;
};

export type CaseDetail = {
  id: string;
  status: string;
  case_type?: string;
  stalled?: boolean;
  error_message: string | null;
  patient_initials: string | null;
  payer_name: string | null;
  plan_type: string;
  claim_number: string | null;
  date_of_service: string | null;
  denial_date: string | null;
  appeal_deadline: string | null;
  deadline_note?: string | null;
  billed_amount_cents: number | null;
  denied_amount_cents: number | null;
  currency: string;
  documents: DocumentDetail[];
  extraction: ExtractionDetail | null;
  analysis: AnalysisDetail | null;
  letter: LetterDetail | null;
  letters: LetterDetail[];
  outcome: OutcomeDetail | null;
  // Pre-check cases only; always null for appeals.
  risk_report?: RiskReportDetail | null;
  // Pre-check only: the draft claim has a text layer the patcher can edit.
  claim_editable?: boolean;
  corrected_claim?: CorrectedClaimDetail | null;
};

export type OutcomePayload = {
  result: string;
  amount_recovered_cents?: number | null;
  resolution_date?: string | null;
  notes?: string | null;
};

export async function fetchCase(id: string): Promise<CaseDetail> {
  const res = await api.get<CaseDetail>(`/api/cases/${id}`);
  return res.data;
}

export async function markSubmitted(
  id: string,
): Promise<{ id: string; status: string }> {
  const res = await api.post(`/api/cases/${id}/mark-submitted`);
  return res.data;
}

export async function submitOutcome(
  id: string,
  payload: OutcomePayload,
): Promise<{ id: string; status: string }> {
  const res = await api.post(`/api/cases/${id}/outcome`, payload);
  return res.data;
}

export async function retryCase(
  id: string,
): Promise<{ id: string; status: string }> {
  const res = await api.post(`/api/cases/${id}/retry`);
  return res.data;
}

export async function createCorrectedClaim(
  id: string,
  selections: CorrectedClaimSelection[],
): Promise<CorrectedClaimDetail> {
  const res = await api.post<CorrectedClaimDetail>(
    `/api/cases/${id}/corrected-claim`,
    { selections },
  );
  return res.data;
}

export async function fetchCorrectedClaimDownloadUrl(
  id: string,
): Promise<string> {
  const res = await api.get<{ url: string }>(
    `/api/cases/${id}/corrected-claim/download-url`,
  );
  return res.data.url;
}

export async function fetchDocumentDownloadUrl(
  documentId: string,
): Promise<string> {
  const res = await api.get<{ url: string }>(
    `/api/documents/${documentId}/download-url`,
  );
  return res.data.url;
}

// ---- Dashboard summary / flywheel (Phase 11) ----

export type PendingOutcomeItem = {
  id: string;
  patient_initials: string | null;
  payer_name: string | null;
  denied_amount_cents: number | null;
  currency: string;
  submitted_days_ago: number;
};

export type CaseSummary = {
  month_case_count: number;
  month_pre_check_count?: number;
  resolved_count: number;
  win_count: number;
  win_rate: number | null;
  total_recovered_cents: number;
  pending_outcomes: PendingOutcomeItem[];
};

export async function fetchSummary(): Promise<CaseSummary> {
  const res = await api.get<CaseSummary>("/api/cases/summary");
  return res.data;
}

/** Fetch the server-generated letter PDF (auth header required) and save it. */
export async function downloadLetterPdf(
  id: string,
  filename: string,
): Promise<void> {
  const res = await api.get(`/api/cases/${id}/letter.pdf`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  // Attached + deferred revoke: Firefox cancels a download whose blob URL is
  // revoked on the same tick as the click on a detached anchor.
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
