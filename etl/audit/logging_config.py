"""Structured logging setup (Master Prompt §6: "never print"; §8: "ETL
logging goes to etl_run_log"). Console handler emits one JSON object per
line — machine-parseable for CI/log aggregation, human-readable enough
for local runs.
"""

import json
import logging
from datetime import UTC, datetime

_RESERVED = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        )
        return json.dumps(payload, default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("etl")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
