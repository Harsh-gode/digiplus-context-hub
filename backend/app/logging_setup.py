"""Structured JSON logging with a per-request correlation ID and secret redaction.

Every log line is one JSON object written to both stdout and a rotating log file.
The request ID is stored in a contextvar so any code (routers, AI service) logs it
automatically without passing it around.
"""
import logging
import re
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

from .config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|password|authorization)", re.I)
SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),          # OpenAI / Anthropic style keys
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),          # Google API keys
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
]


def _redact_value(value):
    if isinstance(value, str):
        for pattern in SECRET_VALUE_PATTERNS:
            value = pattern.sub("[REDACTED]", value)
    return value


def redact_secrets(_, __, event_dict):
    """Processor: mask secret-looking keys and values before anything is written."""
    for key in list(event_dict.keys()):
        if SECRET_KEY_PATTERN.search(key):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def add_request_id(_, __, event_dict):
    event_dict.setdefault("request_id", request_id_var.get())
    return event_dict


def setup_logging() -> None:
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level, logging.INFO)

    shared = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_secrets,
    ]

    structlog.configure(
        processors=shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared,
    )

    file_handler = RotatingFileHandler(settings.log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [file_handler, console_handler]
    root.setLevel(level)

    # Keep third-party noise down; our own access log replaces uvicorn's.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
