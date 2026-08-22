import io
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pypdf import PdfReader

from app.core.config import settings
from app.prompts import text as prompt_text
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
        # Explicit timeouts. Without them botocore's defaults apply unbounded in
        # practice, and every call here runs on a Starlette threadpool worker — a
        # regional stall then pins workers for minutes per document instead of
        # producing clean errors. run_textract's own timeout_seconds bounds only
        # the accumulated polling sleep, never the individual HTTP calls.
        _textract = boto3.client(
            "textract",
            region_name=settings.aws_region,
            config=Config(
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _textract


class NotAPdfError(ValueError):
    """The uploaded object is not a PDF (magic-byte check failed)."""


class TooManyPagesError(ValueError):
    """The PDF exceeds the page cap (see settings.max_document_pages)."""


_UTF8_BOM = b"\xef\xbb\xbf"


def _assert_pdf(data: bytes) -> None:
    # Validate by content, not the client-declared type/extension. The signature
    # must be AT THE START — the previous `b"%PDF-" not in data[:1024]` was a
    # SUBSTRING search over the first kilobyte, so a polyglot that merely mentioned
    # "%PDF-" somewhere in its header passed while the comment claimed otherwise.
    #
    # A leading UTF-8 BOM and/or ASCII whitespace is tolerated (real-world writers
    # emit both), but nothing else may precede the signature.
    head = data.removeprefix(_UTF8_BOM).lstrip()
    if not head[:8].startswith(b"%PDF-"):
        raise NotAPdfError("uploaded file is not a valid PDF")


def assert_page_count(reader: PdfReader) -> int:
    """Enforce the page cap before any per-page work happens.

    The only upload guard is the 25 MB byte cap, and a highly compressed PDF can
    hold tens of thousands of pages inside it. `extract_text()` over all of them
    runs on a threadpool worker with no timeout, so a few such uploads stall every
    threadpool-bound operation in the process — and if the file has no embedded
    text it goes to Textract, which bills per page.
    """
    pages = len(reader.pages)
    if pages > settings.max_document_pages:
        raise TooManyPagesError(
            f"PDF has {pages} pages; the limit is {settings.max_document_pages}"
        )
    return pages


class DocumentParseError(Exception):
    """A PDF the parser couldn't read. Deliberately carries NO detail from the
    parser: pypdf's own messages quote bytes of the (decompressed) content
    stream, i.e. document text, and exception messages reach the logs."""


def digital_text_from_bytes(data: bytes) -> str | None:
    """Return embedded PDF text from raw bytes, or None if the PDF looks scanned
    (and so needs OCR). The caller downloads once and hashes the same bytes."""
    _assert_pdf(data)
    try:
        reader = PdfReader(io.BytesIO(data))
        assert_page_count(reader)
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except TooManyPagesError:
        raise
    except Exception as exc:  # noqa: BLE001 — any parser failure; detail intentionally dropped
        raise DocumentParseError(type(exc).__name__) from None
    return text if len(text) >= MIN_DIGITAL_CHARS else None


def run_textract(s3_key: str, poll_seconds: float = 2.0, timeout_seconds: int = 180) -> str:
    """OCR a scanned PDF with Textract async text detection. Textract reads the
    object straight from S3 — the body never flows through the app."""
    client = _textract_client()
    job_id = _with_retries(
        client.start_document_text_detection,
        DocumentLocation={"S3Object": {"Bucket": settings.s3_bucket_name, "Name": s3_key}},
    )["JobId"]

    # Monotonic deadline, not an accumulator of sleep durations. Summing
    # poll_seconds ignored the time each HTTP call itself took, so a slow Textract
    # could keep the loop alive well past timeout_seconds of real elapsed time.
    deadline = time.monotonic() + timeout_seconds
    # Wrap each poll: a single transient ClientError shouldn't fail the whole job.
    result = _with_retries(client.get_document_text_detection, JobId=job_id)
    while result["JobStatus"] == "IN_PROGRESS":
        if time.monotonic() >= deadline:
            raise TimeoutError("Textract job timed out")
        time.sleep(poll_seconds)
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
    """Write the extracted text next to the original; return the new key.

    Section fences are neutralised at STORE time as well as at prompt-build time.
    The prompts delimit untrusted input with `=== SECTION ===` markers, so a PDF
    whose own text contains that pattern could close a fence early and have the
    remainder read as instructions. Defanging here means the stored artifact is
    already safe for any future consumer that forgets to call prompts.text.
    """
    key = s3.extracted_text_key(s3_key)
    s3.put_text(key, prompt_text.strip_fences(text))
    return key
