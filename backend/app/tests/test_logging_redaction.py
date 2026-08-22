import json
import logging

from app.core.logging import JsonFormatter, _redact, _safe_exception


def test_redacts_ssn():
    out = _redact("patient SSN 000-00-0000 on file")  # synthetic per hard rule 1
    assert "000-00-0000" not in out
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
    out = _redact({"note": "ssn 000-00-0000", "inner": {"mid": "9999999999"}})
    assert "[ssn-redacted]" in out["note"]
    assert out["inner"]["mid"] == "[redacted]"


def _exc_info(exc):
    try:
        raise exc
    except Exception:  # noqa: BLE001
        import sys

        return sys.exc_info()


def test_untrusted_exception_message_is_withheld():
    # pypdf/pydantic/json-style errors quote the input they choked on; only the
    # type and frames may reach the log. Simulate a third-party module origin.
    class ForeignError(Exception):
        pass

    ForeignError.__module__ = "pypdf.generic"
    out = _safe_exception(_exc_info(ForeignError("Invalid object @12: b'(Jane Doe) Tj'")))
    assert out["type"] == "ForeignError"
    assert "Jane" not in json.dumps(out)
    assert out["message"].startswith("[message withheld")


def test_app_exception_message_is_kept():
    from app.services.document_extractor import DocumentParseError

    out = _safe_exception(_exc_info(DocumentParseError("PdfReadError")))
    assert out["message"] == "PdfReadError"


def test_formatter_withholds_untrusted_message_end_to_end():
    class ForeignError(Exception):
        pass

    ForeignError.__module__ = "pypdf.generic"
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "pipeline failed", None, None)
    record.exc_info = _exc_info(ForeignError("b'(Jane Doe) Tj'"))
    payload = json.loads(JsonFormatter().format(record))
    assert "Jane" not in json.dumps(payload)
