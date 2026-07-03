from app.core.logging import _redact


def test_redacts_ssn():
    out = _redact("patient SSN 123-45-6789 on file")
    assert "123-45-6789" not in out
    assert "[ssn-redacted]" in out


def test_redacts_long_digit_runs():
    out = _redact("member 1234567890123")
    assert "1234567890123" not in out
    assert "[redacted]" in out


def test_keeps_short_codes_and_amounts():
    out = _redact("claim CLM-TEST-0001 denied 45000 cents")
    assert "CLM-TEST-0001" in out  # 4-digit run, untouched
    assert "45000" in out  # 5-digit amount, untouched


def test_redacts_nested_context():
    out = _redact({"note": "ssn 111-22-3333", "inner": {"mid": "9999999999"}})
    assert "[ssn-redacted]" in out["note"]
    assert out["inner"]["mid"] == "[redacted]"
