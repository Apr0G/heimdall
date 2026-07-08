from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.cases import STALE_PROCESSING, _is_stalled


def _case(status: str, updated_ago: timedelta) -> SimpleNamespace:
    return SimpleNamespace(status=status, updated_at=datetime.now(UTC) - updated_ago)


def test_fresh_processing_is_not_stalled():
    assert _is_stalled(_case("processing", timedelta(minutes=1))) is False


def test_old_processing_is_stalled():
    assert _is_stalled(_case("processing", STALE_PROCESSING + timedelta(minutes=1))) is True


def test_non_processing_never_stalled():
    assert _is_stalled(_case("ready", timedelta(days=1))) is False
    assert _is_stalled(_case("error", timedelta(days=1))) is False


def test_missing_updated_at_is_not_stalled():
    assert _is_stalled(SimpleNamespace(status="processing", updated_at=None)) is False
