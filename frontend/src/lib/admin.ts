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

// --- User management (mirrors AdminUsersResponse / AdminInviteRequest) -------

export type AdminPractice = { id: string; name: string };

export type AdminUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: "doctor" | "office_manager" | "admin";
  practice_id: string;
  practice_name: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  invite_pending: boolean;
};

export type AdminUsers = { users: AdminUser[]; practices: AdminPractice[] };

export type InvitePayload = {
  email: string;
  role: AdminUser["role"];
  full_name?: string | null;
  practice_id?: string | null;
  practice_name?: string | null;
};

export type InviteResult = {
  user: AdminUser;
  created_user: boolean;
  created_practice: boolean;
  invite_resent: boolean;
};

export async function fetchAdminUsers(): Promise<AdminUsers> {
  const res = await api.get<AdminUsers>("/api/admin/users");
  return res.data;
}

export async function inviteUser(
  payload: InvitePayload,
): Promise<InviteResult> {
  const res = await api.post<InviteResult>("/api/admin/users", payload);
  return res.data;
}

export async function resendInvite(userId: string): Promise<AdminUser> {
  const res = await api.post<AdminUser>(
    `/api/admin/users/${userId}/resend-invite`,
  );
  return res.data;
}

export async function setUserActive(
  userId: string,
  active: boolean,
): Promise<AdminUser> {
  const res = await api.post<AdminUser>(
    `/api/admin/users/${userId}/${active ? "reactivate" : "deactivate"}`,
  );
  return res.data;
}
