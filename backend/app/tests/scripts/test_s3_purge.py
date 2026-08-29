"""Version-aware S3 deletion (HIGH-06).

The bucket is versioned. A keyed delete with no VersionId writes a delete marker
and leaves every prior version fully retrievable — and `security.tf` has no
lifecycle rule over `practices/`, so those versions never expire. The scripts then
DELETE (in FK order, as the app role) the rows holding the only index of those
keys, making the surviving objects permanently unenumerable while the script
prints a destruction count.
"""

import pytest

from app.scripts import s3_purge


class FakeS3:
    """Minimal stand-in for the S3 client: tracks what was actually deleted, and
    whether the caller supplied a VersionId."""

    def __init__(self, versions: dict[str, list[str]]):
        # key -> [version ids], newest first
        self.versions = {k: list(v) for k, v in versions.items()}
        self.delete_calls: list[list[dict]] = []

    def get_paginator(self, name):
        assert name == "list_object_versions"
        return _FakePaginator(self)

    def delete_objects(self, *, Bucket, Delete):  # noqa: N803 — boto3 kwarg casing
        objects = Delete["Objects"]
        self.delete_calls.append(objects)
        for obj in objects:
            key, version = obj["Key"], obj.get("VersionId")
            if version is None:
                # A keyed delete hides but does not destroy — model that faithfully.
                self.versions.setdefault(key, []).insert(0, "delete-marker")
                continue
            if key in self.versions and version in self.versions[key]:
                self.versions[key].remove(version)
                if not self.versions[key]:
                    del self.versions[key]


class _FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, *, Bucket, Prefix):  # noqa: N803
        entries = [
            {"Key": key, "VersionId": v}
            for key, vs in self.client.versions.items()
            if key.startswith(Prefix)
            for v in vs
        ]
        yield {"Versions": entries, "DeleteMarkers": []}


_PREFIX = "practices/p1/cases/c1/denial/"
_KEY = f"{_PREFIX}doc.pdf"
_SIBLING = f"{_KEY}.extracted.txt"


def _bucket() -> FakeS3:
    return FakeS3({_KEY: ["v3", "v2", "v1"], _SIBLING: ["v1"]})


def test_delete_all_versions_removes_every_version():
    s3 = _bucket()
    assert s3_purge.delete_all_versions(s3, "b", _PREFIX) == 4
    assert s3.versions == {}


def test_every_delete_carries_a_version_id():
    """The whole finding: without VersionId nothing is destroyed."""
    s3 = _bucket()
    s3_purge.delete_all_versions(s3, "b", _PREFIX)
    for call in s3.delete_calls:
        for obj in call:
            assert obj.get("VersionId"), f"keyed delete with no VersionId: {obj}"


def test_delete_by_exact_key_does_not_sweep_siblings():
    """A prefix listing for `.../doc.pdf` would also match
    `.../doc.pdf.extracted.txt` — the exact-match filter is what prevents that."""
    s3 = _bucket()
    s3_purge.delete_all_versions_of_keys(s3, "b", {_KEY})
    assert _KEY not in s3.versions
    assert s3.versions[_SIBLING] == ["v1"]


def test_delete_by_keys_ignores_empty_entries():
    s3 = _bucket()
    assert s3_purge.delete_all_versions_of_keys(s3, "b", {"", _SIBLING}) == 1


def test_assert_prefix_empty_passes_when_purged():
    s3 = _bucket()
    s3_purge.delete_all_versions(s3, "b", _PREFIX)
    s3_purge.assert_prefix_empty(s3, "b", _PREFIX)  # must not raise


def test_assert_prefix_empty_aborts_when_versions_survive():
    """Verification runs BEFORE the row DELETE, because the rows are the only
    index of these keys — after that an incomplete purge is unrecoverable."""
    s3 = _bucket()
    with pytest.raises(SystemExit) as exc:
        s3_purge.assert_prefix_empty(s3, "b", _PREFIX)
    assert "NOT truncated" in str(exc.value)


def test_a_keyed_delete_would_have_left_the_data_behind():
    """Regression guard on the original bug: proves the FakeS3 model is faithful
    and that the old approach genuinely destroyed nothing."""
    s3 = _bucket()
    s3.delete_objects(Bucket="b", Delete={"Objects": [{"Key": _KEY}], "Quiet": True})
    assert "v1" in s3.versions[_KEY]
    with pytest.raises(SystemExit):
        s3_purge.assert_prefix_empty(s3, "b", _PREFIX)


def test_batches_respect_the_1000_object_cap():
    s3 = FakeS3({f"{_PREFIX}f{i}.pdf": ["v1"] for i in range(2500)})
    s3_purge.delete_all_versions(s3, "b", _PREFIX)
    assert all(len(call) <= 1000 for call in s3.delete_calls)
    assert s3.versions == {}
