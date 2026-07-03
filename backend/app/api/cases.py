from datetime import UTC, datetime, timedelta
from uuid import UUID

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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.core.config import settings as _settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models import (
    Analysis,
    AppealLetter,
    Case,
    Document,
    Extraction,
    Outcome,
    User,
)
from app.schemas.case import (
    AnalysisDetail,
    CaseDetailResponse,
    CaseListItem,
    CaseListResponse,
    CaseStatusResponse,
    CaseSummaryResponse,
    CreateCaseRequest,
    CreateCaseResponse,
    DocumentDetail,
    ExtractionDetail,
    LetterDetail,
    OutcomeDetail,
    OutcomeRequest,
    PendingOutcomeItem,
    ReanalyzeRequest,
    UploadSlot,
    UploadUrlsRequest,
    UploadUrlsResponse,
)
from app.services import pdf_gen
from app.services.analysis import SUPPLEMENTAL_DOC_TYPES
from app.services.audit import log_audit, safe_ip
from app.services.pipeline import run_full_pipeline, run_reanalysis
from app.services.s3 import (
    REQUIRED_DOC_TYPES,
    case_document_key,
    head_object,
    move_object,
    presigned_put_url,
    temp_upload_key,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])

VALID_OUTCOME_RESULTS = {"overturned", "upheld", "partial", "pending", "withdrawn"}
# A reported outcome resolves the case unless it is still pending.
_TERMINAL_RESULTS = {"overturned", "upheld", "partial", "withdrawn"}
# A "win" for the recovery dashboard's win-rate.
_WIN_RESULTS = {"overturned", "partial"}
# Days after submission before we nag for an outcome.
OUTCOME_REMINDER_DAYS = 30


def case_status_after_outcome(result: str) -> str:
    return "resolved" if result in _TERMINAL_RESULTS else "submitted"


def win_rate(win_count: int, resolved_count: int) -> float | None:
    """Wins over resolved cases, or None when nothing has resolved yet."""
    if resolved_count <= 0:
        return None
    return round(win_count / resolved_count, 3)


