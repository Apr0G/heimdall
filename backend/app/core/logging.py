import json
import logging
import re
import sys
import traceback

# Structured JSON logging.
#
# HARD RULE: never pass PHI into a log record — no patient names,
# no document text, no claim contents. Log lengths, sha256 hashes, and opaque
# IDs only. `logger.info("extracted document", extra={"context": {"doc_id": id,
# "chars": len(text)}})` is fine; logging `text` itself is forbidden.
#
# The redaction below is defense-in-depth for accidental leaks — it is NOT a
# licence to log PHI. It scrubs SSN-shaped strings and long digit runs (member
# IDs) from messages/context. UUIDs, short codes, and amounts are unaffected.

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_DIGITS_RE = re.compile(r"\d{9,}")


def _redact(value: object) -> object:
    if isinstance(value, str):
        return _LONG_DIGITS_RE.sub("[redacted]", _SSN_RE.sub("[ssn-redacted]", value))
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


# How much of an exception's own message we are willing to emit. Exception
# messages are the one part of a traceback that can carry arbitrary payload data.
_MAX_EXC_MESSAGE = 200

# Only exceptions from these module prefixes get their message emitted at all.
# Our own exceptions are written to be PHI-free; AWS/HTTP client errors carry
# service error text. Everything else — parsers in particular — may quote the
# input it choked on (pypdf embeds 80 bytes of the decompressed content stream,
# pydantic echoes field values, json echoes the document snippet), and for those
# the type name plus the frame list is all a debugger gets.
#
# "builtins" is deliberately EXCLUDED: ValueError/KeyError/TypeError/
# UnicodeDecodeError all live there and their str() echoes the offending value
# (e.g. int("<value>") → "invalid literal for int() with base 10: '<value>'"),
# which for model-derived-from-document text is a PHI leak. App-raised builtins
# exceptions carry static messages, so nothing debuggable is lost by dropping it.
_MESSAGE_ALLOWED_MODULES = ("app.", "botocore.", "boto3.", "httpx.", "asyncio.")


def _safe_exception(exc_info) -> dict[str, object]:
    """Render an exception as structured, PHI-bounded fields.

    NOT `formatException`. The default rendering calls `str(exc)`, and SQLAlchemy's
    StatementError appends "[SQL: ...] [parameters: {...}]" there — so a failing
    INSERT would print its bound values (claim number, payer name, patient
    initials, extracted clinical JSON) straight into CloudWatch. `hide_parameters`
    on the engine closes that at the source; this closes it at the sink too, for
    every other exception type that might embed data in its message.

    The frame list is what actually makes an error debuggable, and file/line/
    function names are code identity — never patient data.
    """
    exc_type, exc_value, exc_tb = exc_info
    frames = [
        f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in traceback.extract_tb(exc_tb)
    ]
    module = getattr(exc_type, "__module__", "") or ""
    if exc_value is None or not module.startswith(_MESSAGE_ALLOWED_MODULES):
        message = "" if exc_value is None else "[message withheld: untrusted exception source]"
    else:
        message = str(exc_value)
        if len(message) > _MAX_EXC_MESSAGE:
            message = message[:_MAX_EXC_MESSAGE] + "...[truncated]"
    return {
        "type": getattr(exc_type, "__name__", str(exc_type)),
        "message": _redact(message),
        "frames": frames[-12:],  # deepest frames are the useful ones
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
        }
        # Opt-in structured context, passed via extra={"context": {...}}.
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = _redact(context)
        if record.exc_info:
            payload["exc"] = _safe_exception(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
