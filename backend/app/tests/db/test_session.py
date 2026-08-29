"""The API engine caps every connection server-side (LOW-17).

An external lock holder used to pin a pooled connection indefinitely; with
statement_timeout / lock_timeout in the asyncpg startup parameters the server
cancels the statement instead. The integration suite proves the cap bites
(integration/test_statement_timeout.py); this pins that the engine is built
with it and that the values are wired from Settings.
"""

from app.core.config import Settings, settings
from app.db import session


def test_engine_connect_args_carry_the_timeouts():
    server_settings = session.connect_args["server_settings"]
    assert server_settings == {
        "statement_timeout": str(settings.db_statement_timeout_ms),
        "lock_timeout": str(settings.db_lock_timeout_ms),
    }
    # asyncpg sends server_settings as startup strings; a bare integer is
    # rejected at connect time, so the type matters as much as the value.
    assert all(isinstance(v, str) and v.isdigit() for v in server_settings.values())
    assert "ssl" in session.connect_args  # the TLS context must survive alongside


def test_timeout_defaults_are_request_sized():
    fields = Settings.model_fields
    assert fields["db_statement_timeout_ms"].default == 60_000
    assert fields["db_lock_timeout_ms"].default == 10_000
