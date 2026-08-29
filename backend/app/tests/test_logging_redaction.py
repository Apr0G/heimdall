import io
import json
import logging

import pytest

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


def test_uvicorn_loggers_render_through_the_json_formatter():
    """uvicorn installs its own plaintext handlers (propagate=False) before
    app.main is imported and logs every exception that escapes the ASGI app
    through them — str(exc) and the cause chain, bypassing _safe_exception."""
    from app.core.logging import setup_logging

    root = logging.getLogger()
    uv = logging.getLogger("uvicorn.error")
    saved = (uv.handlers[:], uv.propagate, root.handlers[:], root.level)
    plain = io.StringIO()
    try:
        uv.handlers = [logging.StreamHandler(plain)]  # what uvicorn's LOGGING_CONFIG does
        uv.propagate = False
        setup_logging("INFO")
        assert uv.handlers == [] and uv.propagate is True
        # The one remaining sink is the root's JSON handler.
        (json_handler,) = root.handlers
        captured = io.StringIO()
        json_handler.setStream(captured)

        class ParserError(Exception):
            pass

        ParserError.__module__ = "pypdf.generic"
        try:
            raise ParserError("Invalid object: b'(Jane Doe) Tj'")
        except ParserError:
            uv.exception("Exception in ASGI application")
        assert plain.getvalue() == ""  # nothing on the plaintext path
        record = json.loads(captured.getvalue().strip().splitlines()[-1])
        assert record["logger"] == "uvicorn.error"
        assert record["exc"]["type"] == "ParserError"
        assert "Jane" not in captured.getvalue()
    finally:
        uv.handlers, uv.propagate = saved[0], saved[1]
        root.handlers, root.level = saved[2], saved[3]


@pytest.mark.parametrize(
    ("level", "expected"), [("DEBUG", "INFO"), ("INFO", "INFO"), ("WARNING", "WARNING")]
)
def test_log_level_debug_never_reaches_the_aws_client_loggers(level, expected):
    """botocore at DEBUG logs every request dict — for Bedrock that is the
    prompt holding the document text. LOG_LEVEL=DEBUG widens app logging only."""
    from app.core.logging import setup_logging

    root = logging.getLogger()
    saved = (
        root.handlers[:],
        root.level,
        {n: logging.getLogger(n).level for n in ("botocore", "httpx")},
    )
    try:
        setup_logging(level)
        assert logging.getLogger("app.services.claude_client").getEffectiveLevel() == getattr(
            logging, level
        )
        for name in ("botocore", "boto3", "s3transfer", "urllib3", "httpx", "httpcore"):
            assert logging.getLogger(name).getEffectiveLevel() == getattr(logging, expected), name
    finally:
        root.handlers, root.level = saved[0], saved[1]
        for name, lvl in saved[2].items():
            logging.getLogger(name).setLevel(lvl)
