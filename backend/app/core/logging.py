import json
import logging
import sys

# Structured JSON logging.
#
# HARD RULE: never pass PHI into a log record — no patient names,
# no document text, no claim contents. Log lengths, sha256 hashes, and opaque
# IDs only. `logger.info("extracted document", extra={"context": {"doc_id": id,
# "chars": len(text)}})` is fine; logging `text` itself is forbidden.


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Opt-in structured context, passed via extra={"context": {...}}.
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = context
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
