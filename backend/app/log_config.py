import logging
import sys
from pathlib import Path

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer

from .settings import Settings, LogFormat


def _add_trace_id(logger, method_name, event_dict):
    """Inject trace/span IDs from context vars if opentelemetry is installed."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        span_ctx = span.get_span_context()
        if span_ctx.is_valid:
            event_dict["trace_id"] = hex(span_ctx.trace_id)
            event_dict["span_id"] = hex(span_ctx.span_id)
    except ImportError:
        pass
    return event_dict


def _drop_debug_in_prod(logger, method_name, event_dict):
    """Drop debug logs in production."""
    settings = Settings()  # cached
    if settings.is_production and event_dict.get("log_level") == "DEBUG":
        raise structlog.DropEvent
    return event_dict


def build_processors(settings: Settings):
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.log_include_trace_id:
        processors.insert(1, _add_trace_id)

    if settings.is_production:
        processors.insert(0, _drop_debug_in_prod)

    if settings.log_format == LogFormat.JSON:
        processors.append(JSONRenderer())
    else:
        processors.append(ConsoleRenderer())

    return processors


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=build_processors(settings),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or __name__)
