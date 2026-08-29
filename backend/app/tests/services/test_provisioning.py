"""invite_user: the one place the invite rules live (used by the admin API and
the CLI script). Cognito and the session are faked; these pin the rules."""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Practice, User
from app.services import provisioning
from app.services.provisioning import ProvisioningError, invite_user

pytestmark = pytest.mark.asyncio


class FakeSession:
    """`existing_user` is what the first email lookup sees; `after_conflict`
    is what a re-select after a unique violation sees (a concurrent invite's
    row); `flush_errors` are raised by successive flushes."""

    def __init__(self, existing_user=None, practice=None, *, after_conflict=None, flush_errors=()):
        self.existing_user = existing_user
        self.after_conflict = after_conflict
        self.practice = practice
        self.added = []
        self.flush_errors = list(flush_errors)
        self.lookups = 0
        self.savepoint_rolled_back = False

    async def scalar(self, stmt):
        self.lookups += 1
        return self.after_conflict if self.lookups > 1 else self.existing_user

    async def get(self, model, pk):
        return self.practice if model is Practice else None

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    async def flush(self):
        if self.flush_errors:
            raise self.flush_errors.pop(0)

    def begin_nested(self):
        session = self

        class _Savepoint:
            async def __aenter__(self_):
                self_.start = len(session.added)
                return self_

            async def __aexit__(self_, exc_type, exc, tb):
                if exc_type is not None:
                    # Like SQLAlchemy: objects added inside a rolled-back
                    # savepoint are expunged.
                    session.savepoint_rolled_back = True
                    del session.added[self_.start :]
                return False

        return _Savepoint()


def _conflict() -> IntegrityError:
    return IntegrityError("INSERT INTO users", {}, Exception("duplicate key: users_email_key"))


@pytest.fixture
def cognito(monkeypatch):
    m = MagicMock(return_value=("sub-123", True))
    monkeypatch.setattr(provisioning, "admin_invite", m)
    return m


@pytest.fixture
def find_sub(monkeypatch):
    """The read-only lookup that runs BEFORE any invite; None = no Cognito user."""
    m = MagicMock(return_value=None)
    monkeypatch.setattr(provisioning, "admin_find_sub", m)
    return m


async def test_creates_user_in_existing_practice(cognito, find_sub):
    practice = Practice(name="Sunrise Family Medicine")
    practice.id = uuid.uuid4()
    session = FakeSession(practice=practice)
    res = await invite_user(
        session,
        email="  Jane.Doe@Example.com ",
        role="doctor",
        full_name=" Dr. Jane Doe ",
        practice_id=practice.id,
        practice_name=None,
    )
    cognito.assert_called_once_with("jane.doe@example.com")  # normalised before Cognito
    assert res.created_user and not res.created_practice and res.created_cognito
    assert res.user.email == "jane.doe@example.com"
    assert res.user.full_name == "Dr. Jane Doe"
    assert res.user.cognito_sub == "sub-123"
    assert res.user.practice_id == practice.id


async def test_creates_new_practice_when_named(cognito, find_sub):
    session = FakeSession()
    res = await invite_user(
        session,
        email="a@b.com",
        role="office_manager",
        full_name=None,
        practice_id=None,
        practice_name="New Clinic",
    )
    assert res.created_practice
    assert isinstance(session.added[0], Practice) and session.added[0].name == "New Clinic"
    assert isinstance(session.added[1], User)
    assert res.user.practice_id == session.added[0].id


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(email="nope", role="doctor", practice_id=uuid.uuid4()), "valid email"),
        (dict(email="a@b.com", role="superuser", practice_id=uuid.uuid4()), "Role must be"),
        (dict(email="a@b.com", role="doctor"), "existing practice or name"),
        (
            dict(email="a@b.com", role="doctor", practice_id=uuid.uuid4(), practice_name="X"),
            "existing practice or name",
        ),
    ],
)
async def test_input_validation_happens_before_cognito(cognito, find_sub, kwargs, message):
    with pytest.raises(ProvisioningError, match=message):
        await invite_user(
            FakeSession(),
            full_name=None,
            practice_id=kwargs.get("practice_id"),
            practice_name=kwargs.get("practice_name"),
            email=kwargs["email"],
            role=kwargs["role"],
        )
    cognito.assert_not_called()
    find_sub.assert_not_called()


async def test_unknown_practice_is_rejected(cognito, find_sub):
    with pytest.raises(ProvisioningError, match="doesn't exist"):
        await invite_user(
            FakeSession(practice=None),
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=uuid.uuid4(),
            practice_name=None,
        )


