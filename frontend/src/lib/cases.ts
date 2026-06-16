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

export async function fetchCases(filters: CaseFilters): Promise<CaseListResponse> {
  const params: Record<string, string> = {};
  if (filters.status) params.status = filters.status;
  if (filters.payer) params.payer = filters.payer;
  const res = await api.get<CaseListResponse>("/api/cases", { params });
  return res.data;
}
