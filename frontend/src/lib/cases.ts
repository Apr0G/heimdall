import { api } from "@/lib/api";

export type CaseListItem = {
  id: string;
  status: string;
  patient_initials: string | null;
  payer_name: string | null;
  plan_type: string;
  claim_number: string | null;
  date_of_service: string | null;
  denial_date: string | null;
  appeal_deadline: string | null;
  billed_amount_cents: number | null;
  denied_amount_cents: number | null;
  currency: string;
  carc_codes: string[];
  denial_category: string | null;
  is_appealable: boolean | null;
  probability_band: string | null;
  outcome_result: string | null;
  amount_recovered_cents: number | null;
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
};

export async function fetchCases(
  filters: CaseFilters,
  page = 1,
): Promise<CaseListResponse> {
  const params: Record<string, string> = { page: String(page) };
  if (filters.status) params.status = filters.status;
  if (filters.payer) params.payer = filters.payer;
  const res = await api.get<CaseListResponse>("/api/cases", { params });
  return res.data;
}

// ---- Case detail (Phase 10) ----

export type DocumentDetail = {
  id: string;
  doc_type: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  ocr_status: string;
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

export type CaseDetail = {
  id: string;
  status: string;
  stalled?: boolean;
  error_message: string | null;
  patient_initials: string | null;
  payer_name: string | null;
  plan_type: string;
  claim_number: string | null;
  date_of_service: string | null;
  denial_date: string | null;
  appeal_deadline: string | null;
  billed_amount_cents: number | null;
  denied_amount_cents: number | null;
  currency: string;
  documents: DocumentDetail[];
  extraction: ExtractionDetail | null;
  analysis: AnalysisDetail | null;
  letter: LetterDetail | null;
  letters: LetterDetail[];
  outcome: OutcomeDetail | null;
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

export async function markSubmitted(id: string): Promise<{ id: string; status: string }> {
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

export async function retryCase(id: string): Promise<{ id: string; status: string }> {
  const res = await api.post(`/api/cases/${id}/retry`);
  return res.data;
}

export async function fetchDocumentDownloadUrl(documentId: string): Promise<string> {
  const res = await api.get<{ url: string }>(`/api/documents/${documentId}/download-url`);
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
export async function downloadLetterPdf(id: string, filename: string): Promise<void> {
  const res = await api.get(`/api/cases/${id}/letter.pdf`, { responseType: "blob" });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