async def test_existing_user_same_identity_is_resend_only(cognito, find_sub):
    cognito.return_value = ("sub-123", False)
    find_sub.return_value = "sub-123"
    practice = Practice(name="P")
    practice.id = uuid.uuid4()
    existing = User(email="a@b.com", cognito_sub="sub-123", role="doctor", practice_id=practice.id)
    session = FakeSession(existing_user=existing, practice=practice)
    res = await invite_user(
        session, email="a@b.com", role="admin", full_name=None, practice_id=None, practice_name="Q"
    )
    assert not res.created_user and not res.created_cognito
    assert res.user is existing and res.user.role == "doctor"  # role NOT rewritten
    assert session.added == []


async def test_existing_email_bound_to_other_identity_is_refused(cognito, find_sub):
    find_sub.return_value = "sub-OTHER"
    existing = User(email="a@b.com", cognito_sub="sub-123", role="doctor", practice_id=uuid.uuid4())
    with pytest.raises(ProvisioningError, match="refusing to rebind"):
        await invite_user(
            FakeSession(existing_user=existing),
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=None,
            practice_name="Q",
        )
    # The refusal is decided on the read-only lookup: no identity is created
    # and no temporary password is emailed for a request we then reject.
    cognito.assert_not_called()


async def test_bound_row_whose_identity_is_gone_is_refused_before_invite(cognito, find_sub):
    """No Cognito user at all for an email whose row carries a real sub: an
    invite would mint a NEW sub and the rebind rule would then refuse it —
    after the orphan and the email. Refuse first."""
    find_sub.return_value = None
    existing = User(email="a@b.com", cognito_sub="sub-123", role="doctor", practice_id=uuid.uuid4())
    with pytest.raises(ProvisioningError, match="refusing to rebind"):
        await invite_user(
            FakeSession(existing_user=existing),
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=uuid.uuid4(),
            practice_name=None,
        )
    cognito.assert_not_called()


async def test_identity_replaced_between_lookup_and_invite_is_still_refused(cognito, find_sub):
    find_sub.return_value = "sub-123"
    cognito.return_value = ("sub-OTHER", False)
    existing = User(email="a@b.com", cognito_sub="sub-123", role="doctor", practice_id=uuid.uuid4())
    with pytest.raises(ProvisioningError, match="refusing to rebind"):
        await invite_user(
            FakeSession(existing_user=existing),
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=None,
            practice_name="Q",
        )


async def test_concurrent_invite_conflict_becomes_the_resend_path(cognito, find_sub):
    """Two admins invite the same address at once: the loser's INSERT hits the
    unique email index. It must not 500 — it re-selects and returns the row the
    winner created, exactly as a sequential second invite would."""
    cognito.return_value = ("sub-123", False)
    practice = Practice(name="P")
    practice.id = uuid.uuid4()
    winner_row = User(
        email="a@b.com", cognito_sub="sub-123", role="doctor", practice_id=practice.id
    )
    session = FakeSession(practice=practice, after_conflict=winner_row, flush_errors=[_conflict()])
    res = await invite_user(
        session, email="a@b.com", role="admin", full_name=None, practice_id=None, practice_name="Q"
    )
    assert res.user is winner_row and not res.created_user and not res.created_practice
    # The practice this caller started creating is gone with the savepoint.
    assert session.savepoint_rolled_back and session.added == []


async def test_conflicting_row_with_another_identity_is_refused(cognito, find_sub):
    cognito.return_value = ("sub-123", True)
    other = User(email="a@b.com", cognito_sub="sub-OTHER", role="doctor", practice_id=uuid.uuid4())
    session = FakeSession(after_conflict=other, flush_errors=[_conflict()])
    with pytest.raises(ProvisioningError, match="refusing to rebind"):
        await invite_user(
            session,
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=None,
            practice_name="Q",
        )


async def test_unexplained_integrity_error_still_raises(cognito, find_sub):
    # A unique violation with no users row behind it is not the race — surface it.
    session = FakeSession(after_conflict=None, flush_errors=[_conflict()])
    with pytest.raises(IntegrityError):
        await invite_user(
            session,
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=None,
            practice_name="Q",
        )


async def test_reset_pending_row_may_be_rebound(cognito, find_sub):
    # The one legitimate rebind: an authenticator reset deleted the identity and
    # couldn't re-create it; the admin's re-invite attaches the new sub.
    from app.services.provisioning import RESET_PENDING_PREFIX

    cognito.return_value = ("sub-NEW", True)
    practice = Practice(name="P")
    practice.id = uuid.uuid4()
    existing = User(
        email="a@b.com",
        cognito_sub=f"{RESET_PENDING_PREFIX}sub-OLD",
        role="doctor",
        practice_id=practice.id,
    )
    res = await invite_user(
        FakeSession(existing_user=existing, practice=practice),
        email="a@b.com",
        role="doctor",
        full_name=None,
        practice_id=practice.id,
        practice_name=None,
    )
    assert res.user is existing and existing.cognito_sub == "sub-NEW"
    find_sub.assert_not_called()  # a rebind is the point here; nothing to compare
