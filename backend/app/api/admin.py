"""Internal admin overview — the deliberate exception to Hard rule 3.

Every other endpoint filters by `current_user.practice_id`; this router reads
across ALL practices. That is acceptable only under the constraints encoded
here: `require_role("admin")` on every route (server-side RBAC, 403 for the
other roles), aggregates only — no case-level, patient-level, or document-level
data in any response — and an audit_logs row per view.

If a time-window filter (`?since=`) is ever added, model_runs will need an
index on created_at first; today every aggregate is a full-table GROUP BY.
"""

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cases import _TERMINAL_RESULTS, _WIN_RESULTS, win_rate
from app.core.auth import require_role
from app.core.net import client_ip
from app.db.session import get_db
from app.models import (
    AppealLetter,
    Case,
    Document,
    ModelRun,
    Outcome,
    Practice,
    RiskReport,
    User,
)
from app.models.enums import case_status, model_run_purpose, outcome_result, user_role
from app.schemas.admin import (
    AdminCaseStats,
    AdminDocumentStats,
    AdminModelRunStats,
    AdminOutcomeStats,
    AdminOverviewResponse,
    AdminPreCheckStats,
    AdminUserStats,
    PracticeBreakdownItem,
)
from app.services.audit import log_audit, safe_ip
from app.services.model_costs import estimate_cost_cents

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Module-level so the factory runs once, not per-request-signature (B008); every
# route in this router must depend on it.
require_admin = require_role("admin")


def _zero_filled(enum_type) -> dict[str, int]:
    """Every enum member present with 0, so the frontend never key-checks."""
    return {value: 0 for value in enum_type.enums}


def _max_datetime(*candidates: datetime | None) -> datetime | None:
    present = [c for c in candidates if c is not None]
    return max(present) if present else None


