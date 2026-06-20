from app.api.cases import OUTCOME_REMINDER_DAYS, win_rate


def test_win_rate_none_when_nothing_resolved():
    assert win_rate(0, 0) is None


def test_win_rate_basic():
    assert win_rate(1, 2) == 0.5
    assert win_rate(3, 4) == 0.75
    assert win_rate(0, 5) == 0.0


def test_win_rate_rounds():
    assert win_rate(1, 3) == 0.333


def test_reminder_window_is_30_days():
    assert OUTCOME_REMINDER_DAYS == 30
