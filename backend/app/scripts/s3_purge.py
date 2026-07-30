"""Version-aware S3 deletion for the destruction scripts.

The documents bucket is VERSIONED (`main.tf`). On a versioned bucket a keyed
delete — `delete_objects` with `{"Key": k}` and no `VersionId` — does not destroy
anything: it writes a delete marker and leaves every prior version fully
retrievable by anyone with `s3:GetObjectVersion`. And `security.tf` has no
lifecycle rule covering `practices/`, so `noncurrent_version_expiration` never
collects them either — those versions live forever.

That matters because these scripts then TRUNCATE the tables holding the only
index of those keys, so the surviving objects can never be enumerated for cleanup
again. A destruction attestation given to a practice on that basis would be false.

Everything here deletes by explicit `VersionId`, including delete markers, and
verifies the prefix is empty before the caller is allowed to proceed.
"""

_BATCH = 1000  # delete_objects caps at 1000 objects per call


def _delete_in_batches(s3, bucket: str, victims: list[dict]) -> int:
    for i in range(0, len(victims), _BATCH):
        s3.delete_objects(Bucket=bucket, Delete={"Objects": victims[i : i + _BATCH], "Quiet": True})
    return len(victims)


def list_all_versions(s3, bucket: str, prefix: str) -> list[dict]:
    """Every version and delete-marker under `prefix`, as delete_objects entries."""
    victims: list[dict] = []
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for entry in page.get("Versions", []) + page.get("DeleteMarkers", []):
            victims.append({"Key": entry["Key"], "VersionId": entry["VersionId"]})
    return victims


def delete_all_versions(s3, bucket: str, prefix: str) -> int:
    """Delete every version + delete-marker under a prefix. Returns the count."""
    return _delete_in_batches(s3, bucket, list_all_versions(s3, bucket, prefix))


def delete_all_versions_of_keys(s3, bucket: str, keys: set[str]) -> int:
    """Delete every version of each exact key in `keys`.

    Listing is done per key prefix and then filtered to an exact match, because
    `list_object_versions` has no exact-key mode and a prefix listing for
    ``.../abc.pdf`` would otherwise also sweep ``.../abc.pdf.extracted.txt``.
    """
    victims: list[dict] = []
    for key in sorted(k for k in keys if k):
        victims.extend(v for v in list_all_versions(s3, bucket, key) if v["Key"] == key)
    return _delete_in_batches(s3, bucket, victims)


def assert_prefix_empty(s3, bucket: str, prefix: str) -> None:
    """Raise unless `prefix` holds no versions at all.

    Called BEFORE the caller truncates its tables. The rows are the only index of
    these keys, so once they are gone an incomplete purge is unrecoverable — this
    is the last moment at which the failure is still fixable.
    """
    remaining = list_all_versions(s3, bucket, prefix)
    if remaining:
        raise SystemExit(
            f"ABORTED: {len(remaining)} object version(s) still present under "
            f"s3://{bucket}/{prefix} after the purge. The database rows were NOT "
            "truncated — they are the only index of these keys. Investigate the "
            "S3 permissions (s3:DeleteObjectVersion, s3:ListBucketVersions) and "
            "re-run before assuming anything was destroyed."
        )
