import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.core.config import settings as _settings
from app.core.net import client_ip
from app.core.rate_limit import ai_limiter
from app.db.session import get_db
from app.models import (
    Analysis,
    AppealLetter,
    Case,
    CorrectedClaim,
    Document,
    Extraction,
    Outcome,
    RiskReport,
    User,
)
from app.schemas.case import (
    AnalysisDetail,
    CaseDetailResponse,
    CaseListItem,
    CaseListResponse,
    CaseStatusFilter,
    CaseStatusPollResponse,
    CaseStatusResponse,
    CaseSummaryResponse,
    CaseType,
    CorrectedClaimDetail,
    CorrectedClaimEditResult,
    CorrectedClaimRequest,
    CreateCaseRequest,
    CreateCaseResponse,
    DocumentDetail,
    DownloadUrlResponse,
    ExtractionDetail,
    LetterDetail,
    OutcomeDetail,
    OutcomeRequest,
    PendingOutcomeItem,
    ProcessingIdsResponse,
    ProcessingItem,
    ProposedEditDetail,
    ReanalyzeRequest,
    RiskFindingDetail,
    RiskReportDetail,
    UploadSlot,
    UploadUrlsRequest,
    UploadUrlsResponse,
)
from app.services import corrected_claim as corrected_claim_service
from app.services import pdf_gen
from app.services.analysis import SUPPLEMENTAL_DOC_TYPES
from app.services.audit import log_audit, log_read, safe_ip
from app.services.claim_patch import ClaimPatchError
from app.services.extraction import deadline_note
from app.services.pipeline import run_full_pipeline, run_precheck_pipeline, run_reanalysis
from app.services.s3 import (
    PRECHECK_DOC_TYPES,
    REQUIRED_DOC_TYPES,
    case_document_key,
    head_object,
    move_object,
    presigned_get_url,
    presigned_put_url,
    temp_upload_key,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])

# Outcome/action validation now lives on the schema as a Literal, so bad input is
# a 422 at the boundary rather than a hand-maintained set checked in the router.
# A reported outcome resolves the case unless it is still pending.
_TERMINAL_RESULTS = {"overturned", "upheld", "partial", "withdrawn"}
# A "win" for the recovery dashboard's win-rate.
_WIN_RESULTS = {"overturned", "partial"}
# Days after submission before we nag for an outcome.
OUTCOME_REMINDER_DAYS = 30

# A `processing` case whose row hasn't advanced in this long is treated as stalled:
# the in-process BackgroundTasks pipeline was killed (deploy/crash/OOM) and will
# never finish. Such a case may be retried and the UI surfaces a retry affordance.
# The threshold is generous — a legitimate phase (incl. Textract) stays well under it.
STALE_PROCESSING = timedelta(minutes=15)

# Reject oversized uploads before Textract/analysis. Presigned PUT URLs carry no
# size limit of their own, so we enforce it here after the object lands.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _assert_within_upload_cap(head: dict | None, doc_type: str) -> None:
    if head is not None and (head.get("ContentLength") or 0) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{doc_type} file is too large (25 MB max).")


def _is_stalled(case: Case) -> bool:
    """True when a `processing` case's row hasn't advanced within STALE_PROCESSING
    — i.e. the background pipeline died and the case is safe to retry."""
    return (
        case.status == "processing"
        and case.updated_at is not None
        and datetime.now(UTC) - case.updated_at > STALE_PROCESSING
    )


def _stalled_sql():
    """SQL twin of `_is_stalled`, so staleness can be evaluated by the database
    inside the claim statement instead of in Python beforehand. Uses `now()` from
    the DB, which is also the clock that writes `updated_at`."""
    return and_(
        Case.status == "processing",
        Case.updated_at.is_not(None),
        Case.updated_at < func.now() - STALE_PROCESSING,
    )


def case_status_after_outcome(result: str) -> str:
    return "resolved" if result in _TERMINAL_RESULTS else "submitted"


def win_rate(win_count: int, resolved_count: int) -> float | None:
    """Wins over resolved cases, or None when nothing has resolved yet."""
    if resolved_count <= 0:
        return None
    return round(win_count / resolved_count, 3)


