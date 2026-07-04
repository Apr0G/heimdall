import time
import uuid
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

# The three documents every case requires.
REQUIRED_DOC_TYPES = ("denial", "claim", "clinical")

_client = None


def _get_client():
    # Lazily created so importing this module never requires AWS connectivity.
    global _client
    if _client is None:
        # SigV4 is required for presigned PUTs against an SSE-KMS bucket.
        _client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            config=Config(signature_version="s3v4"),
        )
    return _client


def temp_upload_key(practice_id: uuid.UUID) -> str:
    """Key for the pre-case upload (no case id exists at presign time)."""
    return f"tmp-uploads/{practice_id}/{uuid.uuid4()}.pdf"


def case_document_key(practice_id: uuid.UUID, case_id: uuid.UUID, doc_type: str) -> str:
    return f"practices/{practice_id}/cases/{case_id}/{doc_type}/{uuid.uuid4()}.pdf"


def presigned_put_url(key: str, content_type: str = "application/pdf", expires: int = 900) -> str:
    return _get_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
    )


def presigned_get_url(key: str, expires: int = 900) -> str:
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key},
        ExpiresIn=expires,
    )


def head_object(key: str) -> dict[str, Any] | None:
    """Return object metadata, or None if it does not exist. Without s3:ListBucket
    (least privilege) S3 answers a HEAD for a missing object with 403 rather than
    404, so we treat that as 'not found' too. A genuine access problem would still
    surface on the subsequent GetObject."""
    try:
        return _get_client().head_object(Bucket=settings.s3_bucket_name, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "404",
            "NoSuchKey",
            "NotFound",
            "403",
            "Forbidden",
        }:
            return None
        raise


def move_object(src_key: str, dst_key: str) -> None:
    """Copy then delete — S3 has no atomic move. Re-encrypts under the bucket
    default KMS key on copy."""
    client = _get_client()
    bucket = settings.s3_bucket_name
    client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": src_key},
        Key=dst_key,
    )
    client.delete_object(Bucket=bucket, Key=src_key)


def get_bytes(key: str) -> bytes:
    """Read an object's bytes — internal processing only (e.g. pypdf), never for
    serving file bodies to clients. Retries transient ClientErrors: an object
    that was just written or moved to its final key can be briefly invisible,
    which is why a first analysis attempt could fail but a Retry succeeded."""
    for attempt in range(4):
        try:
            return _get_client().get_object(Bucket=settings.s3_bucket_name, Key=key)["Body"].read()
        except ClientError:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")  # for type-checkers; the loop always returns or raises


def put_text(key: str, text: str) -> None:
    _get_client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )


def extracted_text_key(original_key: str) -> str:
    return f"{original_key}.extracted.txt"
