import io
import time

import boto3
from botocore.exceptions import ClientError
from pypdf import PdfReader

from app.core.config import settings
from app.services import s3

# A digital PDF yields selectable text; a scanned one yields ~nothing and needs
# OCR. This threshold separates the two.
MIN_DIGITAL_CHARS = 20

_textract = None


def _with_retries(fn, *args, attempts: int = 4, base_delay: float = 1.5, **kwargs):
    """Retry a boto3 read on transient ClientErrors. Just after a document is
    written or moved to its final key, S3/Textract can briefly fail to see it;
    the same call succeeds a few seconds later (which is why a manual Retry
    worked). Retrying automatically removes that first-attempt failure."""
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except ClientError:
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay * (attempt + 1))


def _textract_client():
    global _textract
    if _textract is None:
        _textract = boto3.client("textract", region_name=settings.aws_region)
    return _textract


class NotAPdfError(ValueError):
    """The uploaded object is not a PDF (magic-byte check failed)."""


def _assert_pdf(data: bytes) -> None:
    # Validate by content, not the client-declared type/extension. The %PDF
    # signature must appear at the very start (allowing a small BOM/whitespace).
    if b"%PDF-" not in data[:1024]:
        raise NotAPdfError("uploaded file is not a valid PDF")


def digital_text_from_bytes(data: bytes) -> str | None:
    """Return embedded PDF text from raw bytes, or None if the PDF looks scanned
    (and so needs OCR). Lets the caller hash the same bytes without a second read."""
    _assert_pdf(data)
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return text if len(text) >= MIN_DIGITAL_CHARS else None


def extract_digital_text(s3_key: str) -> str | None:
    """Download a PDF and return its embedded text (None if it looks scanned).
    Internal processing only."""
    return digital_text_from_bytes(s3.get_bytes(s3_key))  # get_bytes retries reads


def run_textract(s3_key: str, poll_seconds: float = 2.0, timeout_seconds: int = 180) -> str:
    """OCR a scanned PDF with Textract async text detection. Textract reads the
    object straight from S3 — the body never flows through the app."""
    client = _textract_client()
    job_id = _with_retries(
        client.start_document_text_detection,
        DocumentLocation={"S3Object": {"Bucket": settings.s3_bucket_name, "Name": s3_key}},
    )["JobId"]

    waited = 0.0
    # Wrap each poll: a single transient ClientError shouldn't fail the whole job.
    result = _with_retries(client.get_document_text_detection, JobId=job_id)
    while result["JobStatus"] == "IN_PROGRESS":
        if waited >= timeout_seconds:
            raise TimeoutError("Textract job timed out")
        time.sleep(poll_seconds)
        waited += poll_seconds
        result = _with_retries(client.get_document_text_detection, JobId=job_id)

    if result["JobStatus"] != "SUCCEEDED":
        raise RuntimeError(f"Textract job status {result['JobStatus']}")

    lines: list[str] = []
    page = result
    while True:
        for block in page.get("Blocks", []):
            if block.get("BlockType") == "LINE":
                lines.append(block.get("Text", ""))
        token = page.get("NextToken")
        if not token:
            break
        page = _with_retries(client.get_document_text_detection, JobId=job_id, NextToken=token)

    return "\n".join(lines)


def store_extracted_text(s3_key: str, text: str) -> str:
    """Write the extracted text next to the original; return the new key."""
    key = s3.extracted_text_key(s3_key)
    s3.put_text(key, text)
    return key
