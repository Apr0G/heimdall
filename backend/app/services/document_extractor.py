import io
import time

import boto3
from pypdf import PdfReader

from app.core.config import settings
from app.services import s3

# A digital PDF yields selectable text; a scanned one yields ~nothing and needs
# OCR. This threshold separates the two.
MIN_DIGITAL_CHARS = 20

_textract = None


def _textract_client():
    global _textract
    if _textract is None:
        _textract = boto3.client("textract", region_name=settings.aws_region)
    return _textract


def extract_digital_text(s3_key: str) -> str | None:
    """Return embedded PDF text, or None if the PDF looks scanned (and so needs
    OCR). Downloads the bytes for pypdf — internal processing only."""
    data = s3.get_bytes(s3_key)
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return text if len(text) >= MIN_DIGITAL_CHARS else None


def run_textract(
    s3_key: str, poll_seconds: float = 2.0, timeout_seconds: int = 180
) -> str:
    """OCR a scanned PDF with Textract async text detection. Textract reads the
    object straight from S3 — the body never flows through the app."""
    client = _textract_client()
    job_id = client.start_document_text_detection(
        DocumentLocation={
            "S3Object": {"Bucket": settings.s3_bucket_name, "Name": s3_key}
        }
    )["JobId"]

    waited = 0.0
    result = client.get_document_text_detection(JobId=job_id)
    while result["JobStatus"] == "IN_PROGRESS":
        if waited >= timeout_seconds:
            raise TimeoutError("Textract job timed out")
        time.sleep(poll_seconds)
        waited += poll_seconds
        result = client.get_document_text_detection(JobId=job_id)

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
        page = client.get_document_text_detection(JobId=job_id, NextToken=token)

    return "\n".join(lines)


def store_extracted_text(s3_key: str, text: str) -> str:
    """Write the extracted text next to the original; return the new key."""
    key = s3.extracted_text_key(s3_key)
    s3.put_text(key, text)
    return key