@router.get("", response_model=CaseListResponse)
async def list_cases(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="Filter by case status"),
    payer: str | None = Query(None, description="Case-insensitive payer name search"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> CaseListResponse:
    filters = [Case.practice_id == current_user.practice_id]
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

    items = [
        CaseListItem(
            id=c.id,
            status=c.status,
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

    return CaseListResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.get("/summary", response_model=CaseSummaryResponse)
async def case_summary(
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
        .where(Case.practice_id == pid, Case.created_at >= month_start)
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
            .where(Case.practice_id == pid)
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
                Case.id.not_in(select(Outcome.case_id)),
            )
            .order_by(Case.submitted_at.asc())
        )
    ).all()

    return CaseSummaryResponse(
        month_case_count=month_case_count or 0,
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


def _require_three_docs(doc_types: list[str]) -> None:
    if sorted(doc_types) != sorted(REQUIRED_DOC_TYPES):
        raise HTTPException(
            status_code=400,
            detail=f"Exactly these documents are required: {', '.join(REQUIRED_DOC_TYPES)}",
        )


@router.post("/upload-urls", response_model=UploadUrlsResponse)
async def create_upload_urls(
    body: UploadUrlsRequest,
    current_user: User = Depends(get_current_user),
) -> UploadUrlsResponse:
    _require_three_docs([d.doc_type for d in body.documents])
    uploads: list[UploadSlot] = []
    for doc in body.documents:
        if doc.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")
        key = temp_upload_key(current_user.practice_id)
        url = await run_in_threadpool(presigned_put_url, key, doc.content_type)
        uploads.append(UploadSlot(doc_type=doc.doc_type, s3_key=key, upload_url=url))
    return UploadUrlsResponse(uploads=uploads)


@router.post("", response_model=CreateCaseResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(_settings.rate_limit_ai)
async def create_case(
    body: CreateCaseRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CreateCaseResponse:
    _require_three_docs([d.doc_type for d in body.documents])

    # Only accept uploads this practice just presigned, and confirm they landed.
    tmp_prefix = f"tmp-uploads/{current_user.practice_id}/"
    for doc in body.documents:
        if not doc.s3_key.startswith(tmp_prefix):
            raise HTTPException(status_code=400, detail="Invalid upload key")
        if await run_in_threadpool(head_object, doc.s3_key) is None:
            raise HTTPException(status_code=400, detail=f"Upload missing for {doc.doc_type}")

    case = Case(
        practice_id=current_user.practice_id,
        created_by=current_user.id,
        status="processing",
    )
    session.add(case)
    await session.flush()

    ip = safe_ip(request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")

    for doc in body.documents:
        final_key = case_document_key(current_user.practice_id, case.id, doc.doc_type)
        await run_in_threadpool(move_object, doc.s3_key, final_key)
        head = await run_in_threadpool(head_object, final_key)
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
        metadata={"document_count": len(body.documents)},
    )
    await session.commit()

    # Kick off the (stubbed) pipeline after the response is sent.
    background_tasks.add_task(run_full_pipeline, case.id)

    return CreateCaseResponse(id=case.id, status=case.status)


async def _get_owned_case(session: AsyncSession, case_id: UUID, user: User) -> Case:
    """Fetch a case scoped to the caller's practice, or 404. 404 (not 403) so we
    don't leak which case ids exist across practices."""
    case = await session.get(Case, case_id)
    if case is None or case.practice_id != user.practice_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


async def _latest(session: AsyncSession, model, case_id: UUID, order):
    return await session.scalar(
        select(model).where(model.case_id == case_id).order_by(order).limit(1)
    )


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseDetailResponse:
    case = await _get_owned_case(session, case_id, current_user)

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
    )


@router.post("/{case_id}/mark-submitted", response_model=CaseStatusResponse)
async def mark_submitted(
    case_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusResponse:
    case = await _get_owned_case(session, case_id, current_user)
    if case.status not in {"ready", "submitted"}:
        raise HTTPException(status_code=409, detail="Only a ready case can be marked submitted")
    case.status = "submitted"
    if case.submitted_at is None:
        case.submitted_at = datetime.now(UTC)
    await log_audit(
        session,
        action="case_mark_submitted",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(request.client.host if request.client else None),
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
    case = await _get_owned_case(session, case_id, current_user)
    if body.result not in VALID_OUTCOME_RESULTS:
        raise HTTPException(status_code=400, detail="Invalid outcome result")
    if case.status not in {"submitted", "resolved"}:
        raise HTTPException(
            status_code=409, detail="Mark the case submitted before logging an outcome"
        )

    outcome = await session.scalar(select(Outcome).where(Outcome.case_id == case_id))
    if outcome is None:
        outcome = Outcome(case_id=case_id, source="user_reported")
        session.add(outcome)
    outcome.action_taken = body.action_taken
    outcome.result = body.result
    outcome.amount_recovered_cents = body.amount_recovered_cents
    outcome.resolution_date = body.resolution_date
    outcome.notes = body.notes
    outcome.reported_by = current_user.id

    case.status = case_status_after_outcome(body.result)
    await log_audit(
        session,
        action="case_outcome_report",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        metadata={"result": body.result},
    )
    await session.commit()
    return CaseStatusResponse(id=case.id, status=case.status)


@router.post("/{case_id}/retry", response_model=CaseStatusResponse)
async def retry_case(
    case_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CaseStatusResponse:
    case = await _get_owned_case(session, case_id, current_user)
    if case.status != "error":
        raise HTTPException(status_code=409, detail="Only a failed case can be retried")
    case.status = "processing"
    case.error_message = None
    await log_audit(
        session,
        action="case_retry",
        resource_type="case",
        resource_id=case.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    background_tasks.add_task(run_full_pipeline, case.id)
    return CaseStatusResponse(id=case.id, status=case.status)


@router.get("/{case_id}/letter.pdf")
async def download_letter_pdf(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    case = await _get_owned_case(session, case_id, current_user)
    letter = await _latest(session, AppealLetter, case_id, AppealLetter.version.desc())
    if letter is None or not letter.body:
        raise HTTPException(status_code=404, detail="No appeal letter for this case")
    pdf = await run_in_threadpool(pdf_gen.render_letter_pdf, letter.body)
    filename = f"appeal-{case.claim_number or case.id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require_supplemental_types(doc_types: list[str]) -> None:
    bad = [d for d in doc_types if d not in SUPPLEMENTAL_DOC_TYPES]
    if bad or not doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"Additional documents must be one of: {', '.join(SUPPLEMENTAL_DOC_TYPES)}",
        )


@router.post("/{case_id}/additional-upload-urls", response_model=UploadUrlsResponse)
async def create_additional_upload_urls(
    case_id: UUID,
    body: UploadUrlsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadUrlsResponse:
    await _get_owned_case(session, case_id, current_user)
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
@limiter.limit(_settings.rate_limit_ai)
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
    if case.status != "ready":
        raise HTTPException(status_code=409, detail="Only a ready case can be reanalyzed")
    _require_supplemental_types([d.doc_type for d in body.documents])

    tmp_prefix = f"tmp-uploads/{current_user.practice_id}/"
    for doc in body.documents:
        if not doc.s3_key.startswith(tmp_prefix):
            raise HTTPException(status_code=400, detail="Invalid upload key")
        if await run_in_threadpool(head_object, doc.s3_key) is None:
            raise HTTPException(status_code=400, detail=f"Upload missing for {doc.doc_type}")

    ip = safe_ip(request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    for doc in body.documents:
        final_key = case_document_key(current_user.practice_id, case.id, doc.doc_type)
        await run_in_threadpool(move_object, doc.s3_key, final_key)
        head = await run_in_threadpool(head_object, final_key)
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

    case.status = "processing"
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

    background_tasks.add_task(run_reanalysis, case.id)
    return CaseStatusResponse(id=case.id, status=case.status)
