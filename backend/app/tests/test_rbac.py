from app.core.auth import role_allowed


def test_role_allowed():
    assert role_allowed("admin", ("admin",)) is True
    assert role_allowed("doctor", ("doctor", "admin")) is True
    assert role_allowed("doctor", ("admin",)) is False
    assert role_allowed(None, ("admin",)) is False
