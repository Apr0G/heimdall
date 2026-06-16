from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import Analysis, Case, Document, Extraction, Outcome, User
from app.schemas.case import (
    CaseListItem,
    CaseListResponse,
    CreateCaseRequest,
    CreateCaseResponse,
    UploadSlot,
    UploadUrlsRequest,
    UploadUrlsResponse,
)
from app.services.audit import log_audit, safe_ip
from app.services.pipeline import run_full_pipeline
from app.services.s3 import (
    REQUIRED_DOC_TYPES,
    case_document_key,
    head_object,
    move_object,
    presigned_put_url,
    temp_upload_key,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


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
            denial_category=(
                analyses[c.id].denial_category if c.id in analyses else None
            ),
            is_appealable=analyses[c.id].is_appealable if c.id in analyses else None,
            probability_band=(
                analyses[c.id].probability_band if c.id in analyses else None
            ),
            outcome_result=outcomes[c.id].result if c.id in outcomes else None,
            amount_recovered_cents=(
                outcomes[c.id].amount_recovered_cents if c.id in outcomes else None
            ),
        )
        for c in cases
    ]

    return CaseListResponse(
        items=items, total=total or 0, page=page, page_size=page_size
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
async def create_case(
    body: CreateCaseRequest,
    request: Request,
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
            raise HTTPException(
                status_code=400, detail=f"Upload missing for {doc.doc_type}"
            )

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
