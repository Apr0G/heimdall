"""invite_user: the one place the invite rules live (used by the admin API and
the CLI script). Cognito and the session are faked; these pin the rules."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.models import Practice, User
from app.services import provisioning
from app.services.provisioning import ProvisioningError, invite_user

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self, existing_user=None, practice=None):
        self.existing_user = existing_user
        self.practice = practice
        self.added = []

    async def scalar(self, stmt):
        return self.existing_user

    async def get(self, model, pk):
        return self.practice if model is Practice else None

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    async def flush(self):
        pass


@pytest.fixture
def cognito(monkeypatch):
    m = MagicMock(return_value=("sub-123", True))
    monkeypatch.setattr(provisioning, "admin_invite", m)
    return m


async def test_creates_user_in_existing_practice(cognito):
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


async def test_creates_new_practice_when_named(cognito):
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
async def test_input_validation_happens_before_cognito(cognito, kwargs, message):
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


async def test_unknown_practice_is_rejected(cognito):
    with pytest.raises(ProvisioningError, match="doesn't exist"):
        await invite_user(
            FakeSession(practice=None),
            email="a@b.com",
            role="doctor",
            full_name=None,
            practice_id=uuid.uuid4(),
            practice_name=None,
        )


async def test_existing_user_same_identity_is_resend_only(cognito):
    cognito.return_value = ("sub-123", False)
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


async def test_existing_email_bound_to_other_identity_is_refused(cognito):
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
