"""Which requests count as "a human is here" (MED-11, second pass).

The first fix made the idle timeout server-enforced, which closed the hole the
audit named: a CLOSED tab used to leave a session valid for the token's full
remaining life.

It did not close the other half. `ReadyNotifier` polls `processing-ids` every 12s
with `refetchIntervalInBackground: true`, and the case page polls `{id}/status`
every 2s while a pipeline runs. Both go through `get_current_user`, so both were
stamping `last_seen_at` — meaning an OPEN tab held a session alive forever with
nobody at the keyboard. The product's own traffic defeated the control.

These tests pin the classification that fixes it.
"""

import uuid

import pytest

from app.core.auth import is_user_activity

# --- the pollers must NOT count -----------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/cases/processing-ids",
        "/api/cases/processing-ids/",
        f"/api/cases/{uuid.uuid4()}/status",
        f"/api/cases/{uuid.uuid4()}/status/",
    ],
    ids=["ready-notifier", "ready-notifier-slash", "case-status-poll", "case-status-slash"],
)
def test_background_polls_are_not_activity(path):
    """These fire on a timer. If they refreshed the clock, leaving the app open
    on screen would keep the session alive indefinitely."""
    assert is_user_activity(path) is False


# --- genuine interaction MUST count -------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/heartbeat",
        "/api/auth/me",
        "/api/cases",
        "/api/cases/summary",
        f"/api/cases/{uuid.uuid4()}",
        f"/api/cases/{uuid.uuid4()}/letter.pdf",
        f"/api/cases/{uuid.uuid4()}/mark-submitted",
        f"/api/cases/{uuid.uuid4()}/outcome",
        f"/api/cases/{uuid.uuid4()}/retry",
        f"/api/cases/{uuid.uuid4()}/reanalyze",
        f"/api/documents/{uuid.uuid4()}/download-url",
    ],
)
def test_real_requests_are_activity(path):
    assert is_user_activity(path) is True


def test_heartbeat_counts_so_reading_does_not_sign_you_out():
    """The heartbeat is the ONLY signal for a user who is present but not
    clicking — reading a long appeal letter, say. If it were excluded alongside
    the polls, the timeout would fire mid-sentence."""
    assert is_user_activity("/api/auth/heartbeat") is True


# --- the case detail page is not the case status poll -------------------------


def test_case_detail_is_activity_but_its_status_poll_is_not():
    """Same prefix, opposite meaning: opening a case is a person, polling that
    case's status is a timer. Getting this wrong in either direction either
    defeats the timeout or signs people out while they work."""
    case_id = uuid.uuid4()
    assert is_user_activity(f"/api/cases/{case_id}") is True
    assert is_user_activity(f"/api/cases/{case_id}/status") is False


def test_status_suffix_alone_does_not_exempt_a_path():
    """Guards the regex: only a real case-id-shaped segment before /status is
    exempt, so a future `/api/practices/status` route is not silently excluded."""
    assert is_user_activity("/api/cases/not-a-uuid/status") is True
    assert is_user_activity("/status") is True
    assert is_user_activity("/api/status") is True


def test_processing_ids_must_match_exactly():
    """A path that merely contains the poll's name is still activity."""
    assert is_user_activity("/api/cases/processing-ids/extra") is True
