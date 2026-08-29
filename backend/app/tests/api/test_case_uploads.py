"""Uploads moved into a case that then fails must be deleted again (LOW-02).

The DB rows roll back with the request; S3 does not. An exception after the
first `move_object` (a 413 on the post-move size re-check, an S3 error on a
later document) used to strand every already-moved object under practices/
with no Document row — PHI nothing lists and nothing disposes. S3 is stubbed;
the keys are synthetic.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import cases as cases_api
from app.api.cases import MAX_UPLOAD_BYTES, _attach_uploads


class _Session:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


class _S3:
    """Records the calls; `sizes` is the ContentLength head_object reports per
    final key, `fail_move_on` a doc_type whose move raises."""

    def __init__(self, *, sizes: dict[str, int] | None = None, fail_move_on: str | None = None):
        self.sizes = sizes or {}
        self.fail_move_on = fail_move_on
        self.moved: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def move_object(self, src: str, dst: str) -> None:
        if self.fail_move_on and f"/{self.fail_move_on}/" in dst:
            raise RuntimeError("S3 copy failed")
        self.moved.append((src, dst))

    def head_object(self, key: str) -> dict:
        doc_type = key.rsplit("/", 2)[-2]
        return {"ContentLength": self.sizes.get(doc_type, 1000)}

    def delete_object(self, key: str) -> None:
        self.deleted.append(key)


@pytest.fixture
def s3(monkeypatch):
    def _install(**kwargs) -> _S3:
        fake = _S3(**kwargs)
        monkeypatch.setattr(cases_api, "move_object", fake.move_object)
        monkeypatch.setattr(cases_api, "head_object", fake.head_object)
        monkeypatch.setattr(cases_api, "delete_object", fake.delete_object)
        return fake

    monkeypatch.setattr(cases_api, "log_audit", AsyncMock())
    return _install


def _case_and_user():
    user = SimpleNamespace(id=uuid4(), practice_id=uuid4())
    case = SimpleNamespace(id=uuid4())
    return case, user


def _docs(*doc_types: str):
    return [
        SimpleNamespace(doc_type=t, s3_key=f"tmp-uploads/p/{t}-{uuid4()}.pdf", filename=f"{t}.pdf")
        for t in doc_types
    ]


async def test_oversize_second_document_deletes_every_moved_object(s3):
    fake = s3(sizes={"claim": MAX_UPLOAD_BYTES + 1})
    case, user = _case_and_user()
    session = _Session()
    with pytest.raises(HTTPException) as exc:
        await _attach_uploads(
            session, case, _docs("denial", "claim", "clinical"), user, ip=None, user_agent=None
        )
    assert exc.value.status_code == 413
    # Both objects that reached practices/ are gone — including the oversize
    # one that triggered the failure. The third was never moved.
    assert fake.deleted == [dst for _, dst in fake.moved]
    assert [k.rsplit("/", 2)[-2] for k in fake.deleted] == ["denial", "claim"]


async def test_move_failure_on_a_later_document_cleans_up_and_re_raises(s3):
    fake = s3(fail_move_on="clinical")
    case, user = _case_and_user()
    with pytest.raises(RuntimeError, match="S3 copy failed"):
        await _attach_uploads(
            _Session(), case, _docs("denial", "clinical"), user, ip=None, user_agent=None
        )
    assert len(fake.moved) == 1
    assert fake.deleted == [fake.moved[0][1]]


async def test_cleanup_failure_never_masks_the_original_error(s3, monkeypatch):
    s3(sizes={"clinical": MAX_UPLOAD_BYTES + 1})

    def _boom(key: str) -> None:
        raise RuntimeError("delete failed")

    monkeypatch.setattr(cases_api, "delete_object", _boom)
    case, user = _case_and_user()
    with pytest.raises(HTTPException) as exc:
        await _attach_uploads(
            _Session(), case, _docs("denial", "clinical"), user, ip=None, user_agent=None
        )
    assert exc.value.status_code == 413


async def test_happy_path_moves_everything_and_deletes_nothing(s3):
    fake = s3()
    case, user = _case_and_user()
    session = _Session()
    await _attach_uploads(
        session,
        case,
        _docs("claim", "clinical"),
        user,
        ip="203.0.113.5",
        user_agent="ua",
        audit_extra={"reanalyze": True},
    )
    assert fake.deleted == []
    assert [d.doc_type for d in session.added] == ["claim", "clinical"]
    assert all(d.s3_key.startswith(f"practices/{user.practice_id}/") for d in session.added)
    metadata = [c.kwargs["metadata"] for c in cases_api.log_audit.await_args_list]
    assert metadata == [
        {"doc_type": "claim", "reanalyze": True},
        {"doc_type": "clinical", "reanalyze": True},
    ]
