from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import Case, Document, User
from app.schemas.case import DownloadUrlResponse
from app.services.audit import log_read
from app.services.s3 import presigned_get_url

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{document_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    document_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DownloadUrlResponse:
    """Hand back a short-lived presigned GET URL for a document the caller's
    practice owns. The backend never streams the file body itself."""
    doc = await session.get(Document, document_id)
    case = await session.get(Case, doc.case_id) if doc is not None else None
    # 404 (not 403) on cross-practice access so ids don't leak.
    if doc is None or case is None or case.practice_id != current_user.practice_id:
        raise HTTPException(status_code=404, detail="Document not found")
    # PHI-access audit — granting access to a source document.
    await log_read(session, request, current_user, "document_access", "document", document_id)
    url = await run_in_threadpool(presigned_get_url, doc.s3_key)
    return DownloadUrlResponse(url=url)