@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminOverviewResponse:
    """Global platform aggregates for the internal admin dashboard.

    The SELECTs run sequentially on the one injected session (an AsyncSession
    is not safe for concurrent use); per-practice numbers come from GROUP BY
    practice_id passes merged in Python — never a per-practice query loop.
    """
    practice_count = await session.scalar(select(func.count()).select_from(Practice)) or 0

    user_rows = (
        await session.execute(
            select(
                User.role,
                func.count(),
                func.count().filter(User.is_active.is_(True)),
            ).group_by(User.role)
        )
    ).all()
    users_by_role = _zero_filled(user_role)
    users_total = users_active = 0
    for role, count, active in user_rows:
        users_by_role[role] = count
        users_total += count
        users_active += active

    # Split by case_type so `cases` keeps meaning "appeals" — mixing pre-checks
    # into the billed/denied sums and status counts would quietly distort them.
    case_rows = (
        await session.execute(
            select(
                Case.case_type,
                Case.status,
                func.count(),
                func.coalesce(func.sum(Case.billed_amount_cents), 0),
                func.coalesce(func.sum(Case.denied_amount_cents), 0),
            ).group_by(Case.case_type, Case.status)
        )
    ).all()
    cases_by_status = _zero_filled(case_status)
    prechecks_by_status = _zero_filled(case_status)
    cases_total = billed_total = denied_total = prechecks_total = 0
    for type_value, status_value, count, billed, denied in case_rows:
        if type_value == "pre_check":
            prechecks_by_status[status_value] = count
            prechecks_total += count
            continue
        cases_by_status[status_value] = count
        cases_total += count
        billed_total += billed
        denied_total += denied

    # Headline band of each pre-check's latest risk report ("none" = no flags).
    latest_reports = (
        select(RiskReport.case_id, RiskReport.overall_risk_band)
        .order_by(RiskReport.case_id, RiskReport.created_at.desc())
        .distinct(RiskReport.case_id)
        .subquery()
    )
    band_rows = (
        await session.execute(
            select(latest_reports.c.overall_risk_band, func.count()).group_by(
                latest_reports.c.overall_risk_band
            )
        )
    ).all()
    prechecks_by_band = {"high": 0, "moderate": 0, "low": 0, "none": 0}
    for band, count in band_rows:
        prechecks_by_band[band or "none"] = count

    doc_count, doc_bytes = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Document.file_size_bytes), 0)).select_from(
                Document
            )
        )
    ).one()

    letter_count = await session.scalar(select(func.count()).select_from(AppealLetter)) or 0

    run_rows = (
        await session.execute(
            select(
                ModelRun.purpose,
                func.count(),
                func.count().filter(ModelRun.status == "error"),
                func.coalesce(func.sum(ModelRun.input_tokens), 0),
                func.coalesce(func.sum(ModelRun.output_tokens), 0),
                func.coalesce(func.sum(ModelRun.latency_ms), 0),
                # Count of rows with a latency, so the average weights only them.
                func.count(ModelRun.latency_ms),
            ).group_by(ModelRun.purpose)
        )
    ).all()
    runs_by_purpose = _zero_filled(model_run_purpose)
    runs_total = runs_errors = tokens_in = tokens_out = 0
    latency_sum = latency_n = 0
    for purpose, count, errors, t_in, t_out, lat_sum, lat_n in run_rows:
        runs_by_purpose[purpose] = count
        runs_total += count
        runs_errors += errors
        tokens_in += t_in
        tokens_out += t_out
        latency_sum += lat_sum
        latency_n += lat_n
    avg_latency_ms = round(latency_sum / latency_n, 1) if latency_n else None

    # Tokens summed per model_id in SQL, priced once per group — keeps the
    # integer floor loss under a cent per distinct model (see model_costs).
    model_token_rows = (
        await session.execute(
            select(
                ModelRun.model_id,
                func.coalesce(func.sum(ModelRun.input_tokens), 0),
                func.coalesce(func.sum(ModelRun.output_tokens), 0),
            ).group_by(ModelRun.model_id)
        )
    ).all()
    estimated_cost = sum(
        estimate_cost_cents(t_in, t_out, model_id) for model_id, t_in, t_out in model_token_rows
    )

    outcome_rows = (
        await session.execute(
            select(
                Outcome.result,
                func.count(),
                func.coalesce(func.sum(Outcome.amount_recovered_cents), 0),
            ).group_by(Outcome.result)
        )
    ).all()
    outcomes_by_result = _zero_filled(outcome_result)
    resolved_count = win_count = recovered_total = 0
    for result, count, recovered in outcome_rows:
        if result is None:  # result is nullable; unreported rows aren't a bucket
            continue
        outcomes_by_result[result] = count
        if result in _TERMINAL_RESULTS:
            resolved_count += count
        if result in _WIN_RESULTS:
            win_count += count
            # Only dollars from actual wins, mirroring /api/cases/summary.
            recovered_total += recovered

    # --- Per-practice breakdown: one GROUP BY practice_id pass per source table.
    practice_rows = (
        await session.execute(
            select(Practice.id, Practice.name, Practice.state, Practice.created_at).order_by(
                Practice.created_at
            )
        )
    ).all()

    users_by_practice: dict[UUID, tuple[int, datetime | None]] = {
        pid: (count, last_seen)
        for pid, count, last_seen in (
            await session.execute(
                select(User.practice_id, func.count(), func.max(User.last_seen_at)).group_by(
                    User.practice_id
                )
            )
        ).all()
    }

    cases_by_practice: dict[UUID, dict[str, int]] = defaultdict(dict)
    case_activity_by_practice: dict[UUID, datetime | None] = {}
    for pid, status_value, count, last_updated in (
        await session.execute(
            select(Case.practice_id, Case.status, func.count(), func.max(Case.updated_at)).group_by(
                Case.practice_id, Case.status
            )
        )
    ).all():
        cases_by_practice[pid][status_value] = count
        case_activity_by_practice[pid] = _max_datetime(
            case_activity_by_practice.get(pid), last_updated
        )

    # model_runs has no practice_id — it reaches the tenant through cases.
    tokens_by_practice: dict[UUID, tuple[int, int]] = {
        pid: (t_in, t_out)
        for pid, t_in, t_out in (
            await session.execute(
                select(
                    Case.practice_id,
                    func.coalesce(func.sum(ModelRun.input_tokens), 0),
                    func.coalesce(func.sum(ModelRun.output_tokens), 0),
                )
                .select_from(ModelRun)
                .join(Case, Case.id == ModelRun.case_id)
                .group_by(Case.practice_id)
            )
        ).all()
    }

    recovered_by_practice: dict[UUID, int] = {
        pid: recovered
        for pid, recovered in (
            await session.execute(
                select(
                    Case.practice_id,
                    func.coalesce(func.sum(Outcome.amount_recovered_cents), 0),
                )
                .select_from(Outcome)
                .join(Case, Case.id == Outcome.case_id)
                .where(Outcome.result.in_(_WIN_RESULTS))
                .group_by(Case.practice_id)
            )
        ).all()
    }

    practices = []
    for pid, name, state, created_at in practice_rows:
        user_count, last_seen = users_by_practice.get(pid, (0, None))
        status_counts = _zero_filled(case_status) | cases_by_practice.get(pid, {})
        t_in, t_out = tokens_by_practice.get(pid, (0, 0))
        practices.append(
            PracticeBreakdownItem(
                id=pid,
                name=name,
                state=state,
                created_at=created_at,
                user_count=user_count,
                case_count=sum(status_counts.values()),
                cases_by_status=status_counts,
                input_tokens=t_in,
                output_tokens=t_out,
                # Default rate, not per-model: a 3-column group-by isn't worth it
                # while a single model is in production.
                estimated_cost_cents=estimate_cost_cents(t_in, t_out, None),
                amount_recovered_cents=recovered_by_practice.get(pid, 0),
                last_activity_at=_max_datetime(case_activity_by_practice.get(pid), last_seen),
            )
        )

    # Cross-tenant read audit — the whole point of logging this view.
    await log_audit(
        session,
        action="admin_overview_view",
        resource_type="admin_overview",
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()

    return AdminOverviewResponse(
        practice_count=practice_count,
        users=AdminUserStats(total=users_total, active=users_active, by_role=users_by_role),
        cases=AdminCaseStats(
            total=cases_total,
            by_status=cases_by_status,
            billed_amount_cents=billed_total,
            denied_amount_cents=denied_total,
        ),
        pre_checks=AdminPreCheckStats(
            total=prechecks_total,
            by_status=prechecks_by_status,
            by_risk_band=prechecks_by_band,
        ),
        documents=AdminDocumentStats(count=doc_count, total_bytes=doc_bytes),
        appeal_letter_count=letter_count,
        model_runs=AdminModelRunStats(
            total=runs_total,
            by_purpose=runs_by_purpose,
            error_count=runs_errors,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            avg_latency_ms=avg_latency_ms,
            estimated_cost_cents=estimated_cost,
        ),
        outcomes=AdminOutcomeStats(
            by_result=outcomes_by_result,
            resolved_count=resolved_count,
            win_count=win_count,
            win_rate=win_rate(win_count, resolved_count),
            amount_recovered_cents=recovered_total,
        ),
        practices=practices,
    )
