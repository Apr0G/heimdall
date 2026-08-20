import { api } from "@/lib/api";

// Mirrors backend/app/schemas/admin.py. Aggregates only — nothing in this
// payload is case-level or patient-level.

export type AdminUserStats = {
  total: number;
  active: number;
  by_role: Record<string, number>;
};

export type AdminCaseStats = {
  total: number;
  by_status: Record<string, number>;
  billed_amount_cents: number;
  denied_amount_cents: number;
};

export type AdminDocumentStats = {
  count: number;
  total_bytes: number;
};

export type AdminModelRunStats = {
  total: number;
  by_purpose: Record<string, number>;
  error_count: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number | null;
  estimated_cost_cents: number;
};

export type AdminOutcomeStats = {
  by_result: Record<string, number>;
  resolved_count: number;
  win_count: number;
  win_rate: number | null;
  amount_recovered_cents: number;
};

export type PracticeBreakdownItem = {
  id: string;
  name: string;
  state: string | null;
  created_at: string;
  user_count: number;
  case_count: number;
  cases_by_status: Record<string, number>;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_cents: number;
  amount_recovered_cents: number;
  last_activity_at: string | null;
};

export type AdminOverview = {
  practice_count: number;
  users: AdminUserStats;
  cases: AdminCaseStats;
  documents: AdminDocumentStats;
  appeal_letter_count: number;
  model_runs: AdminModelRunStats;
  outcomes: AdminOutcomeStats;
  practices: PracticeBreakdownItem[];
};

export async function fetchAdminOverview(): Promise<AdminOverview> {
  const res = await api.get<AdminOverview>("/api/admin/overview");
  return res.data;
}
