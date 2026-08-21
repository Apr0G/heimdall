from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AdminUserStats(BaseModel):
    total: int
    active: int
    by_role: dict[str, int]


class AdminCaseStats(BaseModel):
    total: int
    by_status: dict[str, int]
    billed_amount_cents: int
    denied_amount_cents: int


class AdminDocumentStats(BaseModel):
    count: int
    total_bytes: int


class AdminModelRunStats(BaseModel):
    total: int
    by_purpose: dict[str, int]
    error_count: int
    input_tokens: int
    output_tokens: int
    # Latency is not money; a float average is fine (None until a run has one).
    avg_latency_ms: float | None
    estimated_cost_cents: int


class AdminOutcomeStats(BaseModel):
    by_result: dict[str, int]
    resolved_count: int
    win_count: int
    win_rate: float | None
    amount_recovered_cents: int


class PracticeBreakdownItem(BaseModel):
    id: UUID
    name: str
    state: str | None
    created_at: datetime
    user_count: int
    case_count: int
    cases_by_status: dict[str, int]
    input_tokens: int
    output_tokens: int
    estimated_cost_cents: int
    amount_recovered_cents: int
    last_activity_at: datetime | None


class AdminOverviewResponse(BaseModel):
    practice_count: int
    users: AdminUserStats
    cases: AdminCaseStats
    documents: AdminDocumentStats
    appeal_letter_count: int
    model_runs: AdminModelRunStats
    outcomes: AdminOutcomeStats
    practices: list[PracticeBreakdownItem]


# --- User management --------------------------------------------------------


class AdminPracticeItem(BaseModel):
    id: UUID
    name: str


class AdminUserItem(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    role: str
    practice_id: UUID
    practice_name: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    # Never logged in → the invite (temporary password) is still what they hold,
    # so "Resend invite" is the useful action.
    invite_pending: bool


class AdminUsersResponse(BaseModel):
    users: list[AdminUserItem]
    practices: list[AdminPracticeItem]


class AdminInviteRequest(BaseModel):
    email: str
    role: str
    full_name: str | None = None
    practice_id: UUID | None = None
    practice_name: str | None = None


class AdminInviteResponse(BaseModel):
    user: AdminUserItem
    created_user: bool
    created_practice: bool
    invite_resent: bool
