import json
import logging
import re
import sys

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
            payload["exc"] = _redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