@router.get("", response_model=CaseListResponse)
async def list_cases(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    # Literal, not str: an unvalidated value reaches the native Postgres enum and
    # raises DataError -> 500. `?status=Ready` is a client bug deserving a 422.
    status: CaseStatusFilter | None = Query(None, description="Filter by case status"),
    payer: str | None = Query(None, description="Case-insensitive payer name search"),
    # Defaults to appeals so the pre-existing dashboard keeps its exact shape;
    # pre-check cases (NULL deadlines, no outcomes) never leak into it.
    case_type: CaseType = Query("appeal", description="Which kind of cases to list"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> CaseListResponse:
    filters = [Case.practice_id == current_user.practice_id, Case.case_type == case_type]
    if status:
        filters.append(Case.status == status)
    if payer:
        filters.append(Case.payer_name.ilike(f"%{payer}%"))

    total = await session.scalar(select(func.count()).select_from(Case).where(*filters))

    cases = (
        await session.scalars(
            select(Case)
            .where(*filters)
            # Soonest deadline first (undated cases last), then newest.
            .order_by(Case.appeal_deadline.asc().nulls_last(), Case.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()

    case_ids = [c.id for c in cases]
    extractions: dict = {}
    analyses: dict = {}
    outcomes: dict = {}
    if case_ids:
        # DISTINCT ON (case_id) + ORDER BY created_at DESC = latest row per case.
        ex_rows = (
            await session.scalars(
                select(Extraction)
                .where(Extraction.case_id.in_(case_ids))
                .order_by(Extraction.case_id, Extraction.created_at.desc())
                .distinct(Extraction.case_id)
            )
        ).all()
        extractions = {e.case_id: e for e in ex_rows}

        an_rows = (
            await session.scalars(
                select(Analysis)
                .where(Analysis.case_id.in_(case_ids))
                .order_by(Analysis.case_id, Analysis.created_at.desc())
                .distinct(Analysis.case_id)
            )
        ).all()
        analyses = {a.case_id: a for a in an_rows}

        out_rows = (
            await session.scalars(select(Outcome).where(Outcome.case_id.in_(case_ids)))
        ).all()
        outcomes = {o.case_id: o for o in out_rows}

    risk_bands: dict = {}
    if case_ids and case_type == "pre_check":
        rr_rows = (
            await session.scalars(
                select(RiskReport)
                .where(RiskReport.case_id.in_(case_ids))
                .order_by(RiskReport.case_id, RiskReport.created_at.desc())
                .distinct(RiskReport.case_id)
            )
        ).all()
        risk_bands = {r.case_id: r.overall_risk_band for r in rr_rows}

    items = [
        CaseListItem(
            id=c.id,
            status=c.status,
            case_type=c.case_type,
            overall_risk_band=risk_bands.get(c.id),
            patient_initials=c.patient_initials,
            payer_name=c.payer_name,
            plan_type=c.plan_type,
            claim_number=c.claim_number,
            date_of_service=c.date_of_service,
            denial_date=c.denial_date,
            appeal_deadline=c.appeal_deadline,
            billed_amount_cents=c.billed_amount_cents,
            denied_amount_cents=c.denied_amount_cents,
            currency=c.currency,
            carc_codes=extractions[c.id].carc_codes if c.id in extractions else [],
            denial_category=(analyses[c.id].denial_category if c.id in analyses else None),
            is_appealable=analyses[c.id].is_appealable if c.id in analyses else None,
            probability_band=(analyses[c.id].probability_band if c.id in analyses else None),
            outcome_result=outcomes[c.id].result if c.id in outcomes else None,
            amount_recovered_cents=(
                outcomes[c.id].amount_recovered_cents if c.id in outcomes else None
            ),
        )
        for c in cases
    ]

    # PHI-access audit (§164.312(b)): the list carries patient initials, claim
    # numbers, dates and amounts. Coarse "list viewed" row — the background poll
    # uses the PHI-free /processing-ids feed, so this fires on real page loads only.
    await log_audit(
        session,
        action="case_list_view",
        resource_type="case_list",
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()

    return CaseListResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.get("/summary", response_model=CaseSummaryResponse)
async def case_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseSummaryResponse:
    """Recovery stats + the list of submitted cases overdue for an outcome.

    This is the flywheel: the practice sees their win rate and dollars
    recovered (their benefit), and we get the outcome labels (ours).
    """
    pid = current_user.practice_id
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    month_case_count = await session.scalar(
        select(func.count())
        .select_from(Case)
        .where(
            Case.practice_id == pid,
            Case.case_type == "appeal",
            Case.created_at >= month_start,
        )
    )
    month_pre_check_count = await session.scalar(
        select(func.count())
        .select_from(Case)
        .where(
            Case.practice_id == pid,
            Case.case_type == "pre_check",
            Case.created_at >= month_start,
        )
    )

    def _outcome_count(results: set[str]):
        return (
            select(func.count())
            .select_from(Outcome)
            .join(Case, Case.id == Outcome.case_id)
            .where(Case.practice_id == pid, Outcome.result.in_(results))
        )

    resolved_count = await session.scalar(_outcome_count(_TERMINAL_RESULTS)) or 0
    win_count = await session.scalar(_outcome_count(_WIN_RESULTS)) or 0
    total_recovered = (
        await session.scalar(
            select(func.coalesce(func.sum(Outcome.amount_recovered_cents), 0))
            .select_from(Outcome)
            .join(Case, Case.id == Outcome.case_id)
            # Only count dollars from actual wins, not every outcome row.
            .where(Case.practice_id == pid, Outcome.result.in_(_WIN_RESULTS))
        )
        or 0
    )

    cutoff = now - timedelta(days=OUTCOME_REMINDER_DAYS)
    pending_rows = (
        await session.scalars(
            select(Case)
            .where(
                Case.practice_id == pid,
                Case.status == "submitted",
                Case.submitted_at.is_not(None),
                Case.submitted_at <= cutoff,
                # Keep nagging until a TERMINAL outcome is logged — a 'pending'
                # outcome row must not silence the reminder forever.
                Case.id.not_in(
                    select(Outcome.case_id).where(Outcome.result.in_(_TERMINAL_RESULTS))
                ),
            )
            .order_by(Case.submitted_at.asc())
            # Bound the payload — oldest overdue cases first; the tail keeps nagging.
            .limit(200)
        )
    ).all()

    # PHI-access audit (§164.312(b)): pending_outcomes carries patient initials.
    await log_audit(
        session,
        action="case_summary_view",
        resource_type="case_summary",
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()

    return CaseSummaryResponse(
        month_case_count=month_case_count or 0,
        month_pre_check_count=month_pre_check_count or 0,
        resolved_count=resolved_count,
        win_count=win_count,
        win_rate=win_rate(win_count, resolved_count),
        total_recovered_cents=total_recovered,
        pending_outcomes=[
            PendingOutcomeItem(
                id=c.id,
                patient_initials=c.patient_initials,
                payer_name=c.payer_name,
                denied_amount_cents=c.denied_amount_cents,
                currency=c.currency,
                submitted_days_ago=(now - c.submitted_at).days,
            )
            for c in pending_rows
        ],
    )


@router.get("/processing-ids", response_model=ProcessingIdsResponse)
async def processing_case_ids(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProcessingIdsResponse:
    """IDs of the practice's in-flight cases — a PHI-free feed for the background
    'is anything done yet?' poll, so the full (PHI-bearing) list isn't fetched
    (or audited) every few seconds."""
    rows = (
        await session.execute(
            select(Case.id, Case.case_type).where(
                Case.practice_id == current_user.practice_id,
                Case.status == "processing",
            )
        )
    ).all()
    return ProcessingIdsResponse(
        ids=[r.id for r in rows],
        items=[ProcessingItem(id=r.id, case_type=r.case_type) for r in rows],
    )


def _reject_duplicate_keys(documents: list) -> None:
    """Reject the same upload key submitted for more than one slot — the first
    move_object deletes the source, so a later slot 500s mid-loop and strands the
    moved object under practices/ with no DB row."""
    keys = [d.s3_key for d in documents]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="Duplicate upload key in request")


# Exact document set per case type; the sorted-exact-match also rejects
# duplicate types (which would silently overwrite each other in the pipeline's
# doc_type-keyed text map).
_DOCS_BY_CASE_TYPE = {"appeal": REQUIRED_DOC_TYPES, "pre_check": PRECHECK_DOC_TYPES}

# Endpoints that only make sense for an appeal (supplemental docs, submission,
# outcomes). A `ready` pre-check deliberately has no re-run path in v1 — a
# corrected claim is a new pre-check (decision D8 in the plan).
_APPEAL_ONLY = "This action is not available for pre-check cases"


def _require_docs(case_type: str, doc_types: list[str]) -> None:
    required = _DOCS_BY_CASE_TYPE[case_type]
    if sorted(doc_types) != sorted(required):
        raise HTTPException(
            status_code=400,
            detail=f"Exactly these documents are required: {', '.join(required)}",
        )


def _require_appeal_case(case: Case) -> None:
    if case.case_type != "appeal":
        raise HTTPException(status_code=400, detail=_APPEAL_ONLY)


def _pipeline_for(case_type: str):
    return run_precheck_pipeline if case_type == "pre_check" else run_full_pipeline


@router.post("/upload-urls", response_model=UploadUrlsResponse)
async def create_upload_urls(
    body: UploadUrlsRequest,
    current_user: User = Depends(get_current_user),
) -> UploadUrlsResponse:
    _require_docs(body.case_type, [d.doc_type for d in body.documents])
    uploads: list[UploadSlot] = []
    for doc in body.documents:
        if doc.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")
        key = temp_upload_key(current_user.practice_id)
        url = await run_in_threadpool(presigned_put_url, key, doc.content_type)
        uploads.append(UploadSlot(doc_type=doc.doc_type, s3_key=key, upload_url=url))
    return UploadUrlsResponse(uploads=uploads)


@router.post("", response_model=CreateCaseResponse, status_code=status.HTTP_201_CREATED)
@ai_limiter.limit(_settings.rate_limit_ai)
async def create_case(
    body: CreateCaseRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CreateCaseResponse:
    _require_docs(body.case_type, [d.doc_type for d in body.documents])
    _reject_duplicate_keys(body.documents)

    # Only accept uploads this practice just presigned, and confirm they landed.
    tmp_prefix = f"tmp-uploads/{current_user.practice_id}/"
    for doc in body.documents:
        if not doc.s3_key.startswith(tmp_prefix):
            raise HTTPException(status_code=400, detail="Invalid upload key")
        head = await run_in_threadpool(head_object, doc.s3_key)
        if head is None:
            raise HTTPException(status_code=400, detail=f"Upload missing for {doc.doc_type}")
        if (head.get("ContentLength") or 0) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"{doc.doc_type} file is too large (25 MB max)."
            )

    run_id = uuid4()
    case = Case(
        practice_id=current_user.practice_id,
        created_by=current_user.id,
        status="processing",
        case_type=body.case_type,
        pipeline_run_id=run_id,
    )
    session.add(case)
    await session.flush()

    ip = safe_ip(client_ip(request))
    user_agent = request.headers.get("user-agent")

    for doc in body.documents:
        final_key = case_document_key(current_user.practice_id, case.id, doc.doc_type)
        await run_in_threadpool(move_object, doc.s3_key, final_key)
        head = await run_in_threadpool(head_object, final_key)
        # The cap was checked on the temp key, but the presigned PUT stays
        # writable until the move — re-check the object that actually landed,
        # before the pipeline reads the whole body into memory.
        _assert_within_upload_cap(head, doc.doc_type)
        session.add(
            Document(
                case_id=case.id,
                doc_type=doc.doc_type,
                s3_key=final_key,
                original_filename=doc.filename,
                mime_type="application/pdf",
                file_size_bytes=head.get("ContentLength") if head else None,
                uploaded_by=current_user.id,
            )
        )
        await log_audit(
            session,
            action="document_upload",
            resource_type="case",
            resource_id=case.id,
            user_id=current_user.id,
            practice_id=current_user.practice_id,
            ip=ip,
            user_agent=user_agent,
            metadata={"doc_type": doc.doc_type},
        )

    await log_audit(
        session,
        action="case_create",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"document_count": len(body.documents), "case_type": body.case_type},
    )
    await session.commit()

    # Kick off the pipeline after the response is sent (claimed by run_id).
    background_tasks.add_task(_pipeline_for(body.case_type), case.id, run_id)

    return CreateCaseResponse(id=case.id, status=case.status)


async def _get_owned_case(session: AsyncSession, case_id: UUID, user: User) -> Case:
    """Fetch a case scoped to the caller's practice, or 404. 404 (not 403) so we
    don't leak which case ids exist across practices."""
    case = await session.get(Case, case_id)
    if case is None or case.practice_id != user.practice_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


async def _claim_for_pipeline(
    session: AsyncSession, case_id: UUID, user: User, *, when, conflict: str
) -> UUID:
    """Atomically claim a case for a background pipeline run; returns the run token.

    The eligibility check and the claim are ONE conditional UPDATE. Read-then-write
    let two concurrent callers both observe an eligible status and both stamp a
    token, so two pipelines ran on the same case — duplicate Bedrock spend, and
    racing writes that surfaced as a unique violation flipping the case to `error`.
    Here the second caller blocks on the row lock, re-evaluates its WHERE against
    the committed row, matches nothing, and gets a 409.

    Runs inside the caller's transaction, so if the request fails afterwards the
    claim rolls back with it and the case is not stranded in `processing`.
    """
    run_id = uuid4()
    claimed = await session.scalar(
        update(Case)
        .where(Case.id == case_id, Case.practice_id == user.practice_id, when)
        .values(status="processing", error_message=None, pipeline_run_id=run_id)
        .returning(Case.id)
        .execution_options(synchronize_session=False)
    )
    if claimed is None:
        raise HTTPException(status_code=409, detail=conflict)
    return run_id


async def _latest(session: AsyncSession, model, case_id: UUID, order):
    return await session.scalar(
        select(model).where(model.case_id == case_id).order_by(order).limit(1)
    )


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(
    case_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseDetailResponse:
    case = await _get_owned_case(session, case_id, current_user)
    # PHI-access audit (§164.312(b)) — records who viewed which case.
    await log_read(session, request, current_user, "case_view", "case", case_id)

    documents = (
        await session.scalars(
            select(Document).where(Document.case_id == case_id).order_by(Document.uploaded_at.asc())
        )
    ).all()
    extraction = await _latest(session, Extraction, case_id, Extraction.created_at.desc())
    analysis = await _latest(session, Analysis, case_id, Analysis.created_at.desc())
    letters = (
        await session.scalars(
            select(AppealLetter)
            .where(AppealLetter.case_id == case_id)
            .order_by(AppealLetter.version.desc())
        )
    ).all()
    outcome = await session.scalar(select(Outcome).where(Outcome.case_id == case_id))
    risk_report = (
        await _latest(session, RiskReport, case_id, RiskReport.created_at.desc())
        if case.case_type == "pre_check"
        else None
    )
    corrected = (
        await corrected_claim_service.latest_corrected_claim(session, case_id)
        if case.case_type == "pre_check"
        else None
    )

    letter_details = [
        LetterDetail(
            id=ltr.id,
            version=ltr.version,
            status=ltr.status,
            appeal_type=ltr.appeal_type,
            body=ltr.body,
            created_at=ltr.created_at,
        )
        for ltr in letters
    ]

    return CaseDetailResponse(
        id=case.id,
        status=case.status,
        case_type=case.case_type,
        stalled=_is_stalled(case),
        error_message=case.error_message,
        patient_initials=case.patient_initials,
        payer_name=case.payer_name,
        plan_type=case.plan_type,
        claim_number=case.claim_number,
        date_of_service=case.date_of_service,
        denial_date=case.denial_date,
        appeal_deadline=case.appeal_deadline,
        billed_amount_cents=case.billed_amount_cents,
        denied_amount_cents=case.denied_amount_cents,
        currency=case.currency,
        deadline_note=deadline_note(case.plan_type) if case.appeal_deadline else None,
        documents=[
            DocumentDetail(
                id=d.id,
                doc_type=d.doc_type,
                original_filename=d.original_filename,
                file_size_bytes=d.file_size_bytes,
                ocr_status=d.ocr_status,
            )
            for d in documents
        ],
        extraction=(
            ExtractionDetail(
                payer_name=extraction.payer_name,
                plan_type=extraction.plan_type,
                claim_number=extraction.claim_number,
                carc_codes=extraction.carc_codes,
                rarc_codes=extraction.rarc_codes,
                group_codes=extraction.group_codes,
                cpt_codes=extraction.cpt_codes,
                icd10_codes=extraction.icd10_codes,
                modifiers=extraction.modifiers,
                pos_codes=extraction.pos_codes,
                billed_amount_cents=extraction.billed_amount_cents,
                denied_amount_cents=extraction.denied_amount_cents,
                confidence=(
                    float(extraction.confidence) if extraction.confidence is not None else None
                ),
            )
            if extraction
            else None
        ),
        analysis=(
            AnalysisDetail(
                denial_category=analysis.denial_category,
                is_appealable=analysis.is_appealable,
                appealability_reason=analysis.appealability_reason,
                success_probability=(
                    float(analysis.success_probability)
                    if analysis.success_probability is not None
                    else None
                ),
                probability_band=analysis.probability_band,
                reasoning_text=analysis.reasoning_text,
                recommended_appeal_level=analysis.recommended_appeal_level,
                additional_documents_needed=analysis.additional_documents_needed,
            )
            if analysis
            else None
        ),
        letter=letter_details[0] if letter_details else None,
        letters=letter_details,
        outcome=(
            OutcomeDetail(
                action_taken=outcome.action_taken,
                result=outcome.result,
                amount_recovered_cents=outcome.amount_recovered_cents,
                resolution_date=outcome.resolution_date,
                notes=outcome.notes,
                reported_at=outcome.reported_at,
            )
            if outcome
            else None
        ),
        risk_report=(
            RiskReportDetail(
                overall_risk_band=risk_report.overall_risk_band,
                findings=[RiskFindingDetail(**f) for f in risk_report.findings],
                proposed_edits=[
                    ProposedEditDetail(**e) for e in (risk_report.proposed_edits or [])
                ],
                deterministic_count=risk_report.deterministic_count,
                model_count=risk_report.model_count,
                ncci_version_tag=risk_report.ncci_version_tag,
                created_at=risk_report.created_at,
            )
            if risk_report
            else None
        ),
        claim_editable=(
            case.case_type == "pre_check"
            and case.status == "ready"
            and corrected_claim_service.claim_document_editable(list(documents))
        ),
        corrected_claim=_corrected_claim_detail(corrected) if corrected else None,
    )


def _corrected_claim_detail(row: CorrectedClaim) -> CorrectedClaimDetail:
    return CorrectedClaimDetail(
        id=row.id,
        version=row.version,
        results=[CorrectedClaimEditResult(**r) for r in (row.results or [])],
        total_updated=row.total_updated,
        downloadable=row.s3_key is not None,
        created_at=row.created_at,
        downloaded_at=row.downloaded_at,
    )


# User-facing text per refusal code. Codes, never document content.
_NOT_EDITABLE_MESSAGES = {
    "not_ready": "The pre-check must finish before its claim can be corrected.",
    "no_report": "No risk report exists for this pre-check yet.",
    "no_claim_document": "This pre-check has no draft claim document.",
    "scanned": (
        "This claim was uploaded as a scan, so Heimdall can't edit it. "
        "Apply the changes in your billing system, or upload the claim as a "
        "PDF exported from your billing software."
    ),
    "tampered": "The draft claim no longer matches the file that was analysed.",
}


@router.post(
    "/{case_id}/corrected-claim",
    response_model=CorrectedClaimDetail,
    status_code=status.HTTP_201_CREATED,
)
@ai_limiter.limit(_settings.rate_limit_ai)
async def create_corrected_claim(
    case_id: UUID,
    body: CorrectedClaimRequest,
    request: Request,
    response: Response,  # slowapi injects rate-limit headers here
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CorrectedClaimDetail:
    """Apply the selected proposed edits to the draft claim PDF in place and
    store the result as a new corrected-claim version. No model call — but
    parsing an adversarial 25 MB PDF is real CPU, hence the expensive-op limiter."""
    case = await _get_owned_case(session, case_id, current_user)
    selections = [
        corrected_claim_service.Selection(index=s.index, value=s.value, remove=s.remove)
        for s in body.selections
    ]
    try:
        row = await corrected_claim_service.create_corrected_claim(
            session, case, selections, current_user
        )
    except corrected_claim_service.ClaimNotEditable as exc:
        raise HTTPException(
            status_code=409, detail=_NOT_EDITABLE_MESSAGES.get(exc.code, exc.code)
        ) from None
    except corrected_claim_service.InvalidSelection as exc:
        raise HTTPException(status_code=422, detail=f"Invalid edit selection: {exc}") from None
    except ClaimPatchError as exc:
        # The document as a whole couldn't be handled (layout the parser can't
        # read, or the post-edit verification failed). Nothing was stored.
        raise HTTPException(
            status_code=422,
            detail=(
                "Heimdall couldn't edit this PDF automatically "
                f"({exc.code.replace('_', ' ')}). Apply the changes in your billing system."
            ),
        ) from None

    applied = sum(1 for r in row.results if r["applied"])
    await log_audit(
        session,
        action="corrected_claim_create",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
        metadata={
            "version": row.version,
            "selected": len(row.results),
            "applied": applied,
            "total_updated": row.total_updated,
        },
    )
    await session.commit()
    await session.refresh(row)
    return _corrected_claim_detail(row)


@router.get("/{case_id}/corrected-claim/download-url", response_model=DownloadUrlResponse)
async def corrected_claim_download_url(
    case_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DownloadUrlResponse:
    """Short-lived presigned GET for the latest corrected claim. Same shape as
    the source-document download: the backend never streams the body."""
    case = await _get_owned_case(session, case_id, current_user)
    row = await corrected_claim_service.latest_corrected_claim(session, case.id)
    if row is None or row.s3_key is None:
        raise HTTPException(status_code=404, detail="No corrected claim for this case")
    if row.downloaded_at is None:
        row.downloaded_at = datetime.now(UTC)
    # PHI export audit — the corrected claim carries the patient/claim detail.
    await log_read(session, request, current_user, "corrected_claim_download", "case", case_id)
    url = await run_in_threadpool(presigned_get_url, row.s3_key)
    return DownloadUrlResponse(url=url)


@router.get("/{case_id}/status", response_model=CaseStatusPollResponse)
async def case_status_poll(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusPollResponse:
    """PHI-free status for the detail page's processing poll — no audit row, so a
    watched case doesn't write ~1 audit_logs INSERT every 2s. The full (audited)
    detail is fetched once on load and once more when this flips off 'processing'."""
    case = await _get_owned_case(session, case_id, current_user)
    return CaseStatusPollResponse(id=case.id, status=case.status, stalled=_is_stalled(case))


@router.post("/{case_id}/mark-submitted", response_model=CaseStatusResponse)
async def mark_submitted(
    case_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusResponse:
    case = await _get_owned_case(session, case_id, current_user)
    _require_appeal_case(case)
    if case.status not in {"ready", "submitted"}:
        raise HTTPException(status_code=409, detail="Only a ready case can be marked submitted")
    case.status = "submitted"
    now = datetime.now(UTC)
    if case.submitted_at is None:
        case.submitted_at = now

    # Finalize the letter the practice actually sent. This is what makes
    # `finalized_at` real, and it is what export_corpus's "prefer the finalized
    # letter" branch was always meant to select — the version that went to the
    # payer, which is the one the outcome label belongs to.
    letter = await _latest(session, AppealLetter, case_id, AppealLetter.version.desc())
    if letter is not None and letter.status != "archived":
        if letter.finalized_at is None:
            letter.finalized_at = now
        letter.status = "finalized"

    await log_audit(
        session,
        action="case_mark_submitted",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return CaseStatusResponse(id=case.id, status=case.status)


@router.post("/{case_id}/outcome", response_model=CaseStatusResponse)
async def upsert_outcome(
    case_id: UUID,
    body: OutcomeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusResponse:
    # `result` and `action_taken` are Literal-typed on OutcomeRequest, so an invalid
    # value is already a 422 before this handler runs.
    case = await _get_owned_case(session, case_id, current_user)
    _require_appeal_case(case)
    if case.status not in {"submitted", "resolved"}:
        raise HTTPException(
            status_code=409, detail="Mark the case submitted before logging an outcome"
        )

    # A real upsert, matching this endpoint's name. The previous SELECT-then-INSERT
    # raced `outcomes.case_id`'s unique constraint: a double-clicked submit or a
    # client retry after a slow response had both requests see None, both insert,
    # and the loser raise IntegrityError at commit -> unhandled 500. The same file
    # already solves this class of problem correctly for the pipeline claim.
    values = {
        "action_taken": body.action_taken,
        "result": body.result,
        "amount_recovered_cents": body.amount_recovered_cents,
        "resolution_date": body.resolution_date,
        "notes": body.notes,
        "reported_by": current_user.id,
    }
    await session.execute(
        pg_insert(Outcome)
        .values(case_id=case_id, source="user_reported", **values)
        .on_conflict_do_update(index_elements=["case_id"], set_=values)
    )

    case.status = case_status_after_outcome(body.result)
    await log_audit(
        session,
        action="case_outcome_report",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
        metadata={"result": body.result},
    )
    await session.commit()
    return CaseStatusResponse(id=case.id, status=case.status)


@router.post("/{case_id}/retry", response_model=CaseStatusResponse)
# Same AI limit as create_case and reanalyze_case: a retry schedules the full
# pipeline, which is three Bedrock calls. The atomic claim gate bounds concurrent
# retries, but spend was otherwise bounded only by the failure rate, not by any
# request-rate cap. `response` is the parameter slowapi requires to inject headers.
@ai_limiter.limit(_settings.rate_limit_ai)
async def retry_case(
    case_id: UUID,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusResponse:
    # 404 (not 409) for a case outside the caller's practice — see _get_owned_case.
    case = await _get_owned_case(session, case_id, current_user)
    # Claim atomically: the eligibility test lives in the UPDATE's WHERE, so two
    # concurrent retries cannot both pass it. The fresh token also makes any
    # still-running stalled pipeline abort at its next ownership check.
    run_id = await _claim_for_pipeline(
        session,
        case_id,
        current_user,
        when=or_(Case.status == "error", _stalled_sql()),
        conflict="Only a failed or stalled case can be retried",
    )
    await log_audit(
        session,
        action="case_retry",
        resource_type="case",
        resource_id=case_id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    # Dispatch by case type — retrying a pre-check must not run the appeal pipeline.
    background_tasks.add_task(_pipeline_for(case.case_type), case_id, run_id)
    # The claim wrote status via Core UPDATE (synchronize_session=False), so the
    # ORM copy is stale — report the value the claim just committed.
    return CaseStatusResponse(id=case_id, status="processing")


_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _attachment_disposition(filename: str) -> str:
    """Build a Content-Disposition value that cannot 500 the download.

    Starlette encodes header values as latin-1 in `Response.__init__`, so a single
    non-latin-1 codepoint raises UnicodeEncodeError. `patient_initials` comes
    straight from model output, and a curly apostrophe (U+2019, routine in
    "O'Brien") is enough — producing a permanent 500 on that case's letter with no
    UI path to fix the stored value.

    So: an ASCII allowlist for the plain `filename` (with a `case` fallback if
    nothing survives), plus RFC 5987 `filename*` carrying the real UTF-8 name for
    clients that support it.
    """
    ascii_name = _FILENAME_SAFE.sub("-", filename).strip("-") or "appeal-case.pdf"
    if not ascii_name.lower().endswith(".pdf"):
        ascii_name += ".pdf"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


@router.get("/{case_id}/letter.pdf")
async def download_letter_pdf(
    case_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    case = await _get_owned_case(session, case_id, current_user)
    letter = await _latest(session, AppealLetter, case_id, AppealLetter.version.desc())
    if letter is None or not letter.body:
        raise HTTPException(status_code=404, detail="No appeal letter for this case")
    if letter.status == "archived":
        # A re-analysis flipped this case to not-appealable, or a newer draft
        # replaced this one. The practice must not be able to mail an appeal the
        # system has since retracted.
        raise HTTPException(
            status_code=409,
            detail="This appeal letter was superseded by a later analysis. Re-run the case.",
        )

    pdf = await run_in_threadpool(pdf_gen.render_letter_pdf, letter.body)

    # Build the response BEFORE the audit commit. log_read commits, so committing
    # first recorded a PHI export that could then fail to be constructed and never
    # reach the client — an audit trail asserting a disclosure that did not happen.
    disposition = _attachment_disposition(
        f"appeal-{case.patient_initials or 'case'}-{str(case.id)[:8]}.pdf"
    )
    response = Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )

    # Record the download on the letter itself. `status`/`downloaded_at` were
    # declared in 0001 and never written by anything, which left three
    # letter_status members unreachable and made export_corpus's "prefer the
    # finalized letter" branch dead code. A download is the point at which a draft
    # has actually left the building, so it is the transition worth recording.
    if letter.downloaded_at is None:
        letter.downloaded_at = datetime.now(UTC)
    if letter.status == "draft":
        letter.status = "downloaded"

    # PHI export audit — the drafted letter contains patient/claim detail.
    await log_read(session, request, current_user, "letter_download", "case", case_id)
    return response


def _require_supplemental_types(doc_types: list[str]) -> None:
    bad = [d for d in doc_types if d not in SUPPLEMENTAL_DOC_TYPES]
    if bad or not doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"Additional documents must be one of: {', '.join(SUPPLEMENTAL_DOC_TYPES)}",
        )
    # Bound the per-request fan-out: each supplemental type at most once (else one
    # request could spawn 100 duplicate S3 moves + Document rows + Textract jobs).
    if len(doc_types) != len(set(doc_types)):
        raise HTTPException(
            status_code=400,
            detail="Each additional document type may be provided at most once.",
        )


@router.post("/{case_id}/additional-upload-urls", response_model=UploadUrlsResponse)
async def create_additional_upload_urls(
    case_id: UUID,
    body: UploadUrlsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadUrlsResponse:
    case = await _get_owned_case(session, case_id, current_user)
    # Supplemental docs feed reanalysis, which is appeal-only — presigning for a
    # pre-check would only create orphaned uploads that can never attach.
    _require_appeal_case(case)
    _require_supplemental_types([d.doc_type for d in body.documents])
    uploads: list[UploadSlot] = []
    for doc in body.documents:
        if doc.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")
        key = temp_upload_key(current_user.practice_id)
        url = await run_in_threadpool(presigned_put_url, key, doc.content_type)
        uploads.append(UploadSlot(doc_type=doc.doc_type, s3_key=key, upload_url=url))
    return UploadUrlsResponse(uploads=uploads)


@router.post("/{case_id}/reanalyze", response_model=CaseStatusResponse)
@ai_limiter.limit(_settings.rate_limit_ai)
async def reanalyze_case(
    case_id: UUID,
    body: ReanalyzeRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusResponse:
    """Attach conditional documents to a ready case, then re-run analysis + letter
    (drafting the next letter version) in the background."""
    case = await _get_owned_case(session, case_id, current_user)
    _require_appeal_case(case)
    if case.status != "ready":
        raise HTTPException(status_code=409, detail="Only a ready case can be reanalyzed")
    _require_supplemental_types([d.doc_type for d in body.documents])
    _reject_duplicate_keys(body.documents)

    tmp_prefix = f"tmp-uploads/{current_user.practice_id}/"
    for doc in body.documents:
        if not doc.s3_key.startswith(tmp_prefix):
            raise HTTPException(status_code=400, detail="Invalid upload key")
        head = await run_in_threadpool(head_object, doc.s3_key)
        if head is None:
            raise HTTPException(status_code=400, detail=f"Upload missing for {doc.doc_type}")
        if (head.get("ContentLength") or 0) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"{doc.doc_type} file is too large (25 MB max)."
            )

    # Claim BEFORE moving any object or inserting any Document: two concurrent
    # reanalyze calls would otherwise both pass the `ready` check above and both
    # attach their uploads to the same case. Validation above is read-only, so
    # nothing is left behind when the loser 409s here.
    run_id = await _claim_for_pipeline(
        session,
        case_id,
        current_user,
        when=Case.status == "ready",
        conflict="Only a ready case can be reanalyzed",
    )

    ip = safe_ip(client_ip(request))
    user_agent = request.headers.get("user-agent")
    for doc in body.documents:
        final_key = case_document_key(current_user.practice_id, case.id, doc.doc_type)
        await run_in_threadpool(move_object, doc.s3_key, final_key)
        head = await run_in_threadpool(head_object, final_key)
        # The cap was checked on the temp key, but the presigned PUT stays
        # writable until the move — re-check the object that actually landed,
        # before the pipeline reads the whole body into memory.
        _assert_within_upload_cap(head, doc.doc_type)
        session.add(
            Document(
                case_id=case.id,
                doc_type=doc.doc_type,
                s3_key=final_key,
                original_filename=doc.filename,
                mime_type="application/pdf",
                file_size_bytes=head.get("ContentLength") if head else None,
                uploaded_by=current_user.id,
            )
        )
        await log_audit(
            session,
            action="document_upload",
            resource_type="case",
            resource_id=case.id,
            user_id=current_user.id,
            practice_id=current_user.practice_id,
            ip=ip,
            user_agent=user_agent,
            metadata={"doc_type": doc.doc_type, "reanalyze": True},
        )

    await log_audit(
        session,
        action="case_reanalyze",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"document_count": len(body.documents)},
    )
    await session.commit()

    background_tasks.add_task(run_reanalysis, case_id, run_id)
    # ORM copy is stale after the Core claim UPDATE — report the committed value.
    return CaseStatusResponse(id=case_id, status="processing")
