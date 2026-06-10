from __future__ import annotations

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

from ..log_config import get_logger
from ..settings import Settings, TracingExporter

logger = get_logger(__name__)

_tracer = None


def setup_tracing(settings: Settings) -> None:
    if not _HAS_OTEL or not settings.tracing_enabled:
        logger.info("tracing_disabled")
        return

    resource = Resource(attributes={
        SERVICE_NAME: settings.project_name,
    })

    provider = TracerProvider(resource=resource)

    if settings.tracing_exporter == TracingExporter.CONSOLE:
        exporter = ConsoleSpanExporter()
    else:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces")
        except ImportError:
            logger.warning("otlp_exporter_not_installed, falling back to console")
            exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    global _tracer
    _tracer = trace.get_tracer(settings.project_name)

    logger.info("tracing_enabled", exporter=settings.tracing_exporter.value)


def get_tracer():
    global _tracer
    if not _HAS_OTEL:
        return None
    if _tracer is None:
        _tracer = trace.get_tracer("sports-quant")
    return _tracer
